from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))

from app.core.settings import load_settings  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from provision_erpnext_master_data import _read_env_value  # noqa: E402


PRIVATE_ROOT = ROOT / "_private_data/erpnext-benchmark-phase8"
PRACTICE_PDF = PRIVATE_ROOT / "phase8-practice-invoice.pdf"
PRACTICE_EXPECTED = PRIVATE_ROOT / "phase8-practice-expected.json"
DRY_RUN_RECORD = PRIVATE_ROOT / "dry-run-record.json"
FREEZE_MANIFEST = PRIVATE_ROOT / "freeze-manifest.json"
FORMAL_WORKBOOK = (
    ROOT
    / "_private_data/erpnext-benchmark-phase4/outputs/phase-4/erpnext-controlled-benchmark.xlsx"
)
PRACTICE_INVOICE_NUMBER = "PHASE8-PRACTICE-001"
PRACTICE_ERP_SUPPLIER = "Acme Logistics - Assisted Benchmark"
PRACTICE_FILENAME = "phase8-practice-invoice.pdf"
APP_BASE_URL = "http://127.0.0.1:8000"
PROTOCOL_VERSION = "1.2"
FORMAL_DATASET_FINGERPRINT = "ca37538cd0f823acf811f23b92ffcda9e74c56000ed7f580def37bee75420407"


@dataclass(frozen=True)
class PracticeInvoice:
    vendor_name: str = "Acme Logistics"
    invoice_number: str = PRACTICE_INVOICE_NUMBER
    invoice_date: str = "2026-07-01"
    due_date: str = "2026-07-31"
    description: str = "Document review services"
    quantity: str = "1"
    unit_price: str = "100.00"
    subtotal: str = "100.00"
    tax: str = "10.00"
    total: str = "110.00"
    currency: str = "USD"


def main() -> None:
    args = _parse_args()
    if args.command == "prepare":
        _prepare()
    elif args.command == "record":
        _record(args)
    elif args.command == "reset-erp":
        _reset_erp()
    elif args.command == "freeze":
        _freeze()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and freeze the private ERPNext Phase 8 dry run."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "prepare", help="Create the private practice fixture and record template."
    )

    record = subparsers.add_parser("record", help="Record one operator dry-run result.")
    record.add_argument("workflow", choices=("manual", "assisted"))
    record.add_argument("--elapsed-seconds", type=float, required=True)
    record.add_argument("--active-seconds", type=float, required=True)
    record.add_argument("--erp-id", required=True)
    record.add_argument("--notes", default="")

    subparsers.add_parser(
        "reset-erp", help="Reset exact Phase 8 practice records in the local app and ERPNext."
    )
    subparsers.add_parser(
        "freeze",
        help="Freeze non-secret benchmark configuration after both operator rehearsals pass.",
    )
    return parser.parse_args()


def _prepare() -> None:
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    invoice = PracticeInvoice()
    _write_practice_pdf(invoice)
    _write_json(
        PRACTICE_EXPECTED,
        {
            "schema_version": 1,
            "purpose": "phase8_non_benchmark_dry_run",
            "formal_benchmark_case": False,
            "invoice": asdict(invoice),
            "expected_erp": {
                "doctype": "Purchase Invoice",
                "docstatus": 0,
                "supplier": PRACTICE_ERP_SUPPLIER,
                "bill_no": invoice.invoice_number,
                "posting_date_policy": "trial_date",
                "bill_date": invoice.invoice_date,
                "due_date": invoice.due_date,
                "currency": invoice.currency,
                "grand_total": invoice.total,
            },
            "pdf_sha256": _sha256(PRACTICE_PDF),
        },
    )
    if not DRY_RUN_RECORD.exists():
        _write_json(
            DRY_RUN_RECORD,
            {
                "schema_version": 1,
                "protocol_version": PROTOCOL_VERSION,
                "fixture": PRACTICE_PDF.name,
                "formal_dataset_used": False,
                "timer_rule": (
                    "Elapsed includes provider and ERP wait; active time includes operator work "
                    "and excludes unattended wait."
                ),
                "workflows": {
                    "manual": _empty_workflow(),
                    "assisted": _empty_workflow(),
                },
            },
        )
    print(f"Practice PDF: {PRACTICE_PDF}")
    print(f"Expected values: {PRACTICE_EXPECTED}")
    print(f"Dry-run record: {DRY_RUN_RECORD}")


