from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import load_settings  # noqa: E402
from app.providers.factory import build_extractor_provider, build_parser_provider  # noqa: E402
from app.providers.contracts import DocumentSource  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402


DOCUMENTS: list[dict[str, str]] = [
    {"document_id": "sample_invoice", "pdf_path": str(ROOT / "sample_invoice.pdf")},
]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/run_real_fixture_extraction.py <output_predicted_json>"
        )

    output_path = Path(sys.argv[1])

    settings = load_settings()

    if not settings.mistral_api_key:
        raise SystemExit(
            "ERROR: MISTRAL_API_KEY is not configured. Set it in .env to run real extraction."
        )

    if not settings.extractor_api_key or not settings.extractor_endpoint:
        raise SystemExit(
            "ERROR: EXTRACTOR_API_KEY or EXTRACTOR_ENDPOINT is not configured. Set them in .env to run real extraction."
        )

    if (
        settings.parser_provider.strip().lower() == "mock"
        or settings.extractor_provider.strip().lower() == "mock"
    ):
        raise SystemExit(
            "ERROR: Providers are set to 'mock' in settings. Set parser_provider and extractor_provider to real values."
        )

    parser = build_parser_provider(settings)
    extractor = build_extractor_provider(settings)

    results: list[dict] = []
    for doc in DOCUMENTS:
        pdf_path = Path(doc["pdf_path"])
        if not pdf_path.exists():
            print(f"WARNING: {pdf_path} not found, skipping {doc['document_id']}")
            continue

        source = DocumentSource(
            storage_key=doc["document_id"],
            path=pdf_path,
            original_filename=pdf_path.name,
            content_type="application/pdf",
        )
        parsed = parser.parse(source)
        extraction = extractor.extract_invoice(parsed)
        validation = validate_invoice(extraction.extraction.data)

        d = extraction.extraction.data
        record = {
            "document_id": doc["document_id"],
            "vendor_name": d.vendor_name,
            "invoice_number": d.invoice_number,
            "invoice_date": str(d.invoice_date) if d.invoice_date else None,
            "due_date": str(d.due_date) if d.due_date else None,
            "subtotal": str(d.subtotal) if d.subtotal else None,
            "tax": str(d.tax) if d.tax else None,
            "total": str(d.total) if d.total else None,
            "currency": d.currency,
        }
        results.append(record)

        print(f"Extracted {doc['document_id']}: validation_errors={len(validation.issues)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Written {len(results)} prediction(s) to {output_path}")


if __name__ == "__main__":
    main()
