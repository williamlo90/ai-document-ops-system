"""One original-provider PDF through Docker HTTP APIs to verified sandbox posting."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import hashlib
from urllib.request import Request, urlopen
from pathlib import Path

from phase7_demo import configure, request, upload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--document-id", help="Resume review of the same original extraction; never reprocess it"
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Do not overwrite or silently rerun a canary observation")
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    base = "http://127.0.0.1:8000"
    if not args.document_id:
        configure(base, fixture)
    document = args.document_id or upload(base, fixture)
    with urlopen(
        Request(
            base + f"/documents/{document}/content", headers={"X-Access-Token": "release-admin"}
        ),
        timeout=30,
    ) as response:
        assert (
            hashlib.sha256(response.read()).digest()
            == hashlib.sha256(Path(fixture["pdf"]).read_bytes()).digest()
        )
    detail = request(base, f"/documents/{document}")
    anchors = {item["field_name"]: item for item in detail["extraction"]["confidence"]}
    revision = request(base, f"/ap/invoices/{document}/capture", {}, token="release-reviewer")
    expected = {key: value for key, value in fixture["invoice"].items() if key != "line_items"}
    line = revision["line_ids"][0]
    expected.update(
        {
            f"lines.{line}.{key}": value
            for key, value in fixture["invoice"]["line_items"][0].items()
            if key != "line_id"
        }
    )
    fields = {}
    for path, wanted in expected.items():
        value = revision["fields"][path]
        if path.rsplit(".", 1)[-1] in {
            "quantity",
            "unit_price",
            "amount",
            "subtotal",
            "tax",
            "total",
        }:
            assert value["effective"] is not None and Decimal(str(value["effective"])) == Decimal(
                wanted
            ), path
        else:
            assert value["effective"] == wanted, path
        source_path = (
            "line_items[0]." + path.rsplit(".", 1)[-1] if path.startswith("lines.") else path
        )
        anchor = anchors[source_path]
        assert anchor["source_page"] and anchor["source_text"], path
        fields[path] = {
            "kind": "observed",
            "raw": str(value["effective"]),
            "effective": value["effective"],
            "page": anchor["source_page"],
            "excerpt": anchor["source_text"],
        }
    reviewed = request(
        base,
        f"/ap/invoices/{document}/evidence",
        {
            "expected_revision": revision["version"],
            "fields": fields,
            "reason": "Original values and provider source anchors verified; no correction",
        },
        token="release-reviewer",
        method="PUT",
    )
    po, receipt = fixture["sources"]
    snapshot = request(
        base,
        f"/ap/invoices/{document}/snapshots",
        {
            "company": fixture["company"],
            "expected_revision": reviewed["version"],
            "source_system": "erpnext",
            "po_ids": [po["source_id"]],
            "receipt_ids": [receipt["source_id"]],
            "allocations": {line: f"{po['source_id']}:{po['lines'][0]['source_line_id']}"},
        },
        token="release-reviewer",
    )
    assert not snapshot["blockers"], snapshot["blockers"]
    request(
        base,
        f"/ap/snapshots/{snapshot['id']}/approve",
        {"payload_hash": snapshot["payload_hash"]},
        token="release-approver",
    )
    match = request(base, f"/ap/snapshots/{snapshot['id']}/match", {}, token="release-reviewer")
    assert match["recommendation"] == "ready_for_approval", match["issues"]
    request(
        base,
        f"/ap/matches/{match['id']}/approve",
        {"basis_hash": match["basis_hash"]},
        token="release-approver",
    )
    draft = request(
        base,
        f"/ap/posting/{match['id']}/draft",
        {
            "match_id": match["id"],
            "expected_basis_hash": match["basis_hash"],
            "receipt_allocations": {},
        },
        token="release-approver",
    )
    assert draft["state"] == "confirmed", draft.get("error_code")
    approval = request(
        base,
        f"/ap/posting/{match['id']}/approve-submit",
        {
            "operation_id": draft["id"],
            "draft_verification_hash": draft["verification_hash"],
            "reason": "Separately verified original canary PDF and ERP draft",
        },
        token="release-approver",
    )
    posted = request(
        base,
        f"/ap/posting/{match['id']}/submit",
        {"approval_hash": approval["approval_hash"]},
        token="release-approver",
    )
    assert posted.get("posted_verified"), posted.get("error_code")
    result = {
        "document_id": document,
        "match_id": match["id"],
        "approval_hash": approval["approval_hash"],
        "target": posted["target"],
        "original_required_fields_verified": len(fields),
        "reviewer_value_corrections": 0,
        "posted_verified": True,
        "provider_documents": 1,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
