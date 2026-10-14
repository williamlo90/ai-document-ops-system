"""One synthetic page, two provider calls maximum, no retries or ERP effects."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.benchmark.service import invoice_data_to_fields
from app.core.settings import load_settings
from app.evaluation.external_holdout import build_external_evaluation_summary
from app.providers.contracts import DocumentSource, ProviderError
from app.providers.factory import build_parser_provider, build_extractor_provider
from app.providers.llm_json import extraction_prompt_sha256
from app.validation.invoice import validate_invoice

OUTPUT = ROOT / "docs/evidence/invoice-review-v2/phase1-provider-configured-diagnostic.json"
DATASET = ROOT / "examples/benchmark/datasets/invoice_scenarios_v1"
MAX_INPUT_BYTES = 20000  # Conservative upper bound on input token count, including overhead.
MAX_OUTPUT_TOKENS = 2048
CEILING = 0.004 + MAX_INPUT_BYTES * 0.75 / 1e6 + MAX_OUTPUT_TOKENS * 4.5 / 1e6


def bounded_post(post):
    def send(url, payload, headers):
        size = len(json.dumps(payload["messages"]).encode()) + 512
        if size > MAX_INPUT_BYTES:
            raise ProviderError("diagnostic_input_budget_exceeded", "llm_json")
        return post(url, {**payload, "max_completion_tokens": MAX_OUTPUT_TOKENS}, headers)

    return send


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--execute", action="store_true")
    cli.add_argument("--output", type=Path, default=OUTPUT)
    args = cli.parse_args()
    output = args.output.resolve()
    config = load_settings()
    if config.extractor_model != "gpt-5.4-mini-2026-03-17":
        raise SystemExit("Unknown extractor pricing; diagnostic not run")
    settings = replace(
        config, mistral_ocr_model=config.mistral_ocr_model, provider_timeout_seconds=45
    )
    if settings.mistral_ocr_model not in {"mistral-ocr-latest", "mistral-ocr-4-1"}:
        raise SystemExit("Unknown OCR pricing; diagnostic not run")
    ocr_space = settings.parser_provider == "ocr_space"
    gemini = settings.parser_provider == "gemini_ocr"
    if settings.parser_provider not in {"mistral_ocr", "gemini_ocr", "ocr_space"}:
        raise SystemExit("Diagnostic requires a real parser")
    if gemini and settings.gemini_ocr_model not in {"gemini-3.8-flash", "gemini-3.5-flash-lite"}:
        raise SystemExit("Unreviewed Gemini model")
    parser_model = settings.gemini_ocr_model if gemini else settings.mistral_ocr_model
    parser_host = (
        "generativelanguage.googleapis.com"
        if gemini
        else urlparse(settings.mistral_ocr_endpoint).hostname
    )
    if ocr_space:
        parser_model, parser_host = "ocr-space-engine-2", "api.ocr.space"
    source = DATASET / "documents/standard_usd.pdf"
    expected = [json.loads((DATASET / "expected.json").read_text())[0]]
    preflight = {
        "checked_on": datetime.now(UTC).date().isoformat(),
        "documents": 1,
        "pages": 1,
        "max_calls": 2,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_input_token_upper_bound": MAX_INPUT_BYTES,
        "max_estimated_usd": CEILING + (0.10 if gemini else 0),
        "parser_billing_assumption": "Gemini free tier; paid-rate upper estimate also bounded"
        if gemini
        else ("OCR.space free endpoint" if ocr_space else "Mistral standard"),
        "budget_usd": 1,
        "automatic_retries": 0,
        "parser_model": parser_model,
        "extractor_model": settings.extractor_model,
        "pricing_sources": [
            "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
            "https://docs.mistral.ai/inference/pricing",
            "https://ai.google.dev/gemini-api/docs/pricing",
            "https://ocr.space/ocrapi",
        ],
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "prompt_sha256": extraction_prompt_sha256(),
        "parser_host": parser_host,
        "extractor_host": urlparse(settings.extractor_endpoint).hostname,
        "scope": "Existing synthetic service invoice: provider plumbing diagnostic, not goods/PO eligibility",
    }
    if not args.execute:
        print(json.dumps(preflight, indent=2))
        return
    if output.exists():
        raise SystemExit("Diagnostic artifact already exists; no automatic rerun")
    if (
        preflight["parser_host"]
        not in {"api.mistral.ai", "generativelanguage.googleapis.com", "api.ocr.space"}
        or preflight["extractor_host"] != "api.openai.com"
    ):
        raise SystemExit("Diagnostic restricted to reviewed official hosts")
    parser = build_parser_provider(settings)
    extractor = build_extractor_provider(settings)
    extractor = replace(extractor, post_json=bounded_post(extractor.post_json))
    report = {
        "preflight": preflight,
        "status": "started",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "source_hashes": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                *(ROOT / "backend/app/evaluation").glob("*.py"),
                ROOT / "backend/app/providers/llm_json.py",
                ROOT / "backend/app/providers/mistral.py",
                ROOT / "backend/app/providers/gemini.py",
                ROOT / "backend/app/providers/ocr_space.py",
            ]
        },
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    obs = {"document_id": expected[0]["document_id"], "predicted_fields": {}, "error": None}
    stages = []
    started = time.perf_counter()
    stage = "parser"
    tick = time.perf_counter()
    try:
        parsed = parser.parse(DocumentSource("phase1", source, source.name, "application/pdf"))
        stages.append(
            {
                "stage": stage,
                "status": "succeeded",
                "latency_ms": (time.perf_counter() - tick) * 1000,
                "model": parsed.provider_model,
                "usage": asdict(parsed.usage),
            }
        )
        stage = "extractor"
        tick = time.perf_counter()
        result = extractor.extract_invoice(parsed)
        stages.append(
            {
                "stage": stage,
                "status": "succeeded",
                "latency_ms": (time.perf_counter() - tick) * 1000,
                "model": result.provider_model,
                "usage": asdict(result.usage),
            }
        )
        fields = invoice_data_to_fields(result.extraction.data)
        validation = validate_invoice(result.extraction.data)
        obs.update(
            predicted_fields=fields,
            validation_completed=True,
            predicted_validation_codes=sorted({i.code for i in validation.issues}),
            predicted_approval_blocked=validation.has_errors,
            confidence_fields=[i.field_name for i in result.extraction.confidence],
            evidence_fields=[
                i.field_name
                for i in result.extraction.confidence
                if any(
                    p.page_number == i.source_page and i.source_text and i.source_text in p.text
                    for p in parsed.pages
                )
            ],
        )
    except ProviderError as exc:
        # No raw exception/response text, credential, or customer payload in artifacts.
        obs["error"] = "provider_or_budget_failure"
        error_detail = {}
        cause = exc.__cause__
        if hasattr(cause, "read"):
            try:
                body = json.loads(cause.read())
                body = body.get("error", body)
                error_detail = {
                    k: str(body[k])
                    .replace(settings.mistral_api_key or "[no-key]", "[redacted]")
                    .replace(settings.ocr_space_api_key or "[no-key]", "[redacted]")
                    .replace(settings.gemini_api_key or "[no-key]", "[redacted]")
                    .replace(settings.extractor_api_key or "[no-key]", "[redacted]")[:300]
                    for k in ("message", "type", "code")
                    if k in body
                }
            except (ValueError, OSError):
                pass
        stages.append(
            {
                "stage": stage,
                "status": "failed",
                "latency_ms": (time.perf_counter() - tick) * 1000,
                "error_type": type(exc).__name__,
                "http_status": getattr(exc.__cause__, "code", None),
                "error_detail": error_detail,
            }
        )
    obs["latency_ms"] = (time.perf_counter() - started) * 1000
    report.update(
        status="completed" if obs["error"] is None else "failed_diagnostic",
        stages=stages,
        report=build_external_evaluation_summary(
            expected,
            [obs],
            split="development_diagnostic",
            provider=f"{settings.parser_provider}+llm_json",
        ),
        limitations=[
            "One previously seen synthetic page, not sealed holdout.",
            "V1 source has no complete goods/UOM/provenance oracle: whole-invoice metric is N/A.",
            "Sample size one: stage latency is a single observation, not an SLO.",
            "Configured OCR alias used; provider-reported model recorded when available.",
        ],
    )
    cost = 0.0
    for event in stages:
        usage = event.get("usage", {})
        if event["status"] == "succeeded":
            if event["stage"] == "parser":
                if gemini:
                    cost += (usage.get("input_tokens") or 0) * (
                        0.30 if parser_model == "gemini-3.5-flash-lite" else 0.75
                    ) / 1e6 + (usage.get("output_tokens") or 0) * (
                        2.50 if parser_model == "gemini-3.5-flash-lite" else 3.75
                    ) / 1e6
                elif not ocr_space:
                    cost += (usage.get("pages_processed") or 1) * 0.004
            else:
                cost += (usage.get("input_tokens") or 0) * 0.75 / 1e6 + (
                    usage.get("output_tokens") or 0
                ) * 4.5 / 1e6
    report["cost_basis"] = (
        "Paid standard rate estimate; Gemini free tier may charge zero; not an invoice"
        if gemini
        else "Published standard rates"
    )
    report["estimated_usage_cost_usd"] = (
        cost if all(x["status"] == "succeeded" for x in stages) else None
    )
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "provider_calls": len(stages),
                "estimated_usd": report["estimated_usage_cost_usd"],
            }
        )
    )


if __name__ == "__main__":
    main()
