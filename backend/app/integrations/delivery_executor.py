from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

from app.core.observability import OperationEvent, log_operation
from app.core.security import SecurityContext
from app.core.transactions import TransactionManager
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import AuditRepository
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.state_writer import DocumentStateWriter
from app.integrations.models import (
    AccountingIntegrationAdapter,
    IntegrationDeliveryError,
    IntegrationDeliveryRecord,
    IntegrationDeliveryStatus,
    IntegrationExportResult,
    IntegrationIdempotencyConflict,
    IntegrationInvoicePayload,
)
from app.integrations.repositories import IntegrationDeliveryRepository


class IntegrationDeliveryExecutor:
    def __init__(
        self,
        *,
        adapter: AccountingIntegrationAdapter,
        deliveries: IntegrationDeliveryRepository,
        audits: AuditRepository,
        transactions: TransactionManager,
        state_writer: DocumentStateWriter,
    ) -> None:
        self.adapter = adapter
        self.deliveries = deliveries
        self.audits = audits
        self.transactions = transactions
        self.state_writer = state_writer

    def deliver(
        self,
        document: DocumentRecord,
        payload: IntegrationInvoicePayload,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
    ) -> tuple[IntegrationExportResult, IntegrationDeliveryRecord]:
        fingerprint = key_fingerprint(delivery.idempotency_key)
        self._record_attempt(document, delivery, context, fingerprint)
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
            self._record_failure(document, delivery, context, fingerprint, exc)
            raise
        succeeded = self._record_success(document, delivery, context, fingerprint, result)
        return result, succeeded

    def reconcile_provider(
        self,
        document: DocumentRecord,
        payload: IntegrationInvoicePayload,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
    ) -> IntegrationDeliveryRecord:
        payload_hash = self.adapter.payload_hash(payload)
        if payload_hash != delivery.payload_hash:
            raise IntegrationIdempotencyConflict(
                "Approved invoice data changed after delivery was reserved"
            )
        result = self.adapter.find_invoice(
            payload,
            idempotency_key=delivery.idempotency_key,
            payload_hash=delivery.payload_hash,
        )
        if result is None:
            return self._record_not_found(document, delivery, context.actor)
        return self._record_reconciled(document, delivery, result, context.actor)

    def mark_document_exported(
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
        self.state_writer.transition(
            document,
            DocumentStatus.EXPORTED,
            actor,
            payload_summary=(
                f"adapter={delivery.adapter_name}; external_id={delivery.external_id}"
            ),
        )

    def _record_attempt(
        self,
        document: DocumentRecord,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
        fingerprint: str,
    ) -> None:
        event_type = integration_event(self.adapter, "create_started", "attempted")
        with self.transactions.transaction():
            self.audits.add(
                integration_audit(
                    document,
                    event_type=event_type,
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={self.adapter.name}; key={fingerprint}; "
                        f"attempt={delivery.attempt_count}"
                    ),
                )
            )
        log_operation(
            OperationEvent(
                event_type=event_type,
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                provider_name=self.adapter.name,
                status="attempted",
            )
        )

    def _record_failure(
        self,
        document: DocumentRecord,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
        fingerprint: str,
        exc: IntegrationDeliveryError,
    ) -> None:
        event_type = _failure_event(self.adapter, exc)
        failed = replace(
            delivery,
            status=(
                IntegrationDeliveryStatus.UNKNOWN
                if exc.outcome_unknown
                else IntegrationDeliveryStatus.FAILED
            ),
            error_code=exc.code,
            error_detail=safe_error_detail(exc),
            retryable=exc.retryable and not exc.outcome_unknown,
            updated_at=datetime.now(UTC),
        )
        with self.transactions.transaction():
            self.deliveries.save(failed)
            self.audits.add(
                integration_audit(
                    document,
                    event_type=event_type,
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={self.adapter.name}; code={exc.code}; "
                        f"retryable={str(exc.retryable).lower()}; "
                        f"outcome_unknown={str(exc.outcome_unknown).lower()}; "
                        f"key={fingerprint}"
                    ),
                )
            )
        log_operation(
            OperationEvent(
                event_type=event_type,
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                provider_name=self.adapter.name,
                status="failed",
                error_code=exc.code,
                retryable=exc.retryable,
            )
        )

    def _record_success(
        self,
        document: DocumentRecord,
        delivery: IntegrationDeliveryRecord,
        context: SecurityContext,
        fingerprint: str,
        result: IntegrationExportResult,
    ) -> IntegrationDeliveryRecord:
        succeeded = replace(
            delivery,
            status=IntegrationDeliveryStatus.SUCCEEDED,
            external_id=result.external_id,
            external_url=result.external_url,
            provider_docstatus=result.provider_docstatus,
            provider_updated_at=result.provider_updated_at,
            error_code=None,
            error_detail=None,
            retryable=False,
            updated_at=datetime.now(UTC),
        )
        event_type = integration_event(self.adapter, "created", "succeeded")
        with self.transactions.transaction():
            self.deliveries.save(succeeded)
            self.audits.add(
                integration_audit(
                    document,
                    event_type=event_type,
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={result.adapter_name}; external_id={result.external_id}; "
                        f"key={fingerprint}"
                    ),
                )
            )
            self.mark_document_exported(document, succeeded, context.actor)
        log_operation(
            OperationEvent(
                event_type=event_type,
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                provider_name=result.adapter_name,
                status="sent",
            )
        )
        return succeeded

    def _record_not_found(
        self,
        document: DocumentRecord,
        delivery: IntegrationDeliveryRecord,
        actor: str,
    ) -> IntegrationDeliveryRecord:
        failed = replace(
            delivery,
            status=IntegrationDeliveryStatus.FAILED,
            error_code="erpnext_draft_not_found",
            error_detail="ERPNext did not contain a draft for this delivery.",
            retryable=delivery.attempt_count < 3,
            updated_at=datetime.now(UTC),
        )
        with self.transactions.transaction():
            self.deliveries.save(failed)
            self.audits.add(
                integration_audit(
                    document,
                    event_type=integration_event(self.adapter, "failed", "failed"),
                    actor=actor,
                    payload_summary=(
                        "code=erpnext_draft_not_found; "
                        f"key={key_fingerprint(delivery.idempotency_key)}"
                    ),
                )
            )
        return failed

    def _record_reconciled(
        self,
        document: DocumentRecord,
        delivery: IntegrationDeliveryRecord,
        result: IntegrationExportResult,
        actor: str,
    ) -> IntegrationDeliveryRecord:
        now = datetime.now(UTC)
        reconciled = replace(
            delivery,
            status=IntegrationDeliveryStatus.SUCCEEDED,
            external_id=result.external_id,
            external_url=result.external_url,
            provider_docstatus=result.provider_docstatus,
            provider_updated_at=result.provider_updated_at,
            reconciled_at=now,
            error_code=None,
            error_detail=None,
            retryable=False,
            updated_at=now,
        )
        with self.transactions.transaction():
            self.deliveries.save(reconciled)
            self.audits.add(
                integration_audit(
                    document,
                    event_type=integration_event(
                        self.adapter, "reconciled", "reconciled_succeeded"
                    ),
                    actor=actor,
                    payload_summary=(
                        f"external_id={result.external_id}; "
                        f"key={key_fingerprint(delivery.idempotency_key)}"
                    ),
                )
            )
            self.mark_document_exported(document, reconciled, actor)
        return reconciled


def integration_event(
    adapter: AccountingIntegrationAdapter,
    erp_suffix: str,
    generic_suffix: str,
) -> str:
    if adapter.event_prefix == "erp_draft":
        return f"erp_draft_{erp_suffix}"
    return f"integration_export_{generic_suffix}"


def integration_audit(
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


def key_fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def safe_error_detail(exc: Exception) -> str:
    return " ".join(str(exc).split())[:300] or "Integration delivery failed."


def _failure_event(
    adapter: AccountingIntegrationAdapter,
    exc: IntegrationDeliveryError,
) -> str:
    if adapter.event_prefix != "erp_draft":
        return "integration_export_failed"
    if exc.outcome_unknown:
        return "erp_draft_outcome_unknown"
    if exc.code == "erpnext_unsafe_state":
        return "erp_draft_unsafe_state_detected"
    return "erp_draft_failed"
