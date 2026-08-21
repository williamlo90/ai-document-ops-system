from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    alias: str
    source_document_id: str
    source_file: Path
    supplier_name: str | None
    supplier_country: str | None
    currency: str
    tax_rate: Decimal
    erp_outcome: str


@dataclass(frozen=True)
class BenchmarkDataset:
    dataset_id: str
    fingerprint: str
    default_item_code: str
    default_item_name: str
    base_currency: str
    exchange_rates: tuple[dict[str, str], ...]
    cases: tuple[BenchmarkCase, ...]

    @property
    def suppliers(self) -> tuple[tuple[str, str, str], ...]:
        rows = {
            (case.supplier_name, case.supplier_country, case.currency)
            for case in self.cases
            if case.supplier_name and case.supplier_country
        }
        return tuple(sorted(rows))


def load_benchmark_dataset(root: Path, manifest_path: Path) -> BenchmarkDataset:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require_mapping(raw, "benchmark manifest")
    expected_records = _load_expected_records(root)

    cases: list[BenchmarkCase] = []
    fingerprint = hashlib.sha256()
    for raw_case in raw.get("cases", []):
        _require_mapping(raw_case, "benchmark case")
        source_file = root / str(raw_case["source_file"])
        if not source_file.is_file():
            raise ValueError(f"Benchmark source file is missing: {source_file}")
        source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
        if source_hash != raw_case["source_sha256"]:
            raise ValueError(f"Benchmark source hash mismatch for {raw_case['case_id']}.")

        alias = str(raw_case["alias"])
        fingerprint.update(alias.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(source_file.read_bytes())
        fingerprint.update(b"\0")

        source_id = str(raw_case["source_document_id"])
        expected = expected_records.get(source_id)
        if expected is None:
            raise ValueError(f"Ground truth is missing for {source_id}.")
        _verify_case_against_ground_truth(raw_case, expected)

        cases.append(
            BenchmarkCase(
                case_id=str(raw_case["case_id"]),
                alias=alias,
                source_document_id=source_id,
                source_file=source_file,
                supplier_name=_optional_string(raw_case.get("supplier_name")),
                supplier_country=_optional_string(raw_case.get("supplier_country")),
                currency=str(raw_case["currency"]),
                tax_rate=Decimal(str(raw_case["tax_rate"])),
                erp_outcome=str(raw_case["erp_outcome"]),
            )
        )

    actual_fingerprint = fingerprint.hexdigest()
    if actual_fingerprint != raw["dataset_fingerprint_sha256"]:
        raise ValueError("Benchmark dataset fingerprint does not match the locked manifest.")
    if [case.case_id for case in cases] != [f"T{index:02d}" for index in range(1, 11)]:
        raise ValueError("Benchmark manifest must contain T01 through T10 in order.")

    return BenchmarkDataset(
        dataset_id=str(raw["dataset_id"]),
        fingerprint=actual_fingerprint,
        default_item_code=str(raw["default_item_code"]),
        default_item_name=str(raw["default_item_name"]),
        base_currency=str(raw["base_currency"]),
        exchange_rates=tuple(raw.get("fixed_exchange_rates", [])),
        cases=tuple(cases),
    )


def _load_expected_records(root: Path) -> dict[str, dict[str, Any]]:
    expected_path = root / "examples/benchmark/datasets/invoice_scenarios_v1/expected.json"
    raw = json.loads(expected_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Invoice scenario ground truth must be a list.")
    return {str(row["document_id"]): row for row in raw if isinstance(row, dict)}


def _verify_case_against_ground_truth(case: dict[str, Any], expected: dict[str, Any]) -> None:
    comparisons = {
        "supplier_name": expected.get("vendor_name"),
        "currency": expected.get("currency"),
    }
    for field, expected_value in comparisons.items():
        if case.get(field) != expected_value:
            raise ValueError(f"Manifest {field} does not match ground truth for {case['case_id']}.")

    subtotal = Decimal(str(expected["subtotal"]))
    tax = Decimal(str(expected["tax"]))
    expected_rate = Decimal("0") if subtotal == 0 else (tax / subtotal * 100)
    if Decimal(str(case["tax_rate"])) != expected_rate:
        raise ValueError(f"Manifest tax rate does not match ground truth for {case['case_id']}.")


def _require_mapping(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None
