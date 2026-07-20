from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import re
import sys
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.extraction.schemas import InvoiceData  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402


FATURA_ARCHIVE_MD5 = "a25c4f9292630f94774e0ca29d121e82"
FATURA_RECORD_URL = "https://zenodo.org/records/8261508"
PACK_VERSION = "external_invoice_holdout_v1"
DEFAULT_SEED = 20260715
DIAGNOSTIC_COUNT = 15
HOLDOUT_COUNT = 10
TRANSFORM_PROFILES = ("clean", "low_contrast", "soft_blur", "slight_skew", "compressed")


def main() -> None:
    args = _arguments()
    archive = args.archive.resolve()
    output = args.output.resolve()
    _validate_locations(archive, output)
    _verify_archive(archive)
    _prepare_empty_output(output)

    excluded_templates = _excluded_templates(args.exclude_manifest)
    cases = _select_cases(archive, args.seed, excluded_templates=excluded_templates)
    manifest_cases: list[dict[str, Any]] = []
    expected_by_split: dict[str, list[dict[str, Any]]] = {
        "diagnostic": [],
        "holdout": [],
    }

    with zipfile.ZipFile(archive) as source:
        for case in cases:
            expected, private_metadata = _materialize_case(source, output, case)
            expected_by_split[case["split"]].append(expected)
            manifest_cases.append(private_metadata)

    for split, records in expected_by_split.items():
        split_root = output / split
        _write_json(split_root / "expected.json", records)

    manifest = {
        "pack_version": args.pack_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": "FATURA",
            "record_url": FATURA_RECORD_URL,
            "license": "CC BY 4.0",
            "archive_name": archive.name,
            "archive_md5": _digest(archive, "md5"),
        },
        "classification": "private evaluation data; do not commit",
        "selection": {
            "seed": args.seed,
            "strategy": "one instance from each of 25 deterministically shuffled layouts",
            "diagnostic_count": DIAGNOSTIC_COUNT,
            "holdout_count": HOLDOUT_COUNT,
            "excluded_templates_count": len(excluded_templates),
            "exclusion_manifest_sha256": (
                _digest(args.exclude_manifest.resolve(), "sha256")
                if args.exclude_manifest is not None
                else None
            ),
        },
        "label_source": "FATURA Original_Format annotations normalized to invoice_v1",
        "cases": manifest_cases,
    }
    _write_json(output / "private_manifest.json", manifest)
    _write_holdout_seal(output)

    null_counts = Counter()
    for records in expected_by_split.values():
        for record in records:
            for field in _invoice_fields():
                if record[field] is None:
                    null_counts[field] += 1
    print(f"Prepared {len(cases)} private cases at {output}")
    print(f"Split: diagnostic={DIAGNOSTIC_COUNT}, holdout={HOLDOUT_COUNT}")
    print(f"Transform profiles: {', '.join(TRANSFORM_PROFILES)}")
    print(f"Explicitly absent annotated fields: {dict(sorted(null_counts.items()))}")
    print("Holdout sealed with SHA-256 checksums. Raw documents and labels remain private.")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a private, sealed 25-invoice FATURA evaluation pack."
    )
    parser.add_argument("archive", type=Path, help="Downloaded FATURA.zip archive")
    parser.add_argument("output", type=Path, help="Output directory outside the repository")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--pack-version", default=PACK_VERSION)
    parser.add_argument(
        "--exclude-manifest",
        type=Path,
        help="Private manifest whose source templates must not be selected again.",
    )
    return parser.parse_args()


def _validate_locations(archive: Path, output: Path) -> None:
    if not archive.is_file():
        raise SystemExit(f"ERROR: archive not found: {archive}")
    if _is_relative_to(output, ROOT):
        raise SystemExit("ERROR: private evaluation output must be outside the repository.")


