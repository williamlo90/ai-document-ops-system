"""Seed a bounded synthetic AP demo through the running application's HTTP API."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def request(base, path, payload=None, *, token="release-admin", method=None):
    headers = {"X-Access-Token": token}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    with urlopen(Request(base + path, data, headers, method=method), timeout=60) as response:
        return json.load(response)


def author(directory, token):
    from reportlab.pdfgen import canvas

    directory.mkdir(parents=True, exist_ok=False)
    invoice = {
        "vendor_name": "Acme Logistics",
        "invoice_number": f"REL-{token}",
        "invoice_date": "2026-06-18",
        "due_date": "2026-07-18",
        "currency": "USD",
        "subtotal": "100.00",
        "tax": "0.00",
        "total": "100.00",
        "line_items": [
            {
                "line_id": "L1",
                "description": "Release Kit",
                "uom": "EA",
                "quantity": "2",
                "unit_price": "50.00",
                "amount": "100.00",
            }
        ],
    }
    pdf = directory / "invoice.pdf"
    document = canvas.Canvas(str(pdf))
    document.setFont("Helvetica-Bold", 24)
    document.drawString(48, 780, "INVOICE")
    document.setFont("Helvetica", 12)
    y = 730
    for label, key in (
        ("Supplier", "vendor_name"),
        ("Invoice no.", "invoice_number"),
        ("Invoice date", "invoice_date"),
        ("Due date", "due_date"),
        ("Currency", "currency"),
    ):
        document.drawString(48, y, f"{label}: {invoice[key]}")
        y -= 30
    document.drawString(
        48, 530, "Description                       UOM      Qty      Rate       Amount"
    )
    document.drawString(
        48, 500, "Release Kit                         EA          2        50.00      100.00"
    )
    for label, key, y in (
        ("Subtotal", "subtotal", 440),
        ("Tax", "tax", 410),
        ("Total", "total", 380),
    ):
        document.drawString(320, y, f"{label}: {invoice[key]}")
    document.drawString(48, 70, "Synthetic release fixture - no customer data")
    document.save()
    fixture = {
        "invoice": invoice,
        "pdf": str(pdf.resolve()),
        "company": "Invoice Review Assisted Benchmark",
    }
    (directory / "fixture.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    return fixture


def upload(base, fixture):
    boundary = uuid.uuid4().hex
    pdf = Path(fixture["pdf"])
    data = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="invoice.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + pdf.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    headers = {
        "X-Access-Token": "release-uploader",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    with urlopen(Request(base + "/documents/upload", data, headers), timeout=30) as response:
        result = json.load(response)
    document_id = result["document"]["id"]
    for _ in range(60):
        detail = request(base, f"/documents/{document_id}")
        if detail.get("extraction"):
            return document_id
        time.sleep(1)
    raise RuntimeError("Worker did not complete within the 60-second demo budget")


def configure(base, fixture):
    company = fixture["company"]
    supplier = fixture["invoice"]["vendor_name"]
    item = fixture["invoice"]["line_items"][0]["description"]
    request(
        base,
        "/ap/mapping",
        {
            "company": company,
            "supplier_aliases": {supplier: supplier},
            "item_mappings": {item: item},
            "reason": "Verified synthetic release fixture",
        },
        method="PUT",
    )
    request(
        base,
        "/ap/policy",
        {"company": company, "currency": "USD", "reason": "Exact release source policy"},
        method="PUT",
    )
    request(
        base,
        "/ap/match-policy",
        {
            "company": company,
            "effective_from": "2026-01-01T00:00:00Z",
            "mode": "ordered",
            "reason": "Exact release quantity and price",
        },
        method="PUT",
    )
    if "sources" not in fixture:
        po_id = "PO-" + fixture["invoice"]["invoice_number"]
        common = {
            "company": company,
            "source_system": "manual",
            "source_version": "1",
            "source_updated_at": "2026-06-18T00:00:00Z",
            "supplier_id": supplier,
            "currency": "USD",
            "status": "submitted",
        }
        line = {
            "source_line_id": "1",
            "item_id": item,
            "uom": "EA",
            "quantity": "2",
            "unit_price": "50.00",
            "amount": "100.00",
        }
        fixture["sources"] = [
            {**common, "kind": "po", "source_id": po_id, "lines": [line]},
            {
                **common,
                "kind": "receipt",
                "source_id": "PR-" + po_id,
                "lines": [{**line, "po_id": po_id, "po_line_id": "1"}],
            },
        ]
    request(base, "/ap/sources/import", {"records": fixture["sources"]})
    if fixture.get("profile"):
        request(base, "/ap/posting-profile", fixture["profile"], method="PUT")


def attest(base, document_id):
    revision = request(base, f"/ap/invoices/{document_id}/capture", {}, token="release-reviewer")
    fields = {
        path: {
            "kind": "corrected",
            "raw": str(value["effective"]),
            "effective": value["effective"],
            "page": 1,
            "excerpt": str(value["effective"]),
            "reason": "Checked against the authored synthetic PDF",
        }
        for path, value in revision["fields"].items()
        if value["effective"] is not None
    }
    return request(
        base,
        f"/ap/invoices/{document_id}/evidence",
        {
            "expected_revision": revision["version"],
            "fields": fields,
            "reason": "Verified all printed synthetic source values",
        },
        token="release-reviewer",
        method="PUT",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    fixture = (
        json.loads(args.fixture.read_text(encoding="utf-8"))
        if args.fixture
        else author(
            args.directory or ROOT / "_local_docs" / f"release-demo-{uuid.uuid4().hex[:8]}",
            uuid.uuid4().hex[:8],
        )
    )
    configure(args.base, fixture)
    doc = upload(args.base, fixture)
    request(
        args.base,
        f"/review/{doc}/save",
        {
            "corrected_data": fixture["invoice"],
            "notes": "Synthetic demo reviewer correction; mock extraction is not an OCR score",
        },
        token="release-reviewer",
    )
    revision = attest(args.base, doc)
    po, receipt = fixture["sources"]
    snapshot = request(
        args.base,
        f"/ap/invoices/{doc}/snapshots",
        {
            "company": fixture["company"],
            "expected_revision": revision["version"],
            "source_system": po["source_system"],
            "po_ids": [po["source_id"]],
            "receipt_ids": [receipt["source_id"]],
            "allocations": {
                revision["line_ids"][0]: f"{po['source_id']}:{po['lines'][0]['source_line_id']}"
            },
        },
        token="release-reviewer",
    )
    assert not snapshot["blockers"], snapshot["blockers"]
    request(
        args.base,
        f"/ap/snapshots/{snapshot['id']}/approve",
        {"payload_hash": snapshot["payload_hash"]},
        token="release-approver",
    )
    match = request(
        args.base, f"/ap/snapshots/{snapshot['id']}/match", {}, token="release-reviewer"
    )
    assert match["recommendation"] == "ready_for_approval", match["issues"]
    try:
        request(
            args.base,
            f"/ap/matches/{match['id']}/approve",
            {"basis_hash": match["basis_hash"]},
            token="release-uploader",
        )
        raise AssertionError("Uploader unexpectedly approved an AP match")
    except HTTPError as exc:
        assert exc.code == 403
    fixture.update(
        document_id=doc,
        snapshot_id=snapshot["id"],
        match_id=match["id"],
        basis_hash=match["basis_hash"],
    )
    output = args.fixture or Path(fixture["pdf"]).parent / "fixture.json"
    output.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ready_for_review",
                "document_id": doc,
                "review_url": args.base + f"/review/{doc}",
                "fixture": str(output),
                "uploader_approval_blocked": True,
            }
        )
    )


if __name__ == "__main__":
    main()
