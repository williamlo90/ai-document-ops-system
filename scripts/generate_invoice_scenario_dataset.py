from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except ImportError as exc:
    raise SystemExit(
        "reportlab is required. Install development dependencies with "
        "'pip install -r requirements-dev.txt'."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ROOT = ROOT / "examples" / "benchmark" / "datasets" / "invoice_scenarios_v1"
PAGE_WIDTH, PAGE_HEIGHT = A4


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic invoice scenario PDFs.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="Dataset directory containing expected.json.",
    )
    args = parser.parse_args()
    dataset_root = args.dataset_root.resolve()
    records = _load_records(dataset_root / "expected.json")
    documents_root = dataset_root / "documents"
    documents_root.mkdir(parents=True, exist_ok=True)

    expected_files: set[Path] = set()
    for record in records:
        source_file = record.get("source_file")
        if not isinstance(source_file, str) or not source_file.endswith(".pdf"):
            raise ValueError(f"Invalid source_file for {record.get('document_id')}")
        output_path = (dataset_root / source_file).resolve()
        if dataset_root not in output_path.parents:
            raise ValueError(f"source_file escapes dataset root: {source_file}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _render_invoice(record, output_path)
        expected_files.add(output_path)

    for stale_pdf in documents_root.glob("*.pdf"):
        if stale_pdf.resolve() not in expected_files:
            stale_pdf.unlink()

    print(f"Generated {len(records)} synthetic invoice PDFs in {documents_root}")


def _load_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("expected.json must contain a non-empty list")
    if not all(isinstance(record, dict) for record in data):
        raise ValueError("Every expected.json record must be an object")
    return data


def _render_invoice(record: dict[str, Any], output_path: Path) -> None:
    pdf = canvas.Canvas(
        str(output_path),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle(f"Synthetic invoice scenario: {record['document_id']}")
    pdf.setAuthor("AI Document Operations System")
    variant = str(record.get("render_variant") or "standard")

    if variant == "rotated":
        pdf.saveState()
        pdf.translate(PAGE_WIDTH, 0)
        pdf.rotate(90)
        _draw_invoice_page(pdf, record, PAGE_HEIGHT, PAGE_WIDTH, variant)
        pdf.restoreState()
    else:
        _draw_invoice_page(pdf, record, PAGE_WIDTH, PAGE_HEIGHT, variant)

    if variant == "multi_page":
        pdf.showPage()
        _draw_terms_page(pdf, record)
    pdf.save()


def _draw_invoice_page(
    pdf: canvas.Canvas,
    record: dict[str, Any],
    width: float,
    height: float,
    variant: str,
) -> None:
    foreground = colors.HexColor("#9AA4B2") if variant == "low_contrast" else colors.HexColor("#172033")
    muted = colors.HexColor("#B7C0CC") if variant == "low_contrast" else colors.HexColor("#64748B")
    accent = colors.HexColor("#8EA5A0") if variant == "low_contrast" else colors.HexColor("#0F766E")
    border = colors.HexColor("#CBD5E1")
    margin = 46
    right = width - margin
    compact = width < PAGE_WIDTH

    pdf.setFillColor(foreground)
    pdf.setFont("Helvetica-Bold", 21 if compact else 25)
    pdf.drawString(margin, height - 58, "INVOICE")
    pdf.setFillColor(accent)
    pdf.rect(margin, height - 70, 66, 4, stroke=0, fill=1)

    pdf.setFillColor(foreground)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(right, height - 48, "Northstar Accounts Demo")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(right, height - 61, "Synthetic fixture - no real customer data")

    y = height - 112
    vendor = _display(record, "vendor_name")
    if vendor is not None:
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(margin, y, "FROM")
        pdf.setFillColor(foreground)
        pdf.setFont("Helvetica-Bold", 11 if len(vendor) < 55 else 9)
        pdf.drawString(margin, y - 18, vendor)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(margin, y - 32, "100 Example Street, Test City")

    info_x = width * (0.55 if not compact else 0.5)
    info_width = right - info_x
    rows = [
        ("Invoice number", _display(record, "invoice_number")),
        ("Invoice date", _display(record, "invoice_date")),
        ("Due date", _display(record, "due_date")),
        ("Currency", _display(record, "currency")),
    ]
    visible_rows = [(label, value) for label, value in rows if value is not None]
    row_height = 21
    box_height = max(len(visible_rows), 1) * row_height + 12
    pdf.setStrokeColor(border)
    pdf.roundRect(info_x, y - box_height + 7, info_width, box_height, 4, stroke=1, fill=0)
    row_y = y - 8
    for label, value in visible_rows:
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 7)
        pdf.drawString(info_x + 10, row_y, label)
        pdf.setFillColor(foreground)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawRightString(right - 10, row_y, value)
        row_y -= row_height

    table_top = y - 124
    table_left = margin
    table_width = right - margin
    columns = (0.0, 0.55, 0.68, 0.84, 1.0)
    pdf.setFillColor(colors.HexColor("#E8F3F1") if variant != "low_contrast" else colors.HexColor("#EEF1F4"))
    pdf.rect(table_left, table_top, table_width, 24, stroke=0, fill=1)
    pdf.setFillColor(foreground)
    pdf.setFont("Helvetica-Bold", 8)
    for label, ratio in zip(
        ("Description", "Qty", "Unit price", "Amount"),
        columns[:-1],
        strict=True,
    ):
        pdf.drawString(table_left + table_width * ratio + 7, table_top + 8, label)

    items = record.get("line_items") or [
        {
            "description": "Professional services",
            "quantity": "1",
            "unit_price": record.get("subtotal") or record.get("total") or "0.00",
            "amount": record.get("subtotal") or record.get("total") or "0.00",
        }
    ]
    item_y = table_top - 20
    pdf.setFont("Helvetica", 8)
    for item in items[:6]:
        values = (
            str(item.get("description") or ""),
            str(item.get("quantity") or ""),
            str(item.get("unit_price") or ""),
            str(item.get("amount") or ""),
        )
        for value, ratio in zip(values, columns[:-1], strict=True):
            pdf.setFillColor(foreground)
            pdf.drawString(table_left + table_width * ratio + 7, item_y, value[:42])
        pdf.setStrokeColor(border)
        pdf.line(table_left, item_y - 8, right, item_y - 8)
        item_y -= 24

    totals_y = min(item_y - 18, table_top - 115)
    total_rows = [
        ("Subtotal", _display(record, "subtotal")),
        ("Tax", _display(record, "tax")),
        ("Total", _display(record, "total")),
    ]
    for label, value in total_rows:
        if value is None:
            continue
        is_total = label == "Total"
        pdf.setFillColor(foreground if not is_total else accent)
        pdf.setFont("Helvetica-Bold" if is_total else "Helvetica", 11 if is_total else 9)
        pdf.drawRightString(right - 100, totals_y, label)
        pdf.drawRightString(right, totals_y, value)
        totals_y -= 24

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(margin, 34, f"Scenario: {record['scenario_category']} | Synthetic benchmark v1")
    if variant == "noisy_footer":
        pdf.drawCentredString(
            width / 2,
            20,
            "Reference only: PO archive 8841 - warehouse 17 - support@example.invalid",
        )


def _draw_terms_page(pdf: canvas.Canvas, record: dict[str, Any]) -> None:
    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(46, PAGE_HEIGHT - 58, "Invoice terms and delivery notes")
    pdf.setFont("Helvetica", 10)
    lines = [
        f"Invoice reference: {_display(record, 'invoice_number') or 'Not provided'}",
        "Payment is due according to the date shown on page one.",
        "This page contains supporting terms and no replacement invoice totals.",
        "Contact accounts@example.invalid for synthetic benchmark questions.",
    ]
    y = PAGE_HEIGHT - 100
    for line in lines:
        pdf.drawString(46, y, line)
        y -= 24
    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(46, 34, "Page 2 of 2 - synthetic fixture")


def _display(record: dict[str, Any], field_name: str) -> str | None:
    overrides = record.get("display_overrides") or {}
    value = overrides.get(field_name, record.get(field_name))
    if value in (None, ""):
        return None
    return str(value)


if __name__ == "__main__":
    main()