def _record(args: argparse.Namespace) -> None:
    if args.elapsed_seconds <= 0 or args.active_seconds <= 0:
        raise SystemExit("Elapsed and active time must both be greater than zero.")
    if args.active_seconds > args.elapsed_seconds:
        raise SystemExit("Active time cannot exceed elapsed time.")
    record = _load_record()
    record["workflows"][args.workflow] = {
        "status": "completed",
        "elapsed_seconds": round(args.elapsed_seconds, 2),
        "active_human_seconds": round(args.active_seconds, 2),
        "draft_verified": True,
        "erp_id": args.erp_id.strip(),
        "notes": args.notes.strip(),
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    _write_json(DRY_RUN_RECORD, record)
    print(f"Recorded {args.workflow} operator rehearsal.")


def _reset_erp() -> None:
    settings, admin = _admin_client()
    admin.login(_admin_password())
    try:
        rows = admin.list_documents(
            "Purchase Invoice",
            filters={"bill_no": PRACTICE_INVOICE_NUMBER, "docstatus": 0},
            fields=("name", "bill_no", "docstatus"),
            limit=20,
        )
        for row in rows:
            admin.delete_document("Purchase Invoice", str(row["name"]))
        print(f"Removed {len(rows)} Phase 8 practice Draft(s) from {settings.erpnext_base_url}.")
    finally:
        admin.logout()
    removed = _reset_application_records(settings.admin_token)
    print(f"Removed {removed} Phase 8 practice record(s) from {APP_BASE_URL}.")


def _freeze() -> None:
    record = _load_record()
    incomplete = [
        name
        for name, result in record["workflows"].items()
        if result.get("status") != "completed" or not result.get("draft_verified")
    ]
    if incomplete:
        raise SystemExit(
            "Cannot freeze: complete and verify these operator rehearsals first: "
            + ", ".join(incomplete)
        )

    settings = load_settings()
    _assert_practice_reset(settings)
    tracked_files = (
        ROOT / "docs/erpnext-benchmark-protocol.md",
        ROOT / "examples/erpnext/benchmark_cases.json",
        ROOT / "backend/app/integrations/erpnext_mapping.py",
        ROOT / "backend/app/integrations/erpnext_adapter.py",
        ROOT / "backend/app/integrations/services.py",
        ROOT / "frontend/src/pages/ExportsPage.tsx",
    )
    missing = [str(path.relative_to(ROOT)) for path in tracked_files if not path.is_file()]
    if missing:
        raise SystemExit("Cannot freeze; required files are missing: " + ", ".join(missing))
    if not FORMAL_WORKBOOK.is_file():
        raise SystemExit(f"Cannot freeze; formal workbook is missing: {FORMAL_WORKBOOK}")

    manifest = {
        "schema_version": 1,
        "frozen_at": datetime.now(UTC).isoformat(),
        "protocol_version": PROTOCOL_VERSION,
        "formal_dataset_fingerprint_sha256": FORMAL_DATASET_FINGERPRINT,
        "git_commit": _git("rev-parse", "HEAD"),
        "configuration": {
            "app_env": settings.app_env,
            "parser_provider": settings.parser_provider,
            "parser_model": settings.mistral_ocr_model,
            "extractor_provider": settings.extractor_provider,
            "extractor_model": settings.extractor_model,
            "extractor_host": urlsplit(settings.extractor_endpoint).hostname,
            "accounting_provider": settings.accounting_provider,
            "accounting_sandbox_mode": settings.accounting_sandbox_mode,
            "erpnext_host": urlsplit(settings.erpnext_base_url).hostname,
            "erpnext_site": settings.erpnext_site,
            "erpnext_versions": _erpnext_versions(settings),
        },
        "artifact_hashes": {
            str(path.relative_to(ROOT)).replace("\\", "/"): _sha256(path) for path in tracked_files
        },
        "formal_workbook": {
            "path": str(FORMAL_WORKBOOK.relative_to(ROOT)).replace("\\", "/"),
            "sha256": _sha256(FORMAL_WORKBOOK),
        },
        "dry_run_record_sha256": _sha256(DRY_RUN_RECORD),
        "secrets_included": False,
    }
    _write_json(FREEZE_MANIFEST, manifest)
    print(f"Freeze manifest: {FREEZE_MANIFEST}")


def _write_practice_pdf(invoice: PracticeInvoice) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0B1F3A"),
        alignment=TA_RIGHT,
        spaceAfter=2 * mm,
    )
    small = ParagraphStyle(
        "InvoiceSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#42526B"),
    )
    normal = ParagraphStyle(
        "InvoiceNormal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#172B4D"),
    )
    document = SimpleDocTemplate(
        str(PRACTICE_PDF),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="Phase 8 Practice Invoice",
        author="Invoice Review",
    )

    story: list[Any] = []
    header = Table(
        [
            [
                Paragraph(
                    "<b>ACME LOGISTICS</b><br/>120 Harbor Road<br/>Seattle, WA 98101", normal
                ),
                Paragraph("INVOICE", title),
            ]
        ],
        colWidths=[105 * mm, 46 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([header, Spacer(1, 10 * mm)])

    details = Table(
        [
            ["Invoice number", invoice.invoice_number],
            ["Invoice date", invoice.invoice_date],
            ["Due date", invoice.due_date],
            ["Currency", invoice.currency],
        ],
        colWidths=[35 * mm, 55 * mm],
        hAlign="RIGHT",
    )
    details.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#172B4D")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend(
        [
            Paragraph(
                "<b>Bill to</b><br/>Northstar Operations<br/>88 Market Street<br/>Jakarta", normal
            ),
            Spacer(1, 4 * mm),
            details,
            Spacer(1, 12 * mm),
        ]
    )

    line_items = Table(
        [
            ["Description", "Qty", "Unit price", "Amount"],
            [invoice.description, invoice.quantity, invoice.unit_price, invoice.subtotal],
        ],
        colWidths=[78 * mm, 18 * mm, 28 * mm, 28 * mm],
    )
    line_items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7F5F5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#074A50")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9D6E2")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    totals = Table(
        [
            ["Subtotal", invoice.subtotal],
            ["Tax (10%)", invoice.tax],
            ["Total", f"{invoice.currency} {invoice.total}"],
        ],
        colWidths=[35 * mm, 35 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 2), (-1, 2), 1, colors.HexColor("#0A7F86")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            line_items,
            Spacer(1, 7 * mm),
            totals,
            Spacer(1, 18 * mm),
            Paragraph(
                "Payment terms: Net 30. This synthetic invoice is reserved for the Phase 8 "
                "practice run and is not part of the formal T01-T10 benchmark.",
                small,
            ),
        ]
    )
    document.build(story)


