from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DATASET_ROOT = ROOT / "examples" / "benchmark" / "datasets" / "invoice_scenarios_v1"
sys.path.insert(0, str(BACKEND))

from app.api.dependencies import build_container  # noqa: E402
from app.core.security import SecurityContext  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.evaluation.dashboard import EvaluationRunIncomplete  # noqa: E402
from app.providers.llm_json import (  # noqa: E402
    EXTRACTION_PROMPT_VERSION,
    extraction_prompt_sha256,
)


def main() -> int:
    args = _arguments()
    status = _git("status", "--porcelain")
    if status and not args.allow_dirty:
        print(
            "ERROR: current-provider release evidence requires a clean worktree.", file=sys.stderr
        )
        return 2

    configured = load_settings()
    if not configured.mistral_api_key or not configured.extractor_api_key:
        print("ERROR: MISTRAL_API_KEY and EXTRACTOR_API_KEY must be configured.", file=sys.stderr)
        return 2
    if configured.parser_provider == "mock" or configured.extractor_provider == "mock":
        print(
            "ERROR: configure real parser and extractor providers before this run.", file=sys.stderr
        )
        return 2

    with tempfile.TemporaryDirectory() as temp_dir:
        settings = replace(
            configured,
            app_env="test",
            storage_backend="memory",
            document_storage_backend="local",
            upload_root=Path(temp_dir) / "uploads",
            benchmark_real_provider_max_documents=args.max_documents,
            malware_scanning_enabled=False,
        )
        container = build_container(settings)
        context = SecurityContext(
            actor="evaluation-release",
            is_admin=True,
            workspace_id=settings.workspace_id,
            user_id="evaluation-release",
            role="admin",
        )
        try:
            result = container.evaluation_dashboard.run(context=context)
        except EvaluationRunIncomplete as exc:
            failure_path = _failure_path(args.output)
            failure_report = _failure_report(exc, settings=settings, status=status)
            failure_path.parent.mkdir(parents=True, exist_ok=True)
            failure_path.write_text(
                json.dumps(failure_report, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"Current-provider diagnostic failed; safe record written to {failure_path}",
                file=sys.stderr,
            )
            return 1
        record = container.benchmark_history.get(UUID(str(result["run_id"])))

    report = dict(record.report)
    experiment = dict(report.get("experiment") or {})
    experiment.update(_experiment_metadata(settings=settings, status=status))
    report["experiment"] = experiment
    report["holdout_seal_verified"] = False
    report["release_status"] = "diagnostic_not_holdout"
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["limitations"] = list(report.get("limitations") or []) + [
        "This current-provider run is a diagnostic on a previously used synthetic set, not a blind holdout.",
        "A passing local run does not substitute for the manual credentialed CI workflow.",
        "Provider behavior and list-price estimates can change after this observation.",
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    metrics = report["metrics"]
    print(f"Current-provider diagnostic written to {args.output}")
    print(
        "documents={}; field_accuracy={:.2%}; validation_match={:.2%}; provider_errors={}".format(
            report["documents_count"],
            metrics["field_accuracy"],
            metrics["validation_code_exact_match_rate"],
            report["provider_errors"],
        )
    )
    return 0


def _failure_report(
    exc: EvaluationRunIncomplete,
    *,
    settings: Any,
    status: str,
) -> dict[str, Any]:
    attempt = exc.attempt
    return {
        "schema_version": "current_provider_attempt_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "release_status": "failed_diagnostic_not_holdout",
        "holdout_seal_verified": False,
        "attempt": {
            "id": str(attempt.id),
            "status": attempt.status.value,
            "documents_requested": attempt.documents_requested,
            "documents_processed": attempt.documents_processed,
            "provider_calls": attempt.provider_calls,
            "error_code": attempt.error_code,
            "started_at": attempt.started_at.isoformat(),
            "completed_at": (
                attempt.completed_at.isoformat() if attempt.completed_at is not None else None
            ),
        },
        "failures": list(exc.failures),
        "experiment": _experiment_metadata(settings=settings, status=status),
        "limitations": [
            "No partial quality result was promoted.",
            "The failure record excludes OCR text, prompts, provider responses, and invoice contents.",
            "This diagnostic used a previously seen synthetic set and is not a blind holdout.",
        ],
    }


def _experiment_metadata(*, settings: Any, status: str) -> dict[str, Any]:
    return {
        "release_kind": "current_provider_diagnostic",
        "source": {
            "git_commit": _git("rev-parse", "HEAD") or None,
            "git_branch": _git("branch", "--show-current") or None,
            "worktree_dirty": bool(status),
            "critical_code_sha256": _critical_code_fingerprint(),
        },
        "dataset_fingerprint_sha256": _directory_fingerprint(DATASET_ROOT),
        "providers": {
            "parser": {
                "name": settings.parser_provider,
                "requested_model": settings.mistral_ocr_model,
                "endpoint_host": urlparse(settings.mistral_ocr_endpoint).hostname,
            },
            "extractor": {
                "name": settings.extractor_provider,
                "requested_model": settings.extractor_model,
                "endpoint_host": urlparse(settings.extractor_endpoint).hostname,
                "prompt_version": EXTRACTION_PROMPT_VERSION,
                "prompt_sha256": extraction_prompt_sha256(),
            },
        },
    }


def _failure_path(output: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return output.with_name(f"{output.stem}.failed-{timestamp}{output.suffix}")


def _critical_code_fingerprint() -> str:
    paths = (
        ROOT / "backend" / "app" / "providers" / "llm_json.py",
        ROOT / "backend" / "app" / "providers" / "mistral.py",
        ROOT / "backend" / "app" / "evaluation" / "dashboard.py",
        ROOT / "backend" / "app" / "evaluation" / "external_holdout.py",
        ROOT / "backend" / "app" / "evaluation" / "provider_costs.py",
        Path(__file__),
    )
    return _files_fingerprint(paths)


def _directory_fingerprint(path: Path) -> str:
    return _files_fingerprint(tuple(item for item in path.rglob("*") if item.is_file()), root=path)


def _files_fingerprint(paths: tuple[Path, ...], root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        relative = path.relative_to(root) if _is_relative_to(path, root) else Path(path.name)
        digest.update(str(relative).replace("\\", "/").encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a reproducible diagnostic using the currently configured providers."
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-documents", type=int, default=20)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow a dirty diagnostic; never use this flag for release evidence.",
    )
    args = parser.parse_args()
    if args.max_documents < 1 or args.max_documents > 20:
        parser.error("--max-documents must be between 1 and 20")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