def _prepare_empty_output(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"ERROR: output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)


def _verify_archive(archive: Path) -> None:
    actual = _digest(archive, "md5")
    if actual != FATURA_ARCHIVE_MD5:
        raise SystemExit(
            f"ERROR: FATURA archive checksum mismatch: expected {FATURA_ARCHIVE_MD5}, got {actual}"
        )


def _select_cases(
    archive: Path,
    seed: int,
    *,
    excluded_templates: set[int] | None = None,
) -> list[dict[str, Any]]:
    pattern = re.compile(r"/images/Template(?P<template>\d+)_Instance(?P<instance>\d+)\.jpg$")
    by_template: dict[int, list[tuple[int, str]]] = {}
    with zipfile.ZipFile(archive) as source:
        for member in source.namelist():
            match = pattern.search(member)
            if match is None:
                continue
            template = int(match.group("template"))
            instance = int(match.group("instance"))
            by_template.setdefault(template, []).append((instance, member))

    available_templates = set(by_template) - (excluded_templates or set())
    if len(available_templates) < DIAGNOSTIC_COUNT + HOLDOUT_COUNT:
        raise SystemExit("ERROR: source archive does not contain 25 distinct templates.")

    rng = random.Random(seed)
    templates = sorted(available_templates)
    rng.shuffle(templates)
    selected = []
    for index, template in enumerate(templates[: DIAGNOSTIC_COUNT + HOLDOUT_COUNT]):
        candidates = sorted(by_template[template])
        instance, image_member = candidates[rng.randrange(len(candidates))]
        split = "diagnostic" if index < DIAGNOSTIC_COUNT else "holdout"
        ordinal = index + 1 if split == "diagnostic" else index - DIAGNOSTIC_COUNT + 1
        selected.append(
            {
                "document_id": f"{split}-{ordinal:03d}",
                "split": split,
                "template": template,
                "instance": instance,
                "image_member": image_member,
                "annotation_member": (
                    "invoices_dataset_final/Annotations/Original_Format/"
                    f"Template{template}_Instance{instance}.json"
                ),
                "transform_profile": TRANSFORM_PROFILES[index % len(TRANSFORM_PROFILES)],
            }
        )
    return selected


def _excluded_templates(manifest_path: Path | None) -> set[int]:
    if manifest_path is None:
        return set()
    resolved = manifest_path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"ERROR: exclusion manifest not found: {resolved}")
    manifest = json.loads(resolved.read_text(encoding="utf-8"))
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise SystemExit("ERROR: exclusion manifest does not contain cases.")
    templates = {
        int(case["template"])
        for case in cases
        if isinstance(case, dict) and case.get("template") is not None
    }
    if not templates:
        raise SystemExit("ERROR: exclusion manifest does not contain source templates.")
    return templates


