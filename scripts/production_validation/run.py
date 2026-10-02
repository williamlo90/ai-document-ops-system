from __future__ import annotations

import argparse
import os
import re
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from scripts.production_validation.metrics import (
    evaluate_acceptance,
    evaluate_document_invariants,
    evaluate_upload_invariants,
    summarize_samples,
    thresholds_as_dict,
)
from scripts.production_validation.models import AcceptanceThresholds, CheckResult, RequestSample
from scripts.production_validation.report import build_report, write_report


REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_ENV = "PRODUCTION_VALIDATION_ACCESS_TOKEN"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_args(args)
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(f"Set {TOKEN_ENV} before running the validation harness.")

    run_id = _run_id()
    started_at = _now()
    started = time.perf_counter()
    samples, expected_uploads = run_workload(
        base_url=args.base_url,
        access_token=token,
        duration_seconds=args.duration_seconds,
        read_users=args.read_users,
        read_interval_seconds=args.read_interval_seconds,
        upload_rate_per_minute=args.upload_rate_per_minute,
        request_timeout_seconds=args.request_timeout_seconds,
        run_id=run_id,
    )
    workload_elapsed = time.perf_counter() - started
    document_states = reconcile_documents(
        base_url=args.base_url,
        access_token=token,
        samples=samples,
        timeout_seconds=args.settle_timeout_seconds,
        poll_interval_seconds=args.settle_poll_seconds,
    )
    elapsed = time.perf_counter() - started
    completed_at = _now()
    thresholds = AcceptanceThresholds()
    summary = summarize_samples(samples, elapsed_seconds=workload_elapsed)
    summary["document_state_counts"] = dict(sorted(Counter(document_states.values()).items()))
    summary["reconciliation_seconds"] = round(elapsed - workload_elapsed, 3)
    checks = evaluate_acceptance(summary, thresholds)
    checks.extend(evaluate_upload_invariants(samples, expected_uploads=expected_uploads))
    checks.extend(evaluate_document_invariants(samples, document_states))
    checks.append(
        _duration_check(
            observed_seconds=workload_elapsed,
            expected_seconds=args.duration_seconds,
        )
    )
    manifest: dict[str, object] = {
        "run_id": run_id,
        "scope": args.profile,
        "target_label": args.target_label,
        "source_revision": _source_revision(),
        "source_dirty": _workspace_dirty(),
        "started_at": started_at,
        "completed_at": completed_at,
        "workload": {
            "duration_seconds": args.duration_seconds,
            "read_users": args.read_users,
            "read_interval_seconds": args.read_interval_seconds,
            "upload_rate_per_minute": args.upload_rate_per_minute,
            "expected_uploads": expected_uploads,
        },
        "thresholds": thresholds_as_dict(thresholds),
    }
    report = build_report(manifest=manifest, summary=summary, checks=checks, samples=samples)
    output_dir = args.output_root / run_id
    json_path, markdown_path = write_report(report, output_dir)
    print(f"Validation status: {str(report['status']).upper()}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if report["status"] == "passed" else 1


def run_workload(
    *,
    base_url: str,
    access_token: str,
    duration_seconds: float,
    read_users: int,
    read_interval_seconds: float,
    upload_rate_per_minute: float,
    request_timeout_seconds: float,
    run_id: str,
) -> tuple[list[RequestSample], int]:
    samples: list[RequestSample] = []
    sample_lock = threading.Lock()
    deadline = time.monotonic() + duration_seconds
    upload_interval = 60.0 / upload_rate_per_minute
    expected_uploads = max(
        1, int((duration_seconds + upload_interval - 0.000001) // upload_interval)
    )

    def record(sample: RequestSample) -> None:
        with sample_lock:
            samples.append(sample)

    def read_user(user_index: int) -> None:
        next_request = time.monotonic()
        with httpx.Client(base_url=base_url, timeout=request_timeout_seconds) as client:
            while next_request < deadline:
                _wait_until(next_request)
                if time.monotonic() >= deadline:
                    break
                record(_read_invoices(client, access_token, user_index))
                next_request += read_interval_seconds
        _wait_until(deadline)

    def upload_user() -> None:
        next_request = time.monotonic()
        upload_index = 0
        with httpx.Client(base_url=base_url, timeout=request_timeout_seconds) as client:
            while upload_index < expected_uploads:
                _wait_until(next_request)
                record(_upload_document(client, access_token, run_id, upload_index))
                upload_index += 1
                next_request += upload_interval

    with ThreadPoolExecutor(max_workers=read_users + 1) as executor:
        futures = [executor.submit(read_user, index) for index in range(read_users)]
        futures.append(executor.submit(upload_user))
        for future in futures:
            future.result()
    samples.sort(key=lambda sample: sample.started_at)
    return samples, expected_uploads


def reconcile_documents(
    *,
    base_url: str,
    access_token: str,
    samples: list[RequestSample],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, str]:
    document_ids = {
        sample.document_id
        for sample in samples
        if sample.operation == "upload_document" and sample.expected_response and sample.document_id
    }
    states = {document_id: "unresolved" for document_id in document_ids}
    if not document_ids:
        return states
    pending = set(document_ids)
    pending_states = {"uploaded", "queued", "processing", "extracted"}
    deadline = time.monotonic() + timeout_seconds
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        while pending and time.monotonic() < deadline:
            for document_id in tuple(pending):
                _, _, headers = _request_identity(access_token, suffix="reconcile")
                try:
                    response = client.get(f"/documents/{document_id}", headers=headers)
                    if response.status_code != 200:
                        continue
                    payload = response.json()
                    document = payload.get("document", {})
                    status = document.get("status") if isinstance(document, dict) else None
                    if isinstance(status, str):
                        states[document_id] = status
                        if status not in pending_states:
                            pending.remove(document_id)
                except (httpx.HTTPError, ValueError):
                    continue
            if pending:
                _wait_until(min(deadline, time.monotonic() + poll_interval_seconds))
    return states


def _read_invoices(client: httpx.Client, access_token: str, user_index: int) -> RequestSample:
    request_id, trace_id, headers = _request_identity(access_token, suffix=f"u{user_index}")
    started_at = _now()
    started = time.perf_counter()
    try:
        response = client.get(
            "/invoices",
            params={"page": 1, "page_size": 10, "sort": "updated"},
            headers=headers,
        )
        return RequestSample(
            operation="read_invoices",
            started_at=started_at,
            duration_ms=(time.perf_counter() - started) * 1_000,
            status_code=response.status_code,
            expected_statuses=(200,),
            request_id=request_id,
            trace_id=trace_id,
        )
    except httpx.HTTPError as exc:
        return _transport_failure("read_invoices", started_at, started, request_id, trace_id, exc)


def _upload_document(
    client: httpx.Client, access_token: str, run_id: str, upload_index: int
) -> RequestSample:
    request_id, trace_id, headers = _request_identity(access_token)
    started_at = _now()
    started = time.perf_counter()
    try:
        filename = f"synthetic-{run_id}-{upload_index:04d}.pdf"
        response = client.post(
            "/documents/upload",
            headers=headers,
            files={"file": (filename, _synthetic_pdf(run_id, upload_index), "application/pdf")},
        )
        document_id = None
        if response.status_code == 200:
            try:
                payload = response.json()
                document = payload.get("document", {})
                if isinstance(document, dict) and document.get("id") is not None:
                    document_id = str(document["id"])
            except ValueError:
                document_id = None
        return RequestSample(
            operation="upload_document",
            started_at=started_at,
            duration_ms=(time.perf_counter() - started) * 1_000,
            status_code=response.status_code,
            expected_statuses=(200,),
            request_id=request_id,
            trace_id=trace_id,
            document_id=document_id,
        )
    except httpx.HTTPError as exc:
        return _transport_failure("upload_document", started_at, started, request_id, trace_id, exc)


def _transport_failure(
    operation: str,
    started_at: str,
    started: float,
    request_id: str,
    trace_id: str,
    error: Exception,
) -> RequestSample:
    return RequestSample(
        operation=operation,
        started_at=started_at,
        duration_ms=(time.perf_counter() - started) * 1_000,
        status_code=None,
        expected_statuses=(200,),
        request_id=request_id,
        trace_id=trace_id,
        error=type(error).__name__,
    )


def _request_identity(
    access_token: str, *, suffix: str | None = None
) -> tuple[str, str, dict[str, str]]:
    request_id = f"pv-{uuid4().hex}"
    if suffix:
        request_id = f"{request_id}-{suffix}"
    trace_id = uuid4().hex
    parent_id = uuid4().hex[:16]
    return (
        request_id,
        trace_id,
        {
            "X-Access-Token": access_token,
            "X-Request-ID": request_id,
            "traceparent": f"00-{trace_id}-{parent_id}-01",
        },
    )


def _synthetic_pdf(run_id: str, upload_index: int) -> bytes:
    marker = f"Production validation {run_id} item {upload_index}"
    return (
        "%PDF-1.4\n"
        "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
        f"% {marker}\n"
        "trailer<</Root 1 0 R>>\n%%EOF\n"
    ).encode("ascii")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a paced production-validation workload.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--target-label", default="local-rehearsal")
    parser.add_argument("--profile", choices=("local-rehearsal", "pg01"), default="local-rehearsal")
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--read-users", type=int, default=2)
    parser.add_argument("--read-interval-seconds", type=float, default=6.0)
    parser.add_argument("--upload-rate-per-minute", type=float, default=2.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--settle-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--settle-poll-seconds", type=float, default=2.0)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "_local_docs" / "azure" / "production-validation",
    )
    parser.add_argument(
        "--confirm-synthetic-target",
        action="store_true",
        help="Confirm that the target may receive synthetic PDF uploads.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    parsed_url = urlparse(args.base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise SystemExit("--base-url must be an absolute HTTP(S) URL.")
    if not args.confirm_synthetic_target:
        raise SystemExit("Pass --confirm-synthetic-target after verifying the target is safe.")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.target_label):
        raise SystemExit("--target-label must contain only lowercase letters, digits, or hyphens.")
    if args.duration_seconds <= 0 or args.read_users <= 0:
        raise SystemExit("Duration and read-user count must be greater than zero.")
    if args.read_interval_seconds <= 0 or args.upload_rate_per_minute <= 0:
        raise SystemExit("Read interval and upload rate must be greater than zero.")
    if args.request_timeout_seconds <= 0:
        raise SystemExit("Request timeout must be greater than zero.")
    if args.settle_timeout_seconds <= 0 or args.settle_poll_seconds <= 0:
        raise SystemExit("Settle timeout and poll interval must be greater than zero.")
    if args.profile == "pg01":
        violations = []
        if args.duration_seconds < 3_600:
            violations.append("duration must be at least 3600 seconds")
        if args.read_users != 10:
            violations.append("read users must equal 10")
        if args.read_interval_seconds > 6:
            violations.append("read interval must be at most 6 seconds")
        if args.upload_rate_per_minute < 2:
            violations.append("upload rate must be at least 2 per minute")
        if violations:
            raise SystemExit("PG-01 profile invalid: " + "; ".join(violations))


def _wait_until(target: float) -> None:
    remaining = target - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def _run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"pg01-{timestamp}-{uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _source_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _workspace_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.returncode != 0 or bool(result.stdout.strip())


def _duration_check(*, observed_seconds: float, expected_seconds: float) -> CheckResult:
    minimum = max(0.0, expected_seconds - 0.25)
    return CheckResult(
        code="workload_duration_achieved",
        passed=observed_seconds >= minimum,
        expected=f">= {minimum:.3f} seconds",
        observed=f"{observed_seconds:.3f} seconds",
        detail="The scheduled workload must remain active for the requested duration.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
