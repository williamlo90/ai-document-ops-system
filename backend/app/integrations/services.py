from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from app.core.observability import OperationEvent, log_operation
from app.core.security import SecurityContext, require_admin
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
)
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService
from app.extraction.schemas import InvoiceData
from app.integrations.models import (
    AccountingIntegrationAdapter,
    IntegrationDeliveryRecord,
    IntegrationDeliveryError,
    IntegrationDeliveryStatus,
    IntegrationExportResult,
    IntegrationIdempotencyConflict,
    IntegrationInvoicePayload,
    IntegrationLineItem,
    IntegrationOutcomeUnknown,
)
from app.integrations.repositories import IntegrationDeliveryRepository


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
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        adapter: AccountingIntegrationAdapter,
        deliveries: IntegrationDeliveryRepository,
        transactions: TransactionManager | None = None,
    ) -> None:
        self.documents = documents
        self.extractions = extractions
        self.audits = audits
        self.workflow = workflow
        self.adapter = adapter
        self.deliveries = deliveries
        self.transactions = transactions or NoopTransactionManager()

    def send_approved_invoice(
        self,
        document_id: UUID,
        context: SecurityContext,
        *,
        idempotency_key: str,
    ) -> IntegrationSendResult:
        require_admin(context)
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        normalized_key = normalize_idempotency_key(idempotency_key)
        existing = self.deliveries.get_by_key(
            context.workspace_id, self.adapter.name, normalized_key
        )
        if document.status != DocumentStatus.APPROVED and not (
            document.status == DocumentStatus.EXPORTED and existing is not None
        ):
            raise InvalidStatusTransition(
                "Only approved documents can be sent to outbound integrations"
            )
        payload = self._payload_for_document(document)
        payload_hash = _payload_hash(payload)
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
                retryable=True,
                updated_at=datetime.now(UTC),
            )
            event_type = "integration_export_reconciled_failed"
        with self.transactions.transaction():
            self.deliveries.save(reconciled)
            if succeeded:
                self._mark_document_exported(document, reconciled, context.actor)
            self.audits.add(
                _integration_audit(
                    document,
                    event_type=event_type,
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={self.adapter.name}; key={_key_fingerprint(normalized_key)}; "
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
            self._mark_document_exported(document, delivery, context.actor)
            return IntegrationSendResult(
                document=document,
                integration_result=IntegrationExportResult(
                    adapter_name=delivery.adapter_name,
                    external_id=delivery.external_id,
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
        claimed = self.deliveries.claim_retry(delivery.id)
        if claimed is None:
            raise IntegrationOutcomeUnknown("Another request already claimed this retry")
        payload = self._payload_for_document(document)
        return self._deliver(document, payload, claimed, context)

    def _deliver(
        self,
        document: DocumentRecord,
        payload: IntegrationInvoicePayload,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
    ) -> IntegrationSendResult:
        key_fingerprint = _key_fingerprint(delivery.idempotency_key)
        with self.transactions.transaction():
            self.audits.add(
                _integration_audit(
                    document,
                    event_type="integration_export_attempted",
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={self.adapter.name}; key={key_fingerprint}; "
                        f"attempt={delivery.attempt_count}"
                    ),
                )
            )
        log_operation(
            OperationEvent(
                event_type="integration_export_attempted",
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                provider_name=self.adapter.name,
                status="attempted",
            )
        )
        try:
            result = self.adapter.send_invoice(
                payload,
                idempotency_key=delivery.idempotency_key,
            )
            if result.adapter_name != self.adapter.name or not result.external_id.strip():
                raise IntegrationDeliveryError(
                    "Integration returned an invalid delivery receipt",
                    code="invalid_delivery_receipt",
                    retryable=False,
                    outcome_unknown=True,
                )
        except IntegrationDeliveryError as exc:
            failed_delivery = replace(
                delivery,
                status=(
                    IntegrationDeliveryStatus.UNKNOWN
                    if exc.outcome_unknown
                    else IntegrationDeliveryStatus.FAILED
                ),
                error_code=exc.code,
                retryable=exc.retryable and not exc.outcome_unknown,
                updated_at=datetime.now(UTC),
            )
            with self.transactions.transaction():
                self.deliveries.save(failed_delivery)
                self.audits.add(
                    _integration_audit(
                        document,
                        event_type="integration_export_failed",
                        actor=context.actor,
                        payload_summary=(
                            f"adapter={self.adapter.name}; code={exc.code}; "
                            f"retryable={str(exc.retryable).lower()}; "
                            f"outcome_unknown={str(exc.outcome_unknown).lower()}; "
                            f"key={key_fingerprint}"
                        ),
                    )
                )
            log_operation(
                OperationEvent(
                    event_type="integration_export_failed",
                    workspace_id=context.workspace_id,
                    actor=context.actor,
                    document_id=str(document.id),
                    provider_name=self.adapter.name,
                    status="failed",
                    error_code=exc.code,
                    retryable=exc.retryable,
                )
            )
            raise
        succeeded_delivery = replace(
            delivery,
            status=IntegrationDeliveryStatus.SUCCEEDED,
            external_id=result.external_id,
            error_code=None,
            retryable=False,
            updated_at=datetime.now(UTC),
        )
        with self.transactions.transaction():
            self.deliveries.save(succeeded_delivery)
            self.audits.add(
                _integration_audit(
                    document,
                    event_type="integration_export_succeeded",
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={result.adapter_name}; external_id={result.external_id}; "
                        f"key={key_fingerprint}"
                    ),
                )
            )
            self._mark_document_exported(document, succeeded_delivery, context.actor)
        log_operation(
            OperationEvent(
                event_type="integration_export_succeeded",
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                provider_name=result.adapter_name,
                status="sent",
            )
        )
        return IntegrationSendResult(
            document=document,
            integration_result=result,
            delivery=succeeded_delivery,
        )

    def _mark_document_exported(
        self,
        document: DocumentRecord,
        delivery: IntegrationDeliveryRecord,
        actor: str,
    ) -> None:
        if document.status == DocumentStatus.EXPORTED:
            return
        if document.status != DocumentStatus.APPROVED:
            raise InvalidStatusTransition(
                "A delivered invoice can only finalize from approved status"
            )
        self.audits.add(
            self.workflow.transition(
                document,
                DocumentStatus.EXPORTED,
                actor,
                payload_summary=(
                    f"adapter={delivery.adapter_name}; external_id={delivery.external_id}"
                ),
            )
        )
        self.documents.add(document)

    def _payload_for_document(self, document: DocumentRecord) -> IntegrationInvoicePayload:
        stored = self.extractions.get_for_document(document.id)
        data = stored.extraction_result.extraction.data
        return _payload(document, data)


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


def _payload_hash(payload: IntegrationInvoicePayload) -> str:
    canonical = json.dumps(asdict(payload), sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _key_fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _integration_audit(
    document: DocumentRecord,
    *,
    event_type: str,
    actor: str,
    payload_summary: str,
) -> AuditEvent:
    return AuditEvent(
        document_id=document.id,
        event_type=event_type,
        actor=actor,
        old_status=document.status,
        new_status=document.status,
        payload_summary=payload_summary,
    )
