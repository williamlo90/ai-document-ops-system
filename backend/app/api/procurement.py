from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from app.api.dependencies import get_container, require_authenticated_context
from app.core.security import UnauthorizedError, require_any_role
from app.documents.repositories import NotFoundError
from app.procurement.models import (
    StrictModel,
    ProcurementRecord,
    Mapping,
    Policy,
    EvidenceUpdate,
    SnapshotInput,
    MatchPolicy,
    CommittedBilling,
    ExceptionPolicy,
    ExceptionUpdate,
)
from app.procurement.service import EvidenceConflict

router = APIRouter(prefix="/ap", tags=["AP evidence"])


class ImportPayload(StrictModel):
    records: list[ProcurementRecord] = Field(min_length=1, max_length=100)


class CsvPayload(StrictModel):
    content: str = Field(max_length=1_000_000)


class ApprovalPayload(StrictModel):
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class MatchApprovalPayload(StrictModel):
    basis_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class BillingPayload(StrictModel):
    records: list[CommittedBilling] = Field(min_length=1, max_length=100)


class ReleasePayload(StrictModel):
    reason: str = Field(min_length=10, max_length=1000)
    reconciliation_ref: str = Field(min_length=3, max_length=120)


def call(action):
    try:
        return action()
    except UnauthorizedError as exc:
        raise HTTPException(403, "Forbidden") from exc
    except NotFoundError as exc:
        raise HTTPException(404, "Not found") from exc
    except (EvidenceConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/sources/import")
def import_sources(
    payload: ImportPayload,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(
        lambda: container.ap_service.import_records(
            [r.model_dump(mode="json") for r in payload.records], context
        )
    )


@router.post("/sources/import-csv")
def import_csv(
    payload: CsvPayload,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(lambda: container.ap_service.import_csv(payload.content, context))


@router.put("/mapping")
def mapping(
    payload: Mapping,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(lambda: container.ap_service.configure("mapping", payload, context))


@router.put("/policy")
def policy(
    payload: Policy,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(lambda: container.ap_service.configure("policy", payload, context))


@router.get("/invoices/{document_id}")
def evidence(
    document_id: UUID,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    def view():
        container.ap_service.document(document_id, context)
        history = container.ap_service.repo.history(
            context.workspace_id, "invoice", str(document_id)
        )
        values, _, _ = container.ap_service.invoice_values(document_id, context)
        from app.procurement.service import digest

        latest = container.ap_service.repo.latest_for_document(
            context.workspace_id, "snapshot", document_id
        )
        snapshot_status = (
            container.ap_service.approval_status(latest["id"], context) if latest else None
        )
        latest_match = container.ap_service.repo.latest_for_document(
            context.workspace_id, "match", document_id
        )
        current_match = (
            match_service(container).status(latest_match["id"], context) if latest_match else None
        )
        return {
            "capabilities": {
                "review": context.role in {"admin", "reviewer"},
                "approve": context.role in {"admin", "ap_approver"},
                "admin": context.role == "admin",
            },
            "snapshot_status": snapshot_status,
            "match_status": current_match,
            "history": history,
            "current": history[-1] if history else None,
            "needs_capture": not history or history[-1]["extraction_hash"] != digest(values),
            "posting_ready": False,
        }

    return call(view)


@router.post("/invoices/{document_id}/capture")
def capture(
    document_id: UUID,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    def action():
        require_any_role(context, {"admin", "reviewer"})
        return container.ap_service.capture(document_id, context)

    return call(action)


@router.put("/invoices/{document_id}/evidence")
def attest(
    document_id: UUID,
    payload: EvidenceUpdate,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(lambda: container.ap_service.attest(document_id, payload, context))


@router.post("/invoices/{document_id}/snapshots")
def snapshot(
    document_id: UUID,
    payload: SnapshotInput,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(lambda: container.ap_service.snapshot(document_id, payload, context))


@router.post("/snapshots/{snapshot_id}/approve")
def approve(
    snapshot_id: UUID,
    payload: ApprovalPayload,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(
        lambda: container.ap_service.approve(str(snapshot_id), payload.payload_hash, context)
    )


@router.get("/snapshots/{snapshot_id}")
def approval_status(
    snapshot_id: UUID,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    return call(lambda: container.ap_service.approval_status(str(snapshot_id), context))


def match_service(container):
    from app.procurement.matching import MatchService

    return MatchService(container.ap_service)


def exception_service(container):
    from app.procurement.exceptions import ExceptionService

    return ExceptionService(container.ap_service)


@router.put("/exception-policy")
def configure_exception_policy(payload: ExceptionPolicy, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: exception_service(container).configure_policy(payload, context))


@router.get("/exceptions")
def list_ap_exceptions(document_id: UUID | None = None, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: {"items": exception_service(container).list_cases(context, document_id=document_id)})


@router.put("/exceptions/{exception_id}")
def update_ap_exception(exception_id: str, payload: ExceptionUpdate, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: exception_service(container).update(exception_id, payload, context, match_service(container)))


@router.put("/match-policy")
def configure_match_policy(payload: MatchPolicy, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: match_service(container).configure_policy(payload, context))


@router.post("/billings/import")
def import_billings(payload: BillingPayload, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: match_service(container).import_billings([r.model_dump(mode="json") for r in payload.records], context))


@router.post("/snapshots/{snapshot_id}/match")
def assess_match(snapshot_id: UUID, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: match_service(container).assess(str(snapshot_id), context))


@router.get("/matches/{match_id}")
def match_status(match_id: UUID, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: match_service(container).status(str(match_id), context))


@router.post("/matches/{match_id}/approve")
def approve_match(match_id: UUID, payload: MatchApprovalPayload, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: match_service(container).approve(str(match_id), payload.basis_hash, context))


@router.post("/matches/{match_id}/release")
def release_match(match_id: UUID, payload: ReleasePayload, context=Depends(require_authenticated_context), container=Depends(get_container)):
    return call(lambda: match_service(container).release(str(match_id), payload.reason, payload.reconciliation_ref, context))


class SyncPayload(StrictModel):
    kind: str = Field(pattern="^(po|receipt)$")
    source_id: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=120)
    site_timezone: str = Field(min_length=1, max_length=80)

    @field_validator("site_timezone")
    @classmethod
    def timezone_exists(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown site timezone") from exc
        return value


@router.post("/sources/sync-erpnext")
def sync_erpnext(
    payload: SyncPayload,
    context=Depends(require_authenticated_context),
    container=Depends(get_container),
):
    def action():
        require_any_role(context, {"admin"})
        from app.integrations.erpnext_client import ERPNextClient
        from app.procurement.erpnext import read_procurement
        from app.integrations.models import IntegrationDeliveryError

        settings = container.settings
        if not settings.erpnext_api_key or not settings.erpnext_api_secret:
            raise EvidenceConflict("ERP credentials are not configured")
        client = ERPNextClient(
            settings.erpnext_base_url,
            api_key=settings.erpnext_api_key,
            api_secret=settings.erpnext_api_secret,
            timeout_seconds=settings.erpnext_timeout_seconds,
            allowed_hosts=settings.erpnext_allowed_hosts,
        )
        try:
            record = read_procurement(
                client, payload.kind, payload.source_id, payload.site_timezone
            )
        except IntegrationDeliveryError as exc:
            raise EvidenceConflict(
                "ERP source unavailable; check read permission and connectivity"
            ) from exc
        if record.company != payload.company:
            raise EvidenceConflict("ERP company differs from requested company")
        return container.ap_service.import_records(
            [record.model_dump(mode="json")], context, refresh_unchanged=True
        )

    return call(action)
