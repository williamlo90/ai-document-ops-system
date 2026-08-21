from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from app.core.security import SecurityContext, require_admin
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.models import DocumentRecord, ReviewTask
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
    ReviewTaskRepository,
)
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.state_writer import DocumentStateWriter
from app.documents.workflow import DocumentWorkflowService
from app.extraction.schemas import InvoiceData
from app.integrations.models import (
    AccountingIntegrationAdapter,
    IntegrationDeliveryRecord,
    IntegrationDeliveryStatus,
    IntegrationExportResult,
    IntegrationIdempotencyConflict,
    IntegrationInvoicePayload,
    IntegrationLineItem,
    IntegrationOutcomeUnknown,
)
from app.integrations.repositories import IntegrationDeliveryRepository
from app.integrations.delivery_executor import (
    IntegrationDeliveryExecutor,
    integration_audit,
    key_fingerprint,
    safe_error_detail,
)


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


@dataclass(frozen=True)
class IntegrationSendResult:
    document: DocumentRecord
    integration_result: IntegrationExportResult
    delivery: IntegrationDeliveryRecord
    replayed: bool = False


class InvoiceIntegrationService:
    def __init__(
        self,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        reviews: ReviewTaskRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        adapter: AccountingIntegrationAdapter,
        deliveries: IntegrationDeliveryRepository,
        transactions: TransactionManager | None = None,
        state_writer: DocumentStateWriter | None = None,
    ) -> None:
        self.documents = documents
        self.extractions = extractions
        self.reviews = reviews
        self.audits = audits
        self.workflow = workflow
        self.adapter = adapter
        self.deliveries = deliveries
        self.transactions = transactions or NoopTransactionManager()
        resolved_state_writer = state_writer or DocumentStateWriter(
            documents,
            audits,
            workflow,
            self.transactions,
        )
        self.delivery_executor = IntegrationDeliveryExecutor(
            adapter=adapter,
            deliveries=deliveries,
            audits=audits,
            transactions=self.transactions,
            state_writer=resolved_state_writer,
        )

    def send_approved_invoice(
        self,
        document_id: UUID,
        context: SecurityContext,
        *,
        idempotency_key: str | None = None,
    ) -> IntegrationSendResult:
        require_admin(context)
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        try:
            review = self._require_approval_evidence(document)
        except InvalidStatusTransition as exc:
            self._audit_blocked(document, context.actor, str(exc))
            raise
        normalized_key = normalize_idempotency_key(
            _derived_delivery_key(document, review.id)
            if self.adapter.event_prefix == "erp_draft"
            else idempotency_key
        )
        existing = self.deliveries.get_by_key(
            context.workspace_id, self.adapter.name, normalized_key
        )
        if document.status != DocumentStatus.APPROVED and not (
            document.status == DocumentStatus.EXPORTED and existing is not None
        ):
            raise InvalidStatusTransition(
                "Only approved documents can be sent to outbound integrations"
            )
        try:
            payload = self._payload_for_document(document)
            payload_hash = self.adapter.payload_hash(payload)
        except (InvalidStatusTransition, ValueError) as exc:
            self._audit_blocked(document, context.actor, str(exc))
            raise
        if existing is not None:
            return self._handle_existing_delivery(
                existing,
                document=document,
                payload_hash=payload_hash,
                context=context,
            )
        delivery, created = self.deliveries.reserve(
            IntegrationDeliveryRecord(
                workspace_id=context.workspace_id,
                document_id=document.id,
                adapter_name=self.adapter.name,
                idempotency_key=normalized_key,
                payload_hash=payload_hash,
            )
        )
        if not created:
            return self._handle_existing_delivery(
                delivery,
                document=document,
                payload_hash=payload_hash,
                context=context,
            )
        if self.adapter.event_prefix == "erp_draft":
            self.audits.add(
                integration_audit(
                    document,
                    event_type="erp_draft_requested",
                    actor=context.actor,
                    payload_summary=f"key={key_fingerprint(normalized_key)}",
                )
            )
        return self._deliver(document, payload, delivery, context)

    def reconcile_delivery(
        self,
        *,
        idempotency_key: str,
        context: SecurityContext,
        succeeded: bool,
        external_id: str | None,
        reason: str,
    ) -> IntegrationDeliveryRecord:
        require_admin(context)
        normalized_key = normalize_idempotency_key(idempotency_key)
        delivery = self.deliveries.get_by_key(
            context.workspace_id, self.adapter.name, normalized_key
        )
        if delivery is None:
            raise NotFoundError("Integration delivery not found")
        document = self.documents.get(delivery.document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError("Integration delivery not found")
        if delivery.status == IntegrationDeliveryStatus.SUCCEEDED:
            if succeeded and external_id == delivery.external_id:
                return delivery
            raise IntegrationIdempotencyConflict("A successful delivery cannot be overwritten")
        normalized_reason = " ".join(reason.split())[:500]
        if not normalized_reason:
            raise ValueError("Reconciliation reason is required")
        if succeeded:
            normalized_external_id = (external_id or "").strip()
            if not normalized_external_id:
                raise ValueError("external_id is required for successful reconciliation")
            reconciled = replace(
                delivery,
                status=IntegrationDeliveryStatus.SUCCEEDED,
                external_id=normalized_external_id[:200],
                error_code=None,
                error_detail=None,
                retryable=False,
                updated_at=datetime.now(UTC),
            )
            event_type = "integration_export_reconciled_succeeded"
        else:
            if document.status == DocumentStatus.EXPORTED:
                raise IntegrationIdempotencyConflict(
                    "An exported document cannot be reconciled as failed"
                )
            reconciled = replace(
                delivery,
                status=IntegrationDeliveryStatus.FAILED,
                external_id=None,
                error_code="manually_confirmed_not_delivered",
                error_detail="Provider delivery was manually confirmed as not delivered.",
                retryable=True,
                updated_at=datetime.now(UTC),
            )
            event_type = "integration_export_reconciled_failed"
        with self.transactions.transaction():
            self.deliveries.save(reconciled)
            if succeeded:
                self.delivery_executor.mark_document_exported(document, reconciled, context.actor)
            self.audits.add(
                integration_audit(
                    document,
                    event_type=event_type,
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={self.adapter.name}; key={key_fingerprint(normalized_key)}; "
                        f"reason={normalized_reason}"
                    ),
                )
            )
        return reconciled

    def _handle_existing_delivery(
        self,
        delivery: IntegrationDeliveryRecord,
        *,
        document: DocumentRecord,
        payload_hash: str,
        context: SecurityContext,
    ) -> IntegrationSendResult:
        if delivery.document_id != document.id or delivery.payload_hash != payload_hash:
            raise IntegrationIdempotencyConflict(
                "Idempotency key is already bound to a different export payload"
            )
        if delivery.status == IntegrationDeliveryStatus.SUCCEEDED:
            if not delivery.external_id:
                raise IntegrationOutcomeUnknown("Stored success is missing its external id")
            self.delivery_executor.mark_document_exported(document, delivery, context.actor)
            return IntegrationSendResult(
                document=document,
                integration_result=IntegrationExportResult(
                    adapter_name=delivery.adapter_name,
                    external_id=delivery.external_id,
                    external_url=delivery.external_url,
                    provider_docstatus=delivery.provider_docstatus,
                    provider_updated_at=delivery.provider_updated_at,
                    status=(
                        "draft_created" if self.adapter.event_prefix == "erp_draft" else "sent"
                    ),
                ),
                delivery=delivery,
                replayed=True,
            )
        if delivery.status in {
            IntegrationDeliveryStatus.PENDING,
            IntegrationDeliveryStatus.UNKNOWN,
        }:
            raise IntegrationOutcomeUnknown(
                "Delivery outcome is not confirmed; reconcile it before retrying"
            )
        if not delivery.retryable:
            raise IntegrationIdempotencyConflict(
                "The previous delivery failed permanently for this idempotency key"
            )
        if document.status != DocumentStatus.APPROVED:
            raise InvalidStatusTransition(
                "Only approved documents can be sent to outbound integrations"
            )
        if delivery.attempt_count >= 3:
            raise IntegrationIdempotencyConflict("The delivery reached its maximum attempt count")
        claimed = self.deliveries.claim_retry(delivery.id)
        if claimed is None:
            raise IntegrationOutcomeUnknown("Another request already claimed this retry")
        if self.adapter.event_prefix == "erp_draft":
            self.audits.add(
                integration_audit(
                    document,
                    event_type="erp_draft_retry_claimed",
                    actor=context.actor,
                    payload_summary=(
                        f"attempt={claimed.attempt_count}; "
                        f"key={key_fingerprint(claimed.idempotency_key)}"
                    ),
                )
            )
        payload = self._payload_for_document(document)
        return self._deliver(document, payload, claimed, context)

    def _deliver(
        self,
        document: DocumentRecord,
        payload: IntegrationInvoicePayload,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
    ) -> IntegrationSendResult:
        result, succeeded_delivery = self.delivery_executor.deliver(
            document,
            payload,
            delivery,
            context,
        )
        return IntegrationSendResult(
            document=document,
            integration_result=result,
            delivery=succeeded_delivery,
        )

    def get_delivery(
        self,
        document_id: UUID,
        context: SecurityContext,
    ) -> IntegrationDeliveryRecord | None:
        require_admin(context)
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        return self.deliveries.get_for_document(
            context.workspace_id,
            self.adapter.name,
            document_id,
        )

    def reconcile_provider_delivery(
        self,
        document_id: UUID,
        context: SecurityContext,
    ) -> IntegrationDeliveryRecord:
        require_admin(context)
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        delivery = self.deliveries.get_for_document(
            context.workspace_id,
            self.adapter.name,
            document_id,
        )
        if delivery is None:
            raise NotFoundError("Integration delivery not found")
        if delivery.status == IntegrationDeliveryStatus.SUCCEEDED:
            return delivery
        payload = self._payload_for_document(document)
        return self.delivery_executor.reconcile_provider(
            document,
            payload,
            delivery,
            context,
        )

    def _payload_for_document(self, document: DocumentRecord) -> IntegrationInvoicePayload:
        stored = self.extractions.get_for_document(document.id)
        if stored.validation_report.has_errors:
            raise InvalidStatusTransition("Resolve invoice issues before creating an ERP draft")
        data = stored.extraction_result.extraction.data
        return _payload(document, data)

    def _require_approval_evidence(self, document: DocumentRecord) -> ReviewTask:
        if document.status not in {DocumentStatus.APPROVED, DocumentStatus.EXPORTED}:
            raise InvalidStatusTransition(
                "Only approved documents can be sent to outbound integrations"
            )
        try:
            review = self.reviews.get_for_document(document.id)
        except NotFoundError as exc:
            raise InvalidStatusTransition("Human approval evidence is missing") from exc
        if review.status != "approved" or not review.reviewed_by or review.reviewed_at is None:
            raise InvalidStatusTransition("Human approval evidence is incomplete")
        return review

    def _audit_blocked(self, document: DocumentRecord, actor: str, reason: str) -> None:
        if self.adapter.event_prefix != "erp_draft":
            return
        self.audits.add(
            integration_audit(
                document,
                event_type="erp_draft_blocked",
                actor=actor,
                payload_summary=safe_error_detail(ValueError(reason)),
            )
        )