def _empty_workflow() -> dict[str, object]:
    return {
        "status": "pending",
        "elapsed_seconds": None,
        "active_human_seconds": None,
        "draft_verified": False,
        "erp_id": None,
        "notes": "",
        "recorded_at": None,
    }


def _load_record() -> dict[str, Any]:
    if not DRY_RUN_RECORD.is_file():
        raise SystemExit("Run the prepare command before recording or freezing Phase 8.")
    parsed = json.loads(DRY_RUN_RECORD.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("workflows"), dict):
        raise SystemExit("The Phase 8 dry-run record is invalid.")
    return parsed


def _admin_client() -> tuple[Any, ERPNextAdminClient]:
    settings = load_settings()
    host = urlsplit(settings.erpnext_base_url).hostname
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Phase 8 reset is restricted to local ERPNext hosts.")
    return settings, ERPNextAdminClient(
        settings.erpnext_base_url,
        timeout=max(settings.erpnext_timeout_seconds, 180),
    )


def _admin_password() -> str:
    password = os.getenv("ERPNEXT_ADMIN_PASSWORD") or _read_env_value(
        ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"
    )
    if not password:
        raise SystemExit("ERPNEXT_ADMIN_PASSWORD is required in the ignored .env file.")
    return password


def _reset_application_records(admin_token: str | None) -> int:
    if not admin_token:
        raise SystemExit("APP_ADMIN_TOKEN is required in the ignored .env file.")
    documents = _app_request("GET", "/documents", admin_token)
    if not isinstance(documents, list):
        raise SystemExit("The application returned an invalid document list.")
    practice_ids = [
        str(document["id"])
        for document in documents
        if isinstance(document, dict)
        and str(document.get("original_filename") or "").casefold() == PRACTICE_FILENAME.casefold()
    ]
    for document_id in practice_ids:
        _app_request(
            "DELETE",
            f"/documents/{document_id}",
            admin_token,
            payload={"reason": "phase8_dry_run"},
        )
    return len(practice_ids)


def _assert_practice_reset(settings: Any) -> None:
    if not settings.admin_token:
        raise SystemExit("APP_ADMIN_TOKEN is required in the ignored .env file.")
    documents = _app_request("GET", "/documents", settings.admin_token)
    application_count = sum(
        1
        for document in documents
        if isinstance(document, dict)
        and str(document.get("original_filename") or "").casefold() == PRACTICE_FILENAME.casefold()
    )

    _, admin = _admin_client()
    admin.login(_admin_password())
    try:
        erp_rows = admin.list_documents(
            "Purchase Invoice",
            filters={"bill_no": PRACTICE_INVOICE_NUMBER, "docstatus": 0},
            fields=("name",),
            limit=20,
        )
    finally:
        admin.logout()
    if application_count or erp_rows:
        raise SystemExit(
            "Cannot freeze while Phase 8 practice records remain. Run reset-erp first."
        )


def _erpnext_versions(settings: Any) -> dict[str, str]:
    if not settings.erpnext_api_key or not settings.erpnext_api_secret:
        raise SystemExit("ERPNext API credentials are required to freeze provider versions.")
    request = Request(
        settings.erpnext_base_url.rstrip("/") + "/api/method/frappe.utils.change_log.get_versions",
        headers={
            "Accept": "application/json",
            "Authorization": (f"token {settings.erpnext_api_key}:{settings.erpnext_api_secret}"),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SystemExit(f"ERPNext version lookup failed with HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERPNext version lookup failed: {type(exc).__name__}.") from exc
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise SystemExit("ERPNext returned an invalid version response.")
    versions = {
        name: str(details.get("version") or "")
        for name, details in message.items()
        if isinstance(details, dict) and details.get("version")
    }
    if not {"frappe", "erpnext"}.issubset(versions):
        raise SystemExit("ERPNext version response did not include Frappe and ERPNext.")
    return versions


def _app_request(
    method: str,
    path: str,
    admin_token: str,
    *,
    payload: dict[str, str] | None = None,
) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "X-Access-Token": admin_token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(APP_BASE_URL + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SystemExit(f"Application reset failed with HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Application reset failed: {type(exc).__name__}.") from exc


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    main()
