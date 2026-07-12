from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.observability import OperationEvent, log_operation
from app.core.security import SecurityContext, require_admin
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
    IntegrationDeliveryError,
    IntegrationExportResult,
    IntegrationInvoicePayload,
    IntegrationLineItem,
)


@dataclass(frozen=True)
class IntegrationSendResult:
    document: DocumentRecord
    integration_result: IntegrationExportResult


class InvoiceIntegrationService:
    def __init__(
        self,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        adapter: AccountingIntegrationAdapter,
    ) -> None:
        self.documents = documents
        self.extractions = extractions
        self.audits = audits
        self.workflow = workflow
        self.adapter = adapter

    def send_approved_invoice(
        self,
        document_id: UUID,
        context: SecurityContext,
    ) -> IntegrationSendResult:
        require_admin(context)
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        if document.status != DocumentStatus.APPROVED:
            raise InvalidStatusTransition(
                "Only approved documents can be sent to outbound integrations"
            )
        payload = self._payload_for_document(document)
        self.audits.add(
            _integration_audit(
                document,
                event_type="integration_export_attempted",
                actor=context.actor,
                payload_summary=f"adapter={self.adapter.name}",
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
            result = self.adapter.send_invoice(payload)
        except IntegrationDeliveryError as exc:
            self.audits.add(
                _integration_audit(
                    document,
                    event_type="integration_export_failed",
                    actor=context.actor,
                    payload_summary=(
                        f"adapter={self.adapter.name}; code={exc.code}; "
                        f"retryable={str(exc.retryable).lower()}"
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
        self.audits.add(
            _integration_audit(
                document,
                event_type="integration_export_succeeded",
                actor=context.actor,
                payload_summary=f"adapter={result.adapter_name}; external_id={result.external_id}",
            )
        )
        self.audits.add(
            self.workflow.transition(
                document,
                DocumentStatus.EXPORTED,
                context.actor,
                payload_summary=f"adapter={result.adapter_name}; external_id={result.external_id}",
            )
        )
        self.documents.add(document)
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
        return IntegrationSendResult(document=document, integration_result=result)

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