def _payload(document: DocumentRecord, data: InvoiceData) -> IntegrationInvoicePayload:
    return IntegrationInvoicePayload(
        document_id=str(document.id),
        workspace_id=document.workspace_id,
        vendor_name=data.vendor_name,
        invoice_number=data.invoice_number,
        invoice_date=data.invoice_date.isoformat() if data.invoice_date else None,
        due_date=data.due_date.isoformat() if data.due_date else None,
        subtotal=_decimal(data.subtotal),
        tax=_decimal(data.tax),
        total=_decimal(data.total),
        currency=data.currency,
        line_items=tuple(
            IntegrationLineItem(
                description=item.description,
                quantity=_decimal(item.quantity),
                unit_price=_decimal(item.unit_price),
                amount=_decimal(item.amount),
            )
            for item in data.line_items
        ),
    )


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def normalize_idempotency_key(value: str | None) -> str:
    normalized = (value or "").strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Idempotency-Key must be 8-128 characters using letters, numbers, '.', '_', ':', or '-'"
        )
    return normalized


def _derived_delivery_key(document: DocumentRecord, review_id: UUID) -> str:
    identity = f"{document.workspace_id}\0{document.id}\0{review_id}"
    return f"erpnext:{sha256(identity.encode('utf-8')).hexdigest()}"
