from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import load_settings  # noqa: E402
from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.benchmark.models import EvaluationDataset  # noqa: E402
from app.benchmark.report import generate_json_report  # noqa: E402
from app.benchmark.service import run_dataset  # noqa: E402
from app.providers.factory import build_extractor_provider, build_parser_provider  # noqa: E402


DEFAULT_DATASET = ROOT / "examples" / "benchmark" / "datasets" / "pdf_sample"


def main() -> None:
    args = _arguments()
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
    dataset = _limited_dataset(
        load_evaluation_dataset(args.dataset),
        settings.benchmark_real_provider_max_documents,
    )
    run = run_dataset(
        dataset,
        parser,
        extractor,
        rate_limit_s=args.rate_limit_seconds,
    )
    predicted_records = [
        {"document_id": result.document_id, **result.predicted_fields} for result in run.results
    ]

    _write_json(args.output_predicted_json, predicted_records)
    if args.report:
        report = generate_json_report(run, records_from_dataset(dataset), verbose=True)
        _write_json(args.report, report)

    errors = [result for result in run.results if result.error]
    print(
        f"Processed {len(run.results)} document(s) from {dataset.name}; "
        f"provider_errors={len(errors)}"
    )
    print(f"Predictions: {args.output_predicted_json}")
    if args.report:
        print(f"Report: {args.report}")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run configured real providers on a safe dataset.")
    parser.add_argument("output_predicted_json", type=Path)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--rate-limit-seconds", type=float, default=0.2)
    return parser.parse_args()


def _limited_dataset(dataset: EvaluationDataset, maximum: int) -> EvaluationDataset:
    if maximum <= 0:
        raise SystemExit("ERROR: BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS must be greater than zero.")
    documents = dataset.documents[:maximum]
    if len(documents) < len(dataset.documents):
        print(
            f"Safety limit: processing {len(documents)} of {len(dataset.documents)} documents. "
            "Raise BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS explicitly to run more."
        )
    return EvaluationDataset(
        name=dataset.name,
        documents=documents,
        root_path=dataset.root_path,
    )


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
