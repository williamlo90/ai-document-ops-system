from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.benchmark.models import EvaluationDataset  # noqa: E402
from app.benchmark.service import invoice_data_to_fields  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.evaluation.external_holdout import build_external_evaluation_summary  # noqa: E402
from app.evaluation.provider_costs import build_provider_economics  # noqa: E402
from app.providers.contracts import DocumentSource, ProviderError, ProviderUsage  # noqa: E402
from app.providers.factory import build_extractor_provider, build_parser_provider  # noqa: E402
from app.providers.llm_json import (  # noqa: E402
    EXTRACTION_PROMPT_VERSION,
    extraction_prompt_sha256,
)
from app.validation.invoice import validate_invoice  # noqa: E402


def main() -> None:
    args = _arguments()
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    pack_root = args.pack_root.resolve()
    _ensure_private_pack(pack_root)
    seal_verified = _verify_holdout_seal(pack_root) if args.split == "holdout" else None
    dataset_root = pack_root / args.split
    dataset = _filter_diagnostic_dataset(
        load_evaluation_dataset(dataset_root),
        args.document_ids,
        args.split,
    )
    settings = load_settings()
    _validate_real_provider_settings(settings)
    parser = build_parser_provider(settings)
    extractor = build_extractor_provider(settings)
    cached = _load_cached_observations(args.resume_private_result, args.split)

    observations = []
    reused_count = 0
    fresh_count = 0
    total = len(dataset.documents)
    for index, document in enumerate(dataset.documents, start=1):
        cached_observation = cached.get(document.document_id)
        if cached_observation and not cached_observation.get("error"):
            observations.append(cached_observation)
            reused_count += 1
            print(f"Reused {index}/{total} ({args.split})", flush=True)
            continue
        if fresh_count > 0 and args.rate_limit_seconds > 0:
            time.sleep(args.rate_limit_seconds)
        observations.append(
            _run_document(
                document.document_id,
                document.source_path,
                parser,
                extractor,
                max_attempts=args.max_attempts,
                retry_backoff_seconds=args.retry_backoff_seconds,
            )
        )
        fresh_count += 1
        print(f"Processed {index}/{total} ({args.split})", flush=True)

    provider_name = f"{parser.provider_name}+{extractor.provider_name}"
    expected_records = records_from_dataset(dataset)
    summary = build_external_evaluation_summary(
        expected_records,
        observations,
        split=args.split,
        provider=provider_name,
    )
    summary["experiment"] = _experiment_manifest(
        run_id=run_id,
        started_at=started_at,
        dataset_root=dataset_root,
        settings=settings,
        args=args,
        parser_name=parser.provider_name,
        extractor_name=extractor.provider_name,
    )
    summary["provider_economics"] = build_provider_economics(
        observations,
        parser_model=settings.mistral_ocr_model,
        extractor_model=settings.extractor_model,
    )
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    summary["holdout_seal_verified"] = seal_verified
    summary["execution"] = {
        "fresh_documents": fresh_count,
        "reused_successful_diagnostic_documents": reused_count,
    }

    detailed_path = pack_root / "evaluation_runs" / f"{args.split}_{run_id}_private.json"
    _write_json(
        detailed_path,
        {
            "classification": "private provider output; do not commit",
            "summary": summary,
            "observations": observations,
        },
    )
    _write_json(args.sanitized_output.resolve(), summary)
    _append_experiment_index(
        pack_root / "evaluation_runs" / "experiment_index.jsonl",
        summary,
        detailed_path,
    )
    print(f"Private detailed result: {detailed_path}")
    print(f"Sanitized aggregate result: {args.sanitized_output.resolve()}")
    print(
        "Field accuracy={:.2%}; validation exact={:.2%}; blocker accuracy={:.2%}; "
        "source evidence={:.2%}".format(
            summary["metrics"]["field_accuracy"],
            summary["metrics"]["validation_code_exact_match_rate"],
            summary["metrics"]["approval_blocker_accuracy"],
            summary["metrics"]["source_evidence_coverage"],
        )
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real providers on a private diagnostic or sealed holdout split."
    )
    parser.add_argument("pack_root", type=Path)
    parser.add_argument("sanitized_output", type=Path)
    parser.add_argument("--split", choices=("diagnostic", "holdout"), required=True)
    parser.add_argument("--rate-limit-seconds", type=float, default=5.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=10.0)
    parser.add_argument("--resume-private-result", type=Path)
    parser.add_argument(
        "--document-id",
        dest="document_ids",
        action="append",
        help="Run only this diagnostic document ID. Repeat to select more than one.",
    )
    return parser.parse_args()


