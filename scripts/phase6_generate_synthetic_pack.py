"""Author deterministic, separated Phase 6 development and quality cohorts.

The PDFs and oracle stay under the ignored local pack. Generation is an authoring
step, never an extraction or evaluation result. Refuse to overwrite a prior pack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "_local_docs" / "phase6-pack"
COMPANY = "Invoice Review Assisted Benchmark"
COUNTS = {"development": 60, "quality_holdout": 40, "time_study": 20}
ROLE_FILES = {
    "invoice_labels": "invoice-labels.json",
    "procurement": "procurement.json",
    "timeline": "timeline.json",
    "expected_match": "expected-match.json",
    "expected_posting": "expected-posting.json",
    "corrections": "corrections.json",
}
HEADERS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax",
    "total",
    "currency",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scenario(split: str, index: int) -> str:
    if split == "quality_holdout":
        return ("clean", "quantity_price", "receipt", "duplicate")[index // 10]
    if split == "time_study":
        return "clean" if index < 10 else "receipt"
    return ("clean", "quantity", "price", "receipt", "duplicate", "clean")[index // 10]


def author_family(root: Path, split: str, index: int, token: str) -> tuple[dict, list[dict]]:
    prefix = {"development": "DEV", "quality_holdout": "QH", "time_study": "TS"}[split]
    family_id = f"{prefix}-{token}-{index + 1:03d}"
    kind = scenario(split, index)
    layout_number = index // 10 + 1
    layout_id = f"{prefix}-{token}-V7-LAYOUT-{layout_number:02d}"
    vendor = f"{prefix} {token} Northbridge Components {layout_number:02d}"
    invoice_no = f"{prefix}-{token}-{index + 1:04d}"
    invoice_date = (datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=index % 28)).date()
    if split == "development" and index in {0, 20, 30}:
        invoice_date = {
            0: datetime(2026, 10, 10, tzinfo=UTC),
            20: datetime(2026, 10, 11, tzinfo=UTC),
            30: datetime(2026, 10, 12, tzinfo=UTC),
        }[index].date()
    ordered_qty = 6 + index % 3
    base_price = Decimal(
        61 + index * 5 + {"development": 0, "quality_holdout": 29, "time_study": 41}[split]
    )
    qty = ordered_qty + 1 if kind in {"quantity", "quantity_price"} else ordered_qty
    price = base_price + Decimal("5.00") if kind in {"price", "quantity_price"} else base_price
    subtotal = Decimal(qty) * price
    po_id, receipt_id = f"PO-{family_id}", f"PR-{family_id}"
    item = f"{prefix}-{token} Service Kit {index + 1:03d}"
    row = {
        "vendor_name": vendor,
        "invoice_number": invoice_no,
        "invoice_date": invoice_date.isoformat(),
        "due_date": (invoice_date + timedelta(days=30)).isoformat(),
        "subtotal": f"{subtotal:.2f}",
        "tax": "0.00",
        "total": f"{subtotal:.2f}",
        "currency": "USD",
        "line_items": [
            {
                "description": item,
                "uom": "EA",
                "quantity": str(qty),
                "unit_price": f"{price:.2f}",
                "amount": f"{subtotal:.2f}",
            }
        ],
    }
    row["provenance"] = {
        key: {"kind": "observed", "page": 1, "excerpt": str(row[key])} for key in HEADERS
    }
    row["line_items"][0]["provenance"] = {
        key: {"kind": "observed", "page": 1, "excerpt": str(row["line_items"][0][key])}
        for key in ("description", "uom", "quantity", "unit_price", "amount")
    }
    family_dir = root / split / family_id
    pdf = family_dir / "invoice.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    render_invoice(pdf, row, layout_number, split)
    records = []
    for copy_number in range(2 if kind == "duplicate" else 1):
        document_id = f"{family_id}-{'COPY' if copy_number else 'ORIGINAL'}"
        record = {
            "document_id": document_id,
            "source_file": f"{family_id}/invoice.pdf",
            "scenario_category": kind,
            "expected_validation_codes": [],
            "expected_approval_blocked": False,
            **row,
        }
        if kind == "duplicate":
            record["duplicate_group"] = family_id
        records.append(record)
    received_qty = ordered_qty - 1 if kind == "receipt" else ordered_qty
    source_time = "2026-09-01T00:00:00+00:00"
    po = {
        "company": COMPANY,
        "kind": "po",
        "source_system": "erpnext",
        "source_id": po_id,
        "source_version": source_time,
        "source_updated_at": source_time,
        "supplier_id": vendor,
        "currency": "USD",
        "status": "submitted",
        "lines": [
            {
                "source_line_id": "1",
                "item_id": item,
                "uom": "EA",
                "quantity": str(ordered_qty),
                "unit_price": f"{base_price:.2f}",
                "amount": f"{Decimal(ordered_qty) * base_price:.2f}",
            }
        ],
    }
    receipt = {
        "company": COMPANY,
        "kind": "receipt",
        "source_system": "erpnext",
        "source_id": receipt_id,
        "source_version": source_time,
        "source_updated_at": source_time,
        "supplier_id": vendor,
        "currency": "USD",
        "status": "submitted",
        "lines": [
            {
                "source_line_id": "1",
                "item_id": item,
                "uom": "EA",
                "quantity": str(received_qty),
                "unit_price": f"{base_price:.2f}",
                "amount": f"{Decimal(received_qty) * base_price:.2f}",
                "po_id": po_id,
                "po_line_id": "1",
            }
        ],
    }
    issue_codes = {
        "clean": [],
        "quantity": ["quantity_exceeds_available", "receipt_shortfall"],
        "quantity_price": ["quantity_exceeds_available", "receipt_shortfall", "price_variance"],
        "price": ["price_variance"],
        "receipt": ["quantity_exceeds_available", "receipt_shortfall"],
        "duplicate": [],
    }[kind]
    expected_matches = []
    expected_posts = []
    for copy_number, record in enumerate(records):
        issues = [*issue_codes]
        if copy_number:
            issues.append("duplicate_confirmed")
        ready = not issues
        expected_matches.append(
            {
                "document_id": record["document_id"],
                "issue_codes": issues,
                "pipeline_issue_codes": issues
                + (["quantity_exceeds_available"] if copy_number else []),
                "category": kind,
                "expected_action": "submit" if ready else "hold",
                "po_allocation": f"{po_id}:1",
                "receipt_allocation": f"{receipt_id}:1",
            }
        )
        expected_posts.append(
            {
                "document_id": record["document_id"],
                "eligible_submission": ready,
                "terminal_outcome": "posted_verified" if ready else "exception_resolved",
                "erp_company": COMPANY,
                "supplier": vendor,
                "currency": "USD",
                "grand_total": record["total"],
                "expected_ledger": {
                    "expense_debit": record["total"],
                    "payable_credit": record["total"],
                }
                if ready
                else None,
            }
        )
    events = [
        {"at": source_time, "kind": "po_submitted"},
        {"at": "2026-09-02T00:00:00+00:00", "kind": "receipt_submitted"},
        {
            "at": "2026-09-03T00:00:00+00:00",
            "kind": "invoice_received",
            "document_id": records[0]["document_id"],
        },
    ]
    if kind == "duplicate":
        events.append(
            {
                "at": "2026-09-04T00:00:00+00:00",
                "kind": "invoice_received",
                "document_id": records[1]["document_id"],
            }
        )
    revision = None
    if split == "development" and index in {0, 20, 30}:
        revision = {
            0: {
                "revision_id": "supplier-alias-2026-10-10",
                "at": "2026-10-10T00:00:00+00:00",
                "kind": "supplier_alias_change",
                "new_vendor_name": vendor + " LLC",
                "expected_after_unmapped": "hold",
                "expected_after_mapping": "submit",
            },
            20: {
                "revision_id": "price-tolerance-2026-10-11",
                "at": "2026-10-11T00:00:00+00:00",
                "kind": "price_tolerance_change",
                "absolute_tolerance": "5.00",
                "expected_before": "hold",
                "expected_after": "submit",
            },
            30: {
                "revision_id": "receipt-correction-2026-10-12",
                "at": "2026-10-12T00:00:00+00:00",
                "kind": "receipt_quantity_correction",
                "corrected_received_quantity": str(ordered_qty),
                "expected_before": "hold",
                "expected_after": "submit",
            },
        }[index]
        events.append(
            {"at": revision["at"], "kind": revision["kind"], "revision_id": revision["revision_id"]}
        )
    content = {
        "invoice_labels": records,
        "procurement": {"purchase_order": po, "purchase_receipt": receipt},
        "timeline": {"events": events},
        "expected_match": expected_matches,
        "expected_posting": expected_posts,
        "corrections": {
            "events": [revision] if revision else [],
            "label": "development replay only; original extraction remains immutable",
        },
    }
    artifacts = [
        {
            "path": str(pdf.relative_to(root)).replace("\\", "/"),
            "sha256": sha256(pdf),
            "role": "source_pdf",
        }
    ]
    for role, filename in ROLE_FILES.items():
        path = family_dir / filename
        write_json(path, content[role])
        artifacts.append(
            {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "sha256": sha256(path),
                "role": role,
            }
        )
    family = {
        "family_id": family_id,
        "layout_family_ids": [layout_id],
        "duplicate_group_ids": [family_id] if kind == "duplicate" else [],
        "counts": {
            "families": 1,
            "invoices": len(records),
            "lines": len(records),
            "duplicate_pairs": 1 if kind == "duplicate" else 0,
            "supplier_layouts": 1,
            "rule_revisions": int(revision is not None),
            "erp_operations": sum(x["eligible_submission"] for x in expected_posts),
        },
        "artifacts": artifacts,
    }
    return family, records


def render_invoice(path: Path, row: dict, layout_number: int, split: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1, pageCompression=1)
    pdf.setTitle("Synthetic invoice " + row["invoice_number"])
    pdf.setAuthor("Invoice Review Phase 6")
    width, height = A4
    if split == "quality_holdout":
        render_holdout_invoice(pdf, row, layout_number, width, height)
        pdf.save()
        return
    if split == "time_study":
        render_time_invoice(pdf, row, layout_number, width, height)
        pdf.save()
        return
    accent = colors.HexColor("#1E5A63") if split == "development" else colors.HexColor("#684F38")
    left = 46 + (layout_number % 3) * 8
    top = height - 48 - (layout_number % 2) * 12
    pdf.setFillColor(accent)
    pdf.setFont("Helvetica-Bold", 22 if layout_number % 2 else 18)
    pdf.drawString(left, top, "INVOICE")
    pdf.setStrokeColor(accent)
    pdf.line(left, top - 9, width - left, top - 9)
    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica", 9)
    y = top - 55
    details = [
        ("Supplier", row["vendor_name"]),
        ("Invoice no.", row["invoice_number"]),
        ("Invoice date", row["invoice_date"]),
        ("Due date", row["due_date"]),
        ("Currency", row["currency"]),
    ]
    if layout_number % 2 == 0:
        details = [details[1], details[0], *details[2:]]
    for label, value in details:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(left, y, label)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left + 120 + (layout_number % 3) * 8, y, value)
        y -= 28
    y -= 32
    pdf.setFillColor(accent)
    pdf.rect(left, y - 5, width - 2 * left, 24, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    for offset, label in (
        (8, "Description"),
        (245, "UOM"),
        (300, "Qty"),
        (350, "Rate"),
        (420, "Amount"),
    ):
        pdf.drawString(left + offset, y + 3, label)
    y -= 30
    item = row["line_items"][0]
    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica", 11)
    for offset, key in (
        (8, "description"),
        (245, "uom"),
        (300, "quantity"),
        (350, "unit_price"),
        (420, "amount"),
    ):
        pdf.drawString(left + offset, y, item[key])
    y -= 62
    for label, value in (
        ("Subtotal", row["subtotal"]),
        ("Tax", row["tax"]),
        ("Total", row["total"]),
    ):
        pdf.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 11)
        pdf.drawRightString(width - left - 100, y, label)
        pdf.drawRightString(width - left, y, value)
        y -= 28
    pdf.setFont("Helvetica", 8)
    pdf.drawString(left, 65, "Synthetic accounts payable fixture - no customer data")
    pdf.save()


def render_holdout_invoice(
    pdf: canvas.Canvas, row: dict, layout_number: int, width: float, height: float
) -> None:
    """Letterhead form with a vertical fact panel and an item ledger."""
    ink = colors.HexColor("#28333B")
    accent = colors.HexColor("#526B66") if layout_number % 2 else colors.HexColor("#6B5C52")
    margin = 34
    pdf.setFillColor(accent)
    pdf.rect(margin, height - 92, width - 2 * margin, 48, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawRightString(width - margin - 14, height - 76, "INVOICE")
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, height - 126, "Supplier: " + row["vendor_name"])
    entries = [
        ("Invoice no.", row["invoice_number"]),
        ("Invoice date", row["invoice_date"]),
        ("Due date", row["due_date"]),
        ("Currency", row["currency"]),
    ]
    if layout_number % 2 == 0:
        entries = [entries[0], entries[3], entries[1], entries[2]]
    pdf.setStrokeColor(accent)
    pdf.rect(margin, height - 292, width - 2 * margin, 138, fill=0, stroke=1)
    pdf.setFont("Helvetica", 11)
    for n, (label, value) in enumerate(entries):
        x = margin + 12 + 8 * (layout_number % 2)
        y = height - 180 - n * 30
        pdf.drawString(x, y, f"{label}: {value}")
    table_y = height - 348 - 8 * (layout_number % 2)
    pdf.setFont("Helvetica-Bold", 10)
    for offset, label in (
        (4, "Description"),
        (245, "UOM"),
        (300, "Qty"),
        (355, "Rate"),
        (441, "Amount"),
    ):
        pdf.drawString(margin + offset, table_y, label)
    pdf.line(margin, table_y - 10, width - margin, table_y - 10)
    item = row["line_items"][0]
    pdf.setFont("Helvetica", 12)
    for offset, key in (
        (4, "description"),
        (245, "uom"),
        (300, "quantity"),
        (355, "unit_price"),
        (441, "amount"),
    ):
        pdf.drawString(margin + offset, table_y - 38, item[key])
    pdf.line(margin, table_y - 54, width - margin, table_y - 54)
    total_y = table_y - 104
    for label, value in (
        ("Subtotal", row["subtotal"]),
        ("Tax", row["tax"]),
        ("Total due", row["total"]),
    ):
        pdf.setFont("Helvetica-Bold" if label == "Total due" else "Helvetica", 12)
        pdf.drawString(margin + 285, total_y, f"{label}: {value}")
        total_y -= 32
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, 68, "Synthetic accounts payable fixture - no customer data")


def render_time_invoice(
    pdf: canvas.Canvas, row: dict, layout_number: int, width: float, height: float
) -> None:
    """Compact operator form with another header and line geometry."""
    navy = colors.HexColor("#283C50")
    pdf.setFillColor(navy)
    pdf.rect(0, height - 126, width, 126, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(50, height - 70, "INVOICE")
    pdf.setFont("Helvetica", 11)
    pdf.drawRightString(width - 50, height - 70, row["vendor_name"])
    pdf.setFillColor(navy)
    y = height - 180
    facts = [
        ("Invoice no.", row["invoice_number"]),
        ("Invoice date", row["invoice_date"]),
        ("Due", row["due_date"]),
        ("Currency", row["currency"]),
    ]
    for idx, (label, value) in enumerate(facts):
        x = 50 if idx < 2 else width / 2 + 10
        row_y = y - (idx % 2) * 44
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x, row_y, label)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x + 90, row_y, value)
    y -= 165 + layout_number % 2 * 12
    pdf.setFont("Helvetica-Bold", 9)
    for x, label in (
        (50, "Description"),
        (305, "UOM"),
        (365, "Qty"),
        (415, "Rate"),
        (505, "Amount"),
    ):
        pdf.drawString(x, y, label)
    pdf.setStrokeColor(navy)
    pdf.line(50, y - 7, width - 40, y - 7)
    item = row["line_items"][0]
    pdf.setFont("Helvetica", 9)
    for x, key in (
        (50, "description"),
        (305, "uom"),
        (365, "quantity"),
        (415, "unit_price"),
        (505, "amount"),
    ):
        pdf.drawString(x, y - 32, item[key])
    pdf.line(50, y - 45, width - 40, y - 45)
    y -= 105
    for label, value in (
        ("Subtotal", row["subtotal"]),
        ("Tax", row["tax"]),
        ("Total", row["total"]),
    ):
        pdf.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 10)
        pdf.drawRightString(width - 140, y, label)
        pdf.drawRightString(width - 48, y, value)
        y -= 29
    pdf.setFont("Helvetica", 8)
    pdf.drawString(50, 65, "Synthetic accounts payable fixture - no customer data")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--token", default="DRAFT", help="Unique public synthetic instance token")
    args = parser.parse_args()
    if not args.token.isascii() or not args.token.isalnum() or len(args.token) > 8:
        raise SystemExit("Token must be 1-8 ASCII letters or digits")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite a Phase 6 pack: {output}")
    if ROOT not in output.parents:
        raise SystemExit(
            "This authoring command writes only inside the ignored repository local folder"
        )
    output.mkdir(parents=True)
    cohorts = []
    for split, count in COUNTS.items():
        families, records = [], []
        for index in range(count):
            family, invoice_records = author_family(output, split, index, args.token)
            families.append(family)
            records.extend(invoice_records)
        write_json(output / split / "expected.json", records)
        cohorts.append(
            {
                "split": split,
                "planned_families": count,
                "actual_counts": {
                    "families": count,
                    "invoices": len(records),
                    "lines": len(records),
                    "duplicate_pairs": sum(x["counts"]["duplicate_pairs"] for x in families),
                    "supplier_layouts": len(
                        {layout for x in families for layout in x["layout_family_ids"]}
                    ),
                    "rule_revisions": sum(x["counts"]["rule_revisions"] for x in families),
                    "erp_operations": sum(x["counts"]["erp_operations"] for x in families),
                },
                "families": families,
            }
        )
    write_json(
        output / "manifest.json",
        {
            "contract_version": "2.0.0",
            "status": "planned",
            "label_provenance": "developer/AI-assisted synthetic",
            "cohorts": cohorts,
            "freeze": None,
        },
    )
    print(
        json.dumps(
            {"output": str(output), "cohorts": {x["split"]: x["actual_counts"] for x in cohorts}},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