def _materialize_case(
    source: zipfile.ZipFile,
    output: Path,
    case: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    image_bytes = source.read(case["image_member"])
    annotation = json.loads(source.read(case["annotation_member"]))
    fields = _expected_fields(annotation)
    validation_codes = _validation_codes(fields)
    document_name = f"{case['document_id']}.pdf"
    relative_document = Path("documents") / document_name
    document_path = output / case["split"] / relative_document
    document_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(io.BytesIO(image_bytes)) as loaded:
        image = _transform(loaded.convert("RGB"), case["transform_profile"])
        image.save(document_path, "PDF", resolution=150.0)

    expected = {
        "document_id": case["document_id"],
        "source_file": relative_document.as_posix(),
        "scenario_category": f"external_{case['transform_profile']}",
        "expected_validation_codes": validation_codes,
        "expected_review_status": "needs_review",
        **fields,
    }
    private_metadata = {
        **case,
        "source_image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "generated_pdf_sha256": _digest(document_path, "sha256"),
    }
    return expected, private_metadata


def _expected_fields(annotation: dict[str, Any]) -> dict[str, str | None]:
    subtotal, subtotal_currency = _money(annotation, "SUB_TOTAL")
    tax, tax_currency = _money(annotation, "TAX")
    if tax is None:
        tax, tax_currency = _single_gst(annotation)
    total, total_currency = _money(annotation, "TOTAL")
    if total is None:
        total, total_currency = _money(annotation, "AMOUNT_DUE")
    if total is None:
        total, total_currency = _money(annotation, "BALANCE_DUE")

    return {
        "vendor_name": _annotation_text(annotation, "SELLER_NAME"),
        "invoice_number": _invoice_number(_annotation_text(annotation, "NUMBER")),
        "invoice_date": _date_value(_annotation_text(annotation, "DATE")),
        "due_date": _date_value(_annotation_text(annotation, "DUE_DATE")),
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "currency": total_currency or subtotal_currency or tax_currency,
    }


def _single_gst(annotation: dict[str, Any]) -> tuple[str | None, str | None]:
    keys = [key for key in annotation if re.fullmatch(r"GST\(\d+%\)", key)]
    if len(keys) != 1:
        return None, None
    value = _annotation_text(annotation, keys[0])
    if value is None:
        return None, None
    amount_match = re.search(r"(-?\d+(?:\.\d+)?)\s*$", value)
    if amount_match is None:
        raise ValueError(f"Unsupported FATURA GST label: {value}")
    amount = Decimal(amount_match.group(1)).quantize(Decimal("0.01"))
    return str(amount), None


def _annotation_text(annotation: dict[str, Any], key: str) -> str | None:
    value = annotation.get(key)
    if not isinstance(value, dict):
        return None
    text = value.get("text")
    return str(text).strip() if text not in (None, "") else None


def _invoice_number(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(
        r"^invoice\s*(?:number|no\.?|id|#)?\s*[:#-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()
    return normalized or None


def _date_value(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"\b(\d{1,2}-[A-Za-z]{3}-\d{4})\b", value)
    if match is None:
        raise ValueError(f"Unsupported FATURA date label: {value}")
    return datetime.strptime(match.group(1), "%d-%b-%Y").date().isoformat()


def _money(annotation: dict[str, Any], key: str) -> tuple[str | None, str | None]:
    value = _annotation_text(annotation, key)
    if value is None:
        return None, None
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(USD|EUR|\$)\s*$", value, re.IGNORECASE)
    if match is None:
        raise ValueError(f"Unsupported FATURA money label: {value}")
    amount = Decimal(match.group(1)).quantize(Decimal("0.01"))
    currency = "USD" if match.group(2) == "$" else match.group(2).upper()
    return str(amount), currency


def _validation_codes(fields: dict[str, str | None]) -> list[str]:
    invoice = InvoiceData(
        vendor_name=fields["vendor_name"],
        invoice_number=fields["invoice_number"],
        invoice_date=_optional_date(fields["invoice_date"]),
        due_date=_optional_date(fields["due_date"]),
        subtotal=_optional_decimal(fields["subtotal"]),
        tax=_optional_decimal(fields["tax"]),
        total=_optional_decimal(fields["total"]),
        currency=fields["currency"],
    )
    return sorted({issue.code for issue in validate_invoice(invoice).issues})


def _optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _optional_decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _transform(image: Image.Image, profile: str) -> Image.Image:
    if profile == "clean":
        return image
    if profile == "low_contrast":
        return ImageEnhance.Contrast(image).enhance(0.62)
    if profile == "soft_blur":
        return image.filter(ImageFilter.GaussianBlur(radius=0.85))
    if profile == "slight_skew":
        return image.rotate(1.25, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
    if profile == "compressed":
        reduced = image.resize(
            (max(1, int(image.width * 0.58)), max(1, int(image.height * 0.58))),
            Image.Resampling.BILINEAR,
        )
        return reduced.resize(image.size, Image.Resampling.BILINEAR)
    raise ValueError(f"Unsupported transform profile: {profile}")


def _write_holdout_seal(output: Path) -> None:
    holdout = output / "holdout"
    documents = sorted((holdout / "documents").glob("*.pdf"))
    seal = {
        "seal_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_json_sha256": _digest(holdout / "expected.json", "sha256"),
        "documents": [{"name": path.name, "sha256": _digest(path, "sha256")} for path in documents],
    }
    _write_json(output / "holdout_seal.json", seal)


def _invoice_fields() -> tuple[str, ...]:
    return (
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax",
        "total",
        "currency",
    )


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
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