def _filter_diagnostic_dataset(
    dataset: EvaluationDataset,
    document_ids: list[str] | None,
    split: str,
) -> EvaluationDataset:
    if not document_ids:
        return dataset
    if split == "holdout":
        raise SystemExit("ERROR: sealed holdout runs cannot select individual documents.")
    selected_ids = set(document_ids)
    selected = tuple(
        document for document in dataset.documents if document.document_id in selected_ids
    )
    found_ids = {document.document_id for document in selected}
    missing = sorted(selected_ids - found_ids)
    if missing:
        raise SystemExit(f"ERROR: unknown diagnostic document IDs: {', '.join(missing)}")
    return EvaluationDataset(
        name=f"{dataset.name}-subset",
        documents=selected,
        root_path=dataset.root_path,
    )


def _ensure_private_pack(pack_root: Path) -> None:
    if _is_relative_to(pack_root, ROOT):
        raise SystemExit("ERROR: private pack must be outside the repository.")
    required = (
        pack_root / "private_manifest.json",
        pack_root / "diagnostic" / "expected.json",
        pack_root / "holdout" / "expected.json",
        pack_root / "holdout_seal.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"ERROR: incomplete private pack: {', '.join(missing)}")


def _validate_real_provider_settings(settings: Any) -> None:
    if not settings.mistral_api_key:
        raise SystemExit("ERROR: MISTRAL_API_KEY is not configured.")
    if not settings.extractor_api_key or not settings.extractor_endpoint:
        raise SystemExit("ERROR: EXTRACTOR_API_KEY or EXTRACTOR_ENDPOINT is not configured.")
    if settings.parser_provider.strip().lower() == "mock":
        raise SystemExit("ERROR: PARSER_PROVIDER must use a real provider.")
    if settings.extractor_provider.strip().lower() == "mock":
        raise SystemExit("ERROR: EXTRACTOR_PROVIDER must use a real provider.")


def _load_cached_observations(path: Path | None, split: str) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    if split == "holdout":
        raise SystemExit("ERROR: sealed holdout runs cannot reuse cached observations.")
    resolved = path.resolve()
    if _is_relative_to(resolved, ROOT):
        raise SystemExit("ERROR: diagnostic cache must remain outside the repository.")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    observations = data.get("observations")
    if not isinstance(observations, list):
        raise SystemExit("ERROR: resume result does not contain private observations.")
    return {
        str(item["document_id"]): item
        for item in observations
        if isinstance(item, dict) and item.get("document_id")
    }


def _run_document(
    document_id: str,
    source_path: Path | None,
    parser: Any,
    extractor: Any,
    *,
    max_attempts: int,
    retry_backoff_seconds: float,
) -> dict[str, Any]:
    if source_path is None:
        raise ValueError(f"Private evaluation document has no source file: {document_id}")
    source = DocumentSource(
        storage_key=document_id,
        path=source_path,
        original_filename=source_path.name,
        content_type="application/pdf",
    )
    started = time.perf_counter()
    parsed_text = ""
    predicted_fields: dict[str, Any] = {}
    predicted_validation_codes: list[str] = []
    confidence_fields: list[str] = []
    evidence_fields: list[str] = []
    evidence: list[dict[str, Any]] = []
    provider_attempts: list[dict[str, Any]] = []
    error: str | None = None
    trace_id: str | None = None

    for attempt in range(1, max(1, max_attempts) + 1):
        stage = "parser"
        try:
            parsed = parser.parse(source)
            provider_attempts.append(
                _provider_attempt(
                    attempt, stage, parsed.provider_name, parsed.provider_model, parsed.usage
                )
            )
            parsed_text = parsed.text
            trace_id = parsed.provider_trace_id
            if not parsed.text:
                raise ProviderError("empty_parsed_text", parser.provider_name)
            stage = "extractor"
            result = extractor.extract_invoice(parsed)
            provider_attempts.append(
                _provider_attempt(
                    attempt,
                    stage,
                    result.provider_name,
                    result.provider_model,
                    result.usage,
                )
            )
            trace_id = result.provider_trace_id or trace_id
            stage = "postprocess"
            invoice = result.extraction.data
            error = None
            predicted_fields = invoice_data_to_fields(invoice)
            predicted_validation_codes = sorted(
                {issue.code for issue in validate_invoice(invoice).issues}
            )
            for item in result.extraction.confidence:
                if item.field_name not in confidence_fields:
                    confidence_fields.append(item.field_name)
                if (
                    item.source_page is not None
                    and item.source_text
                    and _evidence_exists(parsed, item.source_page, item.source_text)
                ):
                    evidence_fields.append(item.field_name)
                evidence.append(
                    {
                        "field_name": item.field_name,
                        "score": str(item.score) if item.score is not None else None,
                        "source_page": item.source_page,
                        "source_text": item.source_text,
                    }
                )
            break
        except ProviderError as exc:
            error = str(exc)
            provider_attempts.append(
                _failed_provider_attempt(attempt, stage, exc.provider_name, error)
            )
            if not exc.retryable or attempt >= max(1, max_attempts):
                break
            time.sleep(max(0.0, retry_backoff_seconds) * (2 ** (attempt - 1)))
        except Exception:
            error = f"provider_failed:{parser.provider_name}+{extractor.provider_name}"
            provider_attempts.append(
                _failed_provider_attempt(attempt, stage, "evaluation_pipeline", error)
            )
            break

    return {
        "document_id": document_id,
        "predicted_fields": predicted_fields,
        "predicted_validation_codes": predicted_validation_codes,
        "confidence_fields": sorted(set(confidence_fields)),
        "evidence_fields": sorted(set(evidence_fields)),
        "field_evidence": evidence,
        "parsed_text": parsed_text,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "provider_attempts": provider_attempts,
        "error": error,
        "trace_id": trace_id,
    }


def _provider_attempt(
    attempt: int,
    stage: str,
    provider: str,
    model: str | None,
    usage: ProviderUsage,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "stage": stage,
        "status": "succeeded",
        "provider": provider,
        "model": model,
        "usage": asdict(usage),
    }


def _failed_provider_attempt(
    attempt: int,
    stage: str,
    provider: str,
    error: str,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "stage": stage,
        "status": "failed",
        "provider": provider,
        "error": error,
    }


def _experiment_manifest(
    *,
    run_id: str,
    started_at: datetime,
    dataset_root: Path,
    settings: Any,
    args: argparse.Namespace,
    parser_name: str,
    extractor_name: str,
) -> dict[str, Any]:
    return {
        "experiment_id": run_id,
        "started_at": started_at.isoformat(),
        "dataset_fingerprint_sha256": _directory_fingerprint(dataset_root),
        "code": _code_state(),
        "providers": {
            "parser": {
                "name": parser_name,
                "requested_model": settings.mistral_ocr_model,
                "endpoint_host": urlparse(settings.mistral_ocr_endpoint).hostname,
            },
            "extractor": {
                "name": extractor_name,
                "requested_model": settings.extractor_model,
                "endpoint_host": urlparse(settings.extractor_endpoint).hostname,
                "prompt_version": EXTRACTION_PROMPT_VERSION,
                "prompt_sha256": extraction_prompt_sha256(),
            },
        },
        "execution_policy": {
            "rate_limit_seconds": args.rate_limit_seconds,
            "max_attempts": args.max_attempts,
            "retry_backoff_seconds": args.retry_backoff_seconds,
            "diagnostic_cache_reused": args.resume_private_result is not None,
            "selected_document_ids": sorted(args.document_ids or []),
        },
    }


def _code_state() -> dict[str, Any]:
    revision = _git_output("rev-parse", "HEAD")
    status = _git_output("status", "--porcelain")
    critical_paths = (
        ROOT / "backend" / "app" / "providers" / "llm_json.py",
        ROOT / "backend" / "app" / "providers" / "mistral.py",
        ROOT / "backend" / "app" / "evaluation" / "external_holdout.py",
        ROOT / "backend" / "app" / "evaluation" / "provider_costs.py",
        Path(__file__),
    )
    return {
        "git_commit": revision or None,
        "worktree_dirty": bool(status),
        "critical_code_sha256": _files_fingerprint(critical_paths),
    }


def _git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _directory_fingerprint(path: Path) -> str:
    return _files_fingerprint(tuple(item for item in path.rglob("*") if item.is_file()), root=path)


def _files_fingerprint(paths: tuple[Path, ...], root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(
            str(path.relative_to(root) if _is_relative_to(path, root) else path.name).encode()
        )
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _append_experiment_index(path: Path, summary: dict[str, Any], detailed_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "classification": "private experiment index; do not commit",
        "experiment": summary["experiment"],
        "split": summary["split"],
        "provider": summary["provider"],
        "metrics": summary["metrics"],
        "provider_economics": summary["provider_economics"],
        "private_result": detailed_path.name,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _evidence_exists(parsed: Any, page_number: int, source_text: str) -> bool:
    if parsed.pages:
        page = next((item for item in parsed.pages if item.page_number == page_number), None)
        return bool(page and source_text in page.text)
    return page_number == 1 and source_text in parsed.text


def _verify_holdout_seal(pack_root: Path) -> bool:
    seal = json.loads((pack_root / "holdout_seal.json").read_text(encoding="utf-8"))
    holdout = pack_root / "holdout"
    if _digest(holdout / "expected.json") != seal.get("expected_json_sha256"):
        raise SystemExit("ERROR: holdout expected.json changed after sealing.")
    for document in seal.get("documents") or []:
        path = holdout / "documents" / str(document["name"])
        if not path.is_file() or _digest(path) != document.get("sha256"):
            raise SystemExit(f"ERROR: holdout document changed after sealing: {path.name}")
    return True


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
