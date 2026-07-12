from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import load_settings  # noqa: E402
from app.providers.factory import build_extractor_provider, build_parser_provider  # noqa: E402
from app.providers.contracts import DocumentSource  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402


def main() -> None:
    if len(sys.argv) not in {1, 2}:
        raise SystemExit("Usage: python scripts/smoke_providers.py [path/to/invoice.pdf]")

    settings = load_settings()

    if not settings.mistral_api_key:
        print("SKIP: MISTRAL_API_KEY is not configured. Set it in .env to test real OCR.")
        sys.exit(_skip_exit_code())

    if not settings.extractor_api_key or not settings.extractor_endpoint:
        print(
            "SKIP: EXTRACTOR_API_KEY or EXTRACTOR_ENDPOINT is not configured. Set them in .env to test real LLM extraction."
        )
        sys.exit(_skip_exit_code())

    pdf_path = Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT / "sample_invoice.pdf"
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    parser = build_parser_provider(settings)
    extractor = build_extractor_provider(settings)

    print(f"Parsing {pdf_path} with {parser.provider_name} ...")
    source = DocumentSource(
        storage_key="smoke-test",
        path=pdf_path,
        original_filename=pdf_path.name,
        content_type="application/pdf",
    )
    parsed = parser.parse(source)
    print(f"  pages={len(parsed.pages)}, text_length={len(parsed.text)}")
    print(f"  trace_id={parsed.provider_trace_id}")

    print(f"Extracting with {extractor.provider_name} ...")
    result = extractor.extract_invoice(parsed)
    print(f"  provider={result.provider_name}, trace_id={result.provider_trace_id}")
    validation = validate_invoice(result.extraction.data)
    print(f"  validation_errors={len(validation.issues)}")

    print()
    print(json.dumps(_exportable(result, validation), indent=2))
    if validation.has_errors:
        raise SystemExit(1)


def _skip_exit_code() -> int:
    return 1 if os.environ.get("RUN_REAL_PROVIDER_SMOKE") == "1" else 0


def _exportable(result, validation) -> dict:
    d = result.extraction.data
    return {
        "provider": result.provider_name,
        "trace_id": result.provider_trace_id,
        "invoice": {
            "vendor_name": d.vendor_name,
            "invoice_number": d.invoice_number,
            "invoice_date": str(d.invoice_date) if d.invoice_date else None,
            "due_date": str(d.due_date) if d.due_date else None,
            "subtotal": str(d.subtotal) if d.subtotal else None,
            "tax": str(d.tax) if d.tax else None,
            "total": str(d.total) if d.total else None,
            "currency": d.currency,
            "line_items": [
                {
                    "description": li.description,
                    "quantity": str(li.quantity) if li.quantity else None,
                    "unit_price": str(li.unit_price) if li.unit_price else None,
                    "amount": str(li.amount) if li.amount else None,
                }
                for li in d.line_items
            ],
        },
        "field_confidence": [
            {"field": fc.field_name, "score": str(fc.score)} for fc in result.extraction.confidence
        ],
        "validation_issues": [
            {
                "field": issue.field_name,
                "severity": issue.severity.value,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in validation.issues
        ],
    }


if __name__ == "__main__":
    main()
