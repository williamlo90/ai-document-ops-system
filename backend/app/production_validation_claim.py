from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Sequence
from uuid import UUID

from app.api.dependencies import AppContainer, build_container
from app.core.observability import OperationEvent, configure_structured_logging, log_operation
from app.core.settings import Settings, load_settings


RUN_ID_ENV = "PRODUCTION_VALIDATION_RUN_ID"
VALIDATION_WORKSPACE = "azure-validation"
_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{11,95}$")


class ValidationGuardError(RuntimeError):
    pass


def validate_claim_guards(
    settings: Settings,
    *,
    requested_run_id: str,
    configured_run_id: str | None,
    confirmed: bool,
) -> None:
    failures: list[str] = []
    if settings.app_env.strip().lower() != "production":
        failures.append("APP_ENV must equal production")
    if settings.workspace_id.strip() != VALIDATION_WORKSPACE:
        failures.append(f"APP_WORKSPACE_ID must equal {VALIDATION_WORKSPACE}")
    if settings.parser_provider.strip().lower() != "mock":
        failures.append("PARSER_PROVIDER must equal mock")
    if settings.extractor_provider.strip().lower() != "mock":
        failures.append("EXTRACTOR_PROVIDER must equal mock")
    if not _RUN_ID_PATTERN.fullmatch(requested_run_id):
        failures.append("run ID format is invalid")
    if not configured_run_id or requested_run_id != configured_run_id:
        failures.append(f"run ID must exactly match {RUN_ID_ENV}")
    if not confirmed:
        failures.append("explicit lease-abandonment confirmation is required")
    if failures:
        raise ValidationGuardError("; ".join(failures))


def claim_and_exit(container: AppContainer, *, job_id: UUID, run_id: str) -> dict[str, object]:
    job = container.jobs.get(job_id)
    document = container.documents.get(job.document_id)
    if document.workspace_id != VALIDATION_WORKSPACE:
        raise ValidationGuardError("target job is outside the isolated validation workspace")
    now = datetime.now(UTC)
    claimed = container.jobs.claim_processable(
        job_id,
        stale_before=now - timedelta(seconds=container.settings.worker_job_lease_seconds),
        now=now,
    )
    if claimed is None or claimed.lease_token is None:
        raise ValidationGuardError("target job is not currently claimable")
    log_operation(
        OperationEvent(
            event_type="production_validation_job_claimed_and_exited",
            workspace_id=document.workspace_id,
            actor="production-validation-claim-and-exit",
            document_id=str(document.id),
            job_id=str(claimed.id),
            status=claimed.status.value,
            attempt_count=claimed.attempt_count,
            trace_id=run_id,
        )
    )
    return {
        "job_id": str(claimed.id),
        "document_id": str(document.id),
        "status": claimed.status.value,
        "attempt_count": claimed.attempt_count,
        "lease_abandoned": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Claim one validation job and exit without committing a result."
    )
    parser.add_argument("--job-id", type=UUID, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm-lease-abandonment", action="store_true")
    args = parser.parse_args(argv)
    settings = load_settings()
    validate_claim_guards(
        settings,
        requested_run_id=args.run_id,
        configured_run_id=os.environ.get(RUN_ID_ENV),
        confirmed=args.confirm_lease_abandonment,
    )
    configure_structured_logging()
    container = build_container(settings)
    try:
        result = claim_and_exit(container, job_id=args.job_id, run_id=args.run_id)
    finally:
        container.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
