"""Score the real AP matcher on reviewer-verified reference input, apart from OCR quality."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.security import SecurityContext  # noqa: E402
from app.documents.models import DocumentRecord  # noqa: E402
from app.documents.repositories import InMemoryDocumentRepository, InMemoryExtractionRepository  # noqa: E402
from app.documents.sqlite_store import SqliteStore  # noqa: E402
from app.extraction.schemas import InvoiceData, InvoiceExtraction, InvoiceLineItem  # noqa: E402
from app.procurement.matching import MatchService  # noqa: E402
from app.procurement.models import EvidenceUpdate, FieldEvidence, Mapping, MatchPolicy, Policy, SnapshotInput  # noqa: E402
from app.procurement.repository import VersionRepository  # noqa: E402
from app.procurement.service import EvidenceService  # noqa: E402
from app.providers.contracts import ExtractionResult  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402
from phase6_validate_pack import audit, load_json  # noqa: E402


CATEGORY_CODES = {
    "quantity": {"quantity_exceeds_available"},
    "price": {"price_variance"},
    "receipt": {"receipt_shortfall"},
    "duplicate": {"duplicate_confirmed"},
}


def invoice_data(label: dict) -> InvoiceData:
    rows = tuple(InvoiceLineItem(
        line_id=f"L{index + 1}", description=row["description"], uom=row["uom"],
        quantity=Decimal(row["quantity"]), unit_price=Decimal(row["unit_price"]),
        amount=Decimal(row["amount"]),
    ) for index, row in enumerate(label["line_items"]))
    return InvoiceData(vendor_name=label["vendor_name"], invoice_number=label["invoice_number"],
                       invoice_date=date.fromisoformat(label["invoice_date"]),
                       due_date=date.fromisoformat(label["due_date"]),
                       subtotal=Decimal(label["subtotal"]), tax=Decimal(label["tax"]),
                       total=Decimal(label["total"]), currency=label["currency"], line_items=rows)


def run(pack: Path, split: str, revision_ids: tuple[str, ...] = ()) -> dict:
    pack = pack.resolve()
    check = audit(pack, require_sealed=split != "development", inspect_pdf_text=False)
    if split not in {"development", "quality_holdout"}:
        raise ValueError("Reference match is intended for development or quality holdout")
    if revision_ids and split != "development":
        raise ValueError("Revision replay is development only")
    families = next(cohort["families"] for cohort in load_json(pack / "manifest.json")["cohorts"]
                    if cohort["split"] == split)
    labels_by_id = {record["document_id"]: record for record in load_json(pack / split / "expected.json")}
    mappings = {}
    items = {}
    changes = {}
    for family in families:
        source = load_json(pack / split / family["family_id"] / "procurement.json")
        mappings[source["purchase_order"]["supplier_id"]] = source["purchase_order"]["supplier_id"]
        item = source["purchase_order"]["lines"][0]["item_id"]
        items[item] = item
        for revision in load_json(pack / split / family["family_id"] / "corrections.json")["events"]:
            if revision["revision_id"] in revision_ids:
                changes[family["family_id"]] = revision
                if revision["kind"] == "supplier_alias_change":
                    mappings[revision["new_vendor_name"]] = source["purchase_order"]["supplier_id"]
    admin = SecurityContext("Phase 6 admin", role="admin", is_admin=True)
    reviewer = SecurityContext("Phase 6 reference reviewer", role="reviewer")
    approver = SecurityContext("Phase 6 approver", role="ap_approver")
    observations = []
    with tempfile.TemporaryDirectory() as temporary:
        store = SqliteStore(Path(temporary) / "reference.db")
        try:
            repo = VersionRepository(store)
            documents = InMemoryDocumentRepository()
            extractions = InMemoryExtractionRepository()
            evidence = EvidenceService(repo, documents, extractions)
            matcher = MatchService(evidence)
            company = "Invoice Review Assisted Benchmark"
            evidence.configure("mapping", Mapping(company=company, supplier_aliases=mappings,
                item_mappings=items, reason="Phase 6 synthetic reference master"), admin)
            evidence.configure("policy", Policy(company=company, currency="USD",
                reason="Phase 6 synthetic currency policy"), admin)
            matcher.configure_policy(MatchPolicy(company=company,
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                mode="ordered",
                reason="Phase 6 exact quantity and price policy"), admin)
            for revision in changes.values():
                if revision["kind"] == "price_tolerance_change":
                    matcher.configure_policy(MatchPolicy(company=company,
                        effective_from=datetime.fromisoformat(revision["at"]), mode="ordered",
                        price_tolerance_absolute=revision["absolute_tolerance"],
                        reason="Dated development purchasing revision"), admin)
            for family in families:
                directory = pack / split / family["family_id"]
                source = load_json(directory / "procurement.json")
                change = changes.get(family["family_id"])
                if change and change["kind"] == "receipt_quantity_correction":
                    receipt = source["purchase_receipt"]
                    receipt["source_version"] = receipt["source_updated_at"] = change["at"]
                    receipt["lines"][0]["quantity"] = change["corrected_received_quantity"]
                    receipt["lines"][0]["amount"] = str(Decimal(change["corrected_received_quantity"])
                                                        * Decimal(receipt["lines"][0]["unit_price"]))
                evidence.import_records([source["purchase_order"], source["purchase_receipt"]], admin)
                expected_matches = load_json(directory / "expected-match.json")
                for expectation in expected_matches:
                    label = labels_by_id[expectation["document_id"]]
                    if change:
                        expectation["issue_codes"] = []
                        expectation["expected_action"] = "submit"
                        if change["kind"] == "supplier_alias_change":
                            label["vendor_name"] = change["new_vendor_name"]
                    tick = time.perf_counter()
                    document = DocumentRecord(original_filename="synthetic.pdf",
                                              storage_key=expectation["document_id"],
                                              content_type="application/pdf")
                    documents.save(document)
                    data = invoice_data(label)
                    extractions.save(document.id, ExtractionResult(InvoiceExtraction(data), "phase6_reference"),
                                     validate_invoice(data))
                    revision = evidence.capture(document.id, reviewer)
                    fields = {path: FieldEvidence(kind="observed", raw=str(value["effective"]),
                        effective=value["effective"], page=1, excerpt=str(value["effective"]))
                        for path, value in revision["fields"].items() if value["effective"] is not None}
                    revision = evidence.attest(document.id, EvidenceUpdate(
                        expected_revision=revision["version"], fields=fields,
                        reason="Synthetic reference evidence from independently authored oracle"), reviewer)
                    snapshot = evidence.snapshot(document.id, SnapshotInput(
                        company=company, expected_revision=revision["version"], source_system="erpnext",
                        po_ids=[source["purchase_order"]["source_id"]],
                        receipt_ids=[source["purchase_receipt"]["source_id"]],
                        allocations={"L1": expectation["po_allocation"]}), reviewer)
                    evidence.approve(snapshot["id"], snapshot["payload_hash"], approver)
                    assessed = matcher.assess(snapshot["id"], reviewer)
                    issues = sorted({row["code"] for row in assessed["issues"]})
                    observations.append({"document_id": expectation["document_id"],
                        "expected_issue_codes": sorted(expectation["issue_codes"]),
                        "actual_issue_codes": issues,
                        "expected_action": expectation["expected_action"],
                        "actual_action": "submit" if assessed["recommendation"] == "ready_for_approval" else "hold",
                        "recommendation": assessed["recommendation"],
                        "latency_ms": round((time.perf_counter() - tick) * 1000, 2)})
        finally:
            store.close()
    matrices = {}
    for category, codes in CATEGORY_CODES.items():
        counts = Counter()
        for item in observations:
            expected = bool(codes.intersection(item["expected_issue_codes"]))
            actual = bool(codes.intersection(item["actual_issue_codes"]))
            counts["TP" if expected and actual else "FN" if expected else "FP" if actual else "TN"] += 1
        matrices[category] = {key: counts[key] for key in ("TP", "FN", "FP", "TN")}
    clean = [item for item in observations if item["expected_action"] == "submit"]
    unsafe = [item for item in observations if item["expected_action"] == "hold"]
    return {"scope": "deterministic reviewer-verified reference input; no OCR or ERP write",
            "split": split, "manifest_status": check["status"],
            "development_revision_ids": list(revision_ids),
            "scheduled": len(observations),
            "exact_issue_set": sum(item["expected_issue_codes"] == item["actual_issue_codes"] for item in observations),
            "category_matrices": matrices,
            "false_holds": {"numerator": sum(item["actual_action"] == "hold" for item in clean),
                            "denominator": len(clean)},
            "unsafe_ready": {"numerator": sum(item["actual_action"] == "submit" for item in unsafe),
                             "denominator": len(unsafe)},
            "observations": observations}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--split", choices=("development", "quality_holdout"), default="development")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an evaluation result")
    report = run(args.pack, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "observations"}, indent=2))


if __name__ == "__main__":
    main()
