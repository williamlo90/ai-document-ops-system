"""One-pass bounded OCR.space and extractor evaluation on a sealed Phase 6 cohort."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.benchmark.service import invoice_data_to_fields  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.evaluation.external_holdout import build_external_evaluation_summary  # noqa: E402
from app.providers.contracts import DocumentSource, ProviderError  # noqa: E402
from app.providers.factory import build_extractor_provider, build_parser_provider  # noqa: E402
from app.providers.llm_json import extraction_prompt_sha256  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402


MAX_INPUT_BYTES = 20_000
MAX_OUTPUT_TOKENS = 2048
MAX_OCR_ATTEMPTS = 2
MAX_EXTRACTOR_ATTEMPTS = 2
MAX_QUOTA_WAIT_SECONDS = 3600
SOURCE_FILES = [
    "scripts/phase6_provider_run.py", "scripts/phase6_validate_pack.py",
    "backend/app/evaluation/invoice.py", "backend/app/evaluation/line_items.py",
    "backend/app/evaluation/provenance.py", "backend/app/evaluation/external_holdout.py",
    "backend/app/providers/llm_json.py", "backend/app/providers/ocr_space.py",
]


def config_fingerprint(settings) -> str:
    credential_count = len(set(key for key in (settings.ocr_space_api_key, *settings.ocr_space_api_keys) if key))
    selected = {"parser_provider": settings.parser_provider, "extractor_provider": settings.extractor_provider,
                "parser_model": f"ocr-space-engine-{settings.ocr_space_engine}",
                "extractor_model": settings.extractor_model, "policy_mode": "ordered",
                "extractor_endpoint": settings.extractor_endpoint,
                "erpnext_base_url": settings.erpnext_base_url,
                "provider_timeout_seconds": settings.provider_timeout_seconds,
                "max_input_bytes": MAX_INPUT_BYTES, "max_output_tokens": MAX_OUTPUT_TOKENS,
                "automatic_ocr_retries": MAX_OCR_ATTEMPTS - 1,
                "ocr_credential_count": credential_count,
                "ocr_failover_policy": "ordered_per_key_cooldown_v1",
                "maximum_quota_wait_seconds": MAX_QUOTA_WAIT_SECONDS,
                "extractor_retries": MAX_EXTRACTOR_ATTEMPTS - 1,
                "extractor_transport_backoff_seconds": 5}
    return hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()


def bounded_post(post):
    def send(url, payload, headers):
        if len(json.dumps(payload.get("messages", [])).encode()) + 512 > MAX_INPUT_BYTES:
            raise ProviderError("phase6_input_limit", "llm_json")
        return post(url, {**payload, "max_completion_tokens": MAX_OUTPUT_TOKENS}, headers)
    return send


class RateAwareParser:
    """One bounded retry of the same PDF, only after an explicit 429 cooldown."""

    def __init__(self, provider, *, sleep=time.sleep):
        self.provider = provider
        self.provider_name = provider.provider_name
        self.sleep = sleep
        self.last_attempts = []

    def parse(self, source):
        self.last_attempts = []
        for index in range(MAX_OCR_ATTEMPTS):
            started = time.perf_counter()
            try:
                parsed = self.provider.parse(source)
                self.last_attempts.append({"attempt": index + 1, "status": "succeeded",
                    "credential_attempts": getattr(self.provider, "last_attempts", None),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
                return parsed
            except ProviderError as exc:
                attempt = {"attempt": index + 1, "status": "failed", "http_status": exc.http_status,
                           "credential_attempts": getattr(self.provider, "last_attempts", None),
                           "retry_after_seconds": exc.retry_after_seconds,
                           "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
                self.last_attempts.append(attempt)
                delay = exc.retry_after_seconds
                if (index + 1 >= MAX_OCR_ATTEMPTS or exc.http_status != 429 or delay is None
                        or not 0 < delay <= MAX_QUOTA_WAIT_SECONDS):
                    raise
                attempt["wait_before_retry_seconds"] = delay + 2
                remaining = delay + 2
                print(f"OCR quota cooldown: {remaining:.0f}s; one retry of the same PDF is scheduled", flush=True)
                while remaining > 0:
                    interval = min(30, remaining)
                    self.sleep(interval)
                    remaining -= interval
        raise RuntimeError("OCR retry policy exhausted")


def physical_ocr_attempts(stage):
    attempts = stage.get("attempts", [])
    if not attempts:
        return [{"status": stage["status"], "http_status": stage.get("http_status")}]
    return [physical for attempt in attempts for physical in
            (attempt["credential_attempts"] if attempt.get("credential_attempts") is not None else [attempt])]


class BoundedExtractor:
    """Retry a failed transport once; never retry an extracted answer or schema error."""

    def __init__(self, provider, *, sleep=time.sleep):
        self.provider = provider
        self.provider_name = provider.provider_name
        self.sleep = sleep
        self.last_attempts = []

    def extract_invoice(self, document):
        self.last_attempts = []
        for index in range(MAX_EXTRACTOR_ATTEMPTS):
            tick = time.perf_counter()
            try:
                result = self.provider.extract_invoice(document)
                self.last_attempts.append({"attempt": index + 1, "status": "succeeded",
                    "latency_ms": round((time.perf_counter() - tick) * 1000, 2)})
                return result
            except ProviderError as exc:
                attempt = {"attempt": index + 1, "status": "failed", "http_status": exc.http_status,
                    "error_code": str(exc), "latency_ms": round((time.perf_counter() - tick) * 1000, 2)}
                self.last_attempts.append(attempt)
                delay = exc.retry_after_seconds
                if (not exc.retryable or index + 1 >= MAX_EXTRACTOR_ATTEMPTS
                        or (exc.http_status == 429 and delay is None)
                        or (delay is not None and not 0 < delay <= MAX_QUOTA_WAIT_SECONDS)):
                    raise
                delay = max(5, delay or 0)
                attempt["wait_before_retry_seconds"] = delay
                remaining = delay
                while remaining > 0:
                    interval = min(30, remaining)
                    self.sleep(interval)
                    remaining -= interval
        raise RuntimeError("Extractor retry policy exhausted")


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(percentile / 100 * len(ordered)) - 1)], 2)


def latency_summary(observations: list[dict]) -> dict:
    names = ("ocr", "extraction", "validation", "total")
    result = {}
    for name in names:
        values = [event["latency_ms"] for row in observations for event in row.get("stages", [])
                  if event["stage"] == name and event["status"] == "succeeded"]
        result[name] = {"N": len(values), "p50_ms": _percentile(values, 50),
                        "p90_ms": _percentile(values, 90), "p95_ms": _percentile(values, 95)}
    return result


def attach_provenance(fields: dict, confidence: tuple) -> None:
    """Only grounded provider excerpts become evidence; missing anchors remain missing."""
    headers = {key: value for key, value in fields.items() if key != "line_items"}
    for item in confidence:
        if item.source_page is None or not item.source_text:
            continue
        name = item.field_name
        if name in headers:
            value = fields.get(name)
            excerpt = str(value) if value is not None and str(value) in item.source_text else item.source_text
            evidence = {"kind": "observed", "page": item.source_page, "excerpt": excerpt}
            fields.setdefault("provenance", {})[name] = evidence
            continue
        for index, row in enumerate(fields.get("line_items", [])):
            for prefix in (f"line_items[{index}].", f"line_items.{index}.",
                           f"lines.{row.get('line_id')}."):
                if name.startswith(prefix):
                    field = name[len(prefix):]
                    if field in {"description", "uom", "quantity", "unit_price", "amount"}:
                        value = row.get(field)
                        excerpt = str(value) if value is not None and str(value) in item.source_text else item.source_text
                        evidence = {"kind": "observed", "page": item.source_page, "excerpt": excerpt}
                        row.setdefault("provenance", {})[field] = evidence


def run_document(document, parser, extractor) -> dict:
    source = DocumentSource(document.document_id, document.source_path,
                            document.source_path.name, "application/pdf")
    row = {"document_id": document.document_id, "predicted_fields": {},
           "predicted_validation_codes": [], "validation_completed": False,
           "stages": [], "error": None}
    started = time.perf_counter()
    stage = "ocr"
    tick = time.perf_counter()
    try:
        parsed = parser.parse(source)
        row["source_pages"] = [{"page": page.page_number, "text": page.text} for page in parsed.pages]
        row["stages"].append({"stage": stage, "status": "succeeded",
                              "latency_ms": round((time.perf_counter() - tick) * 1000, 2),
                              "model": parsed.provider_model, "usage": asdict(parsed.usage),
                              "attempts": getattr(parser, "last_attempts", [])})
        stage = "extraction"
        tick = time.perf_counter()
        result = extractor.extract_invoice(parsed)
        row["stages"].append({"stage": stage, "status": "succeeded",
                              "latency_ms": round((time.perf_counter() - tick) * 1000, 2),
                              "model": result.provider_model, "usage": asdict(result.usage),
                              "attempts": getattr(extractor, "last_attempts", [])})
        stage = "validation"
        tick = time.perf_counter()
        fields = invoice_data_to_fields(result.extraction.data)
        attach_provenance(fields, result.extraction.confidence)
        validation = validate_invoice(result.extraction.data)
        row.update(predicted_fields=fields,
                   predicted_validation_codes=sorted({item.code for item in validation.issues}),
                   predicted_approval_blocked=validation.has_errors,
                   validation_completed=True,
                   confidence_fields=sorted({item.field_name for item in result.extraction.confidence}),
                   evidence_fields=sorted({item.field_name for item in result.extraction.confidence
                                           if item.source_page and item.source_text}))
        row["stages"].append({"stage": stage, "status": "succeeded",
                              "latency_ms": round((time.perf_counter() - tick) * 1000, 2)})
    except ProviderError as exc:
        code = str(exc) if re.fullmatch(r"[a-z0-9_]{1,80}", str(exc)) else "provider_error"
        row["error"] = f"{stage}:{exc.provider_name}:{code}"
        row["stages"].append({"stage": stage, "status": "failed",
                              "latency_ms": round((time.perf_counter() - tick) * 1000, 2),
                              "error_code": code, "retryable": exc.retryable,
                              "http_status": exc.http_status, "retry_after_seconds": exc.retry_after_seconds,
                              "attempts": getattr(parser if stage == "ocr" else extractor, "last_attempts", [])})
    except Exception as exc:
        row["error"] = f"{stage}:unexpected:{type(exc).__name__}"
        row["stages"].append({"stage": stage, "status": "failed",
                              "latency_ms": round((time.perf_counter() - tick) * 1000, 2),
                              "error_code": type(exc).__name__})
    row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    row["stages"].append({"stage": "total", "status": "succeeded" if not row["error"] else "failed",
                          "latency_ms": row["latency_ms"]})
    return row


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("pack", type=Path)
    command.add_argument("--split", choices=("development", "quality_holdout"), required=True)
    command.add_argument("--private-output", type=Path, required=True)
    command.add_argument("--aggregate-output", type=Path, required=True)
    command.add_argument("--rate-limit-seconds", type=float, default=5.0)
    command.add_argument("--max-documents", type=int, help="Development diagnostic only")
    args = command.parse_args()
    pack = args.pack.resolve()
    private = args.private_output.resolve()
    aggregate = args.aggregate_output.resolve()
    if args.rate_limit_seconds < 0 or private.exists() or aggregate.exists():
        raise SystemExit("Invalid delay or a result already exists; no automatic rerun")
    if args.max_documents is not None and (args.split != "development" or args.max_documents < 1):
        raise SystemExit("Only a development diagnostic may select a document subset")
    if ROOT not in private.parents or "_local_docs" not in private.parts:
        raise SystemExit("Detailed provider output must stay inside ignored _local_docs")
    check = audit(pack, require_sealed=args.split == "quality_holdout", inspect_pdf_text=False)
    settings = load_settings()
    if (settings.parser_provider != "ocr_space" or settings.extractor_provider != "llm_json"
            or urlparse(settings.extractor_endpoint).hostname != "api.openai.com"):
        raise SystemExit("Phase 6 provider run requires reviewed OCR.space and OpenAI endpoints")
    if not settings.ocr_space_api_key or not settings.extractor_api_key:
        raise SystemExit("Provider credentials missing")
    manifest = load_json(pack / "manifest.json")
    if args.split == "quality_holdout":
        freeze = manifest["freeze"]
        details = load_json(pack / "freeze-details.json")
        if (freeze["prompt_sha256"] != extraction_prompt_sha256()
                or freeze["config_sha256"] != config_fingerprint(settings)
                or any(file_digest(ROOT / path) != value
                       for path, value in details["source_hashes"].items())):
            raise SystemExit("Frozen prompt, configuration or evaluator source changed")
    dataset = load_evaluation_dataset(pack / args.split)
    if len(dataset.documents) != check["cohorts"][args.split]["invoices"]:
        raise SystemExit("Scheduled document count differs from sealed manifest")
    if args.max_documents is not None:
        dataset = replace(dataset, documents=dataset.documents[:args.max_documents])
    parser = RateAwareParser(build_parser_provider(settings))
    extractor = build_extractor_provider(settings)
    extractor = replace(extractor, post_json=bounded_post(extractor.post_json))
    extractor = BoundedExtractor(extractor)
    observations = []
    started_at = datetime.now(UTC).isoformat()
    write_json(private, {"status": "started", "started_at": started_at,
                         "scheduled": len(dataset.documents), "observations": observations})
    try:
        for index, document in enumerate(dataset.documents, start=1):
            if index > 1 and args.rate_limit_seconds:
                time.sleep(args.rate_limit_seconds)
            observations.append(run_document(document, parser, extractor))
            write_json(private, {"status": "running", "started_at": started_at,
                                 "scheduled": len(dataset.documents), "observations": observations})
            print(f"{index}/{len(dataset.documents)} completed; stage_error={bool(observations[-1]['error'])}", flush=True)
    finally:
        write_json(private, {"status": "completed" if len(observations) == len(dataset.documents) else "partial",
                             "started_at": started_at, "scheduled": len(dataset.documents),
                             "observations": observations})
    summary = build_external_evaluation_summary(records_from_dataset(dataset), observations,
        split=args.split, provider="ocr_space+llm_json",
        dataset_class="Phase 6 AI-assisted synthetic invoices")
    summary["scheduled_denominator"] = len(dataset.documents)
    summary["stage_latency_ms"] = latency_summary(observations)
    summary["provider_usage"] = {
        "ocr_calls": sum(any(stage["stage"] == "ocr" and stage["status"] == "succeeded"
                             for stage in row["stages"]) for row in observations),
        "extractor_calls": sum(any(stage["stage"] == "extraction" and stage["status"] == "succeeded"
                                   for stage in row["stages"]) for row in observations),
        "extractor_input_tokens": sum(stage.get("usage", {}).get("input_tokens") or 0
                                      for row in observations for stage in row["stages"]
                                      if stage["stage"] == "extraction"),
        "extractor_output_tokens": sum(stage.get("usage", {}).get("output_tokens") or 0
                                       for row in observations for stage in row["stages"]
                                       if stage["stage"] == "extraction"),
        "billed_cost_usd": None,
    }
    summary["run_status"] = "completed" if len(observations) == len(dataset.documents) else "partial"
    summary["started_at"] = started_at
    summary["completed_at"] = datetime.now(UTC).isoformat()
    summary["manifest_sha256"] = file_digest(pack / "manifest.json")
    write_json(aggregate, summary)
    print(json.dumps({"run_status": summary["run_status"], "scheduled": len(dataset.documents),
                      "provider_errors": summary["provider_errors"],
                      "whole_invoice_exact": summary["metrics"]["full_invoice_exact_match_rate"]}, indent=2))


if __name__ == "__main__":
    main()
