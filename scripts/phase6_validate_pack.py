"""Audit a local Phase 6 pack without executing providers or opening sealed answers for tuning."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.evaluation.invoice import evaluate_invoices  # noqa: E402
from app.procurement.models import ProcurementRecord  # noqa: E402


SPLITS = {"development": 60, "quality_holdout": 40, "time_study": 20}
ROLES = {"source_pdf", "invoice_labels", "procurement", "timeline",
         "expected_match", "expected_posting", "corrections"}
COUNT_KEYS = {"families", "invoices", "lines", "duplicate_pairs", "supplier_layouts",
              "rule_revisions", "erp_operations"}


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_artifact(pack: Path, relative: str, split: str, family_id: str) -> Path:
    if (not relative or "\\" in relative or ":" in relative or relative.startswith("/")):
        fail(f"Invalid artifact path: {relative}")
    path = (pack / relative).resolve()
    family_root = (pack / split / family_id).resolve()
    if not path.is_relative_to(family_root) or not path.is_file():
        fail(f"Artifact missing or escapes its family: {relative}")
    return path


def pdf_text(path: Path) -> str:
    if path.stat().st_size > 1_000_000:
        fail(f"OCR.space PDF limit exceeded: {path}")
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True)
    pages = next((int(line.split(":", 1)[1]) for line in info.stdout.splitlines()
                  if line.startswith("Pages:")), 0)
    if pages < 1 or pages > 3:
        fail(f"PDF page count outside OCR.space limit: {path}")
    result = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                            capture_output=True, text=True, check=True)
    return result.stdout


def audit(pack: Path, *, require_sealed: bool = False, inspect_pdf_text: bool = True) -> dict:
    pack = pack.resolve()
    manifest = load_json(pack / "manifest.json")
    if (manifest.get("contract_version") != "2.0.0"
            or manifest.get("label_provenance") != "developer/AI-assisted synthetic"):
        fail("Wrong Phase 6 dataset contract")
    status = manifest.get("status")
    if status not in {"planned", "sealed"} or (require_sealed and status != "sealed"):
        fail("Pack is not in the required state")
    if (status == "planned") != (manifest.get("freeze") is None):
        fail("Freeze metadata does not match manifest state")
    if status == "sealed":
        details = load_json(pack / "freeze-details.json")
        if details.get("freeze") != manifest["freeze"]:
            fail("Freeze details disagree with sealed manifest")
        if details.get("manifest_sha256") != file_digest(pack / "manifest.json"):
            fail("Sealed manifest hash changed")
        source_hashes = details.get("source_hashes")
        if not isinstance(source_hashes, dict) or not source_hashes:
            fail("Frozen source hashes are missing")
        for relative, expected_hash in source_hashes.items():
            source = (ROOT / relative).resolve()
            if not source.is_relative_to(ROOT) or not source.is_file() or file_digest(source) != expected_hash:
                fail(f"Frozen source changed: {relative}")
        digest = hashlib.sha256()
        for relative in ("erp-profile.json", "erp-provision-journal.json", "erp-environment.json", "lineage.json"):
            if (pack / relative).exists():
                digest.update(f"{relative}\0{file_digest(pack / relative)}\n".encode())
        for cohort in sorted(manifest["cohorts"], key=lambda item: item["split"]):
            split = cohort["split"]
            path = pack / split / "expected.json"
            digest.update(f"{split}/expected.json\0{file_digest(path)}\n".encode())
            for family in sorted(cohort["families"], key=lambda item: item["family_id"]):
                for artifact in sorted(family["artifacts"], key=lambda item: item["path"]):
                    digest.update(f"{artifact['path']}\0{artifact['sha256']}\n".encode())
        if digest.hexdigest() != manifest["freeze"]["oracle_sha256"]:
            fail("Frozen oracle hash changed")
    cohorts = manifest.get("cohorts")
    if not isinstance(cohorts, list) or {c.get("split") for c in cohorts} != set(SPLITS):
        fail("Exactly the three Phase 6 cohorts are required")
    family_ids: set[str] = set()
    layout_owners: dict[str, str] = {}
    duplicate_owners: dict[str, str] = {}
    all_doc_ids: set[str] = set()
    report = {"status": status, "cohorts": {}, "disjoint": True, "artifact_hashes_verified": 0,
              "pdf_text_checked": inspect_pdf_text}
    for cohort in cohorts:
        split = cohort["split"]
        families = cohort["families"]
        if cohort.get("planned_families") != SPLITS[split]:
            fail(f"Planned family count changed for {split}")
        if status == "sealed" and len(families) != SPLITS[split]:
            fail(f"Sealed cohort {split} has too few families")
        if len(families) > SPLITS[split]:
            fail(f"Too many families in {split}")
        records = load_json(pack / split / "expected.json") if families else []
        record_ids = [item["document_id"] for item in records]
        if len(record_ids) != len(set(record_ids)) or all_doc_ids.intersection(record_ids):
            fail(f"Invoice IDs are duplicated within or across splits: {split}")
        all_doc_ids.update(record_ids)
        if records:
            dataset = load_evaluation_dataset(pack / split)
            score = evaluate_invoices(records_from_dataset(dataset), records_from_dataset(dataset))
            if score.quality["full_invoice_documents_matched"] != len(records):
                fail(f"Self-oracle is incomplete or inconsistent in {split}")
        invoices = lines = pairs = operations = revisions = 0
        layout_ids: set[str] = set()
        categories = Counter()
        eligible = clean = 0
        for family in families:
            family_id = family["family_id"]
            if family_id in family_ids:
                fail(f"Family appears twice: {family_id}")
            family_ids.add(family_id)
            for layout in family["layout_family_ids"]:
                if layout in layout_owners and layout_owners[layout] != split:
                    fail(f"Layout family leaks across splits: {layout}")
                layout_owners[layout] = split
                layout_ids.add(layout)
            for duplicate in family["duplicate_group_ids"]:
                if duplicate in duplicate_owners and duplicate_owners[duplicate] != split:
                    fail(f"Duplicate group leaks across splits: {duplicate}")
                duplicate_owners[duplicate] = split
            artifacts = family["artifacts"]
            roles = [item["role"] for item in artifacts]
            if set(roles) != ROLES or len(roles) != len(ROLES):
                fail(f"Family artifact roles are incomplete: {family_id}")
            paths = {}
            for item in artifacts:
                path = safe_artifact(pack, item["path"], split, family_id)
                if file_digest(path) != item["sha256"]:
                    fail(f"Artifact hash changed: {item['path']}")
                paths[item["role"]] = path
                report["artifact_hashes_verified"] += 1
            labels = load_json(paths["invoice_labels"])
            sources = load_json(paths["procurement"])
            expected_match = load_json(paths["expected_match"])
            expected_posting = load_json(paths["expected_posting"])
            timeline = load_json(paths["timeline"])
            corrections = load_json(paths["corrections"])
            for kind, record in sources.items():
                if kind.endswith(("purchase_order", "purchase_receipt")):
                    ProcurementRecord.model_validate(record)
            if {x["document_id"] for x in labels} != {x["document_id"] for x in expected_match} or \
                    {x["document_id"] for x in labels} != {x["document_id"] for x in expected_posting}:
                fail(f"Oracle IDs differ within {family_id}")
            if not {x["document_id"] for x in labels}.issubset(set(record_ids)):
                fail(f"Family invoice absent from split expected.json: {family_id}")
            pdf = paths["source_pdf"]
            if inspect_pdf_text:
                text = pdf_text(pdf)
                for label in labels:
                    for field in ("vendor_name", "invoice_number", "invoice_date", "due_date",
                                  "subtotal", "tax", "total", "currency"):
                        excerpt = label["provenance"][field]["excerpt"]
                        if excerpt not in text:
                            fail(f"Source excerpt absent from PDF: {family_id}/{field}")
                    for line in label["line_items"]:
                        for field in ("description", "uom", "quantity", "unit_price", "amount"):
                            if line["provenance"][field]["excerpt"] not in text:
                                fail(f"Line excerpt absent from PDF: {family_id}/{field}")
            if len(timeline["events"]) < 3:
                fail(f"Event timeline is incomplete: {family_id}")
            if len(corrections["events"]) != family["counts"]["rule_revisions"]:
                fail(f"Revision count differs from dated correction events: {family_id}")
            for revision in corrections["events"]:
                if revision["revision_id"] not in {event.get("revision_id") for event in timeline["events"]}:
                    fail(f"Revision is absent from family timeline: {family_id}")
            for match, posting in zip(expected_match, expected_posting, strict=True):
                if match["document_id"] != posting["document_id"]:
                    fail(f"Match/posting oracle order differs: {family_id}")
                po, receipt = sources["purchase_order"], sources["purchase_receipt"]
                if match["po_allocation"] not in {f"{po['source_id']}:{line['source_line_id']}" for line in po["lines"]} \
                        or match["receipt_allocation"] not in {f"{receipt['source_id']}:{line['source_line_id']}" for line in receipt["lines"]}:
                    fail(f"Source allocation oracle differs from procurement: {family_id}")
                ready = not match["issue_codes"]
                if ready != posting["eligible_submission"] or \
                        match["expected_action"] != ("submit" if ready else "hold"):
                    fail(f"Match and posting expectations disagree: {family_id}")
                eligible += int(ready)
                clean += int(ready and match["category"] == "clean")
                code_set = set(match["issue_codes"])
                categories["quantity"] += int("quantity_exceeds_available" in code_set)
                categories["price"] += int("price_variance" in code_set)
                categories["receipt"] += int("receipt_shortfall" in code_set)
                categories["duplicate"] += int("duplicate_confirmed" in code_set)
            count = family["counts"]
            if set(count) != COUNT_KEYS or count["families"] != 1 or count["invoices"] != len(labels) \
                    or count["lines"] != sum(len(x["line_items"]) for x in labels) \
                    or count["erp_operations"] != sum(x["eligible_submission"] for x in expected_posting):
                fail(f"Family counts disagree with oracle: {family_id}")
            invoices += count["invoices"]
            lines += count["lines"]
            pairs += count["duplicate_pairs"]
            operations += count["erp_operations"]
            revisions += count["rule_revisions"]
        actual = {"families": len(families), "invoices": invoices, "lines": lines,
                  "duplicate_pairs": pairs, "supplier_layouts": len(layout_ids),
                  "rule_revisions": revisions, "erp_operations": operations}
        if cohort["actual_counts"] != actual:
            fail(f"Actual cohort counts disagree with manifest: {split}")
        if status == "sealed" and split == "quality_holdout":
            if any(categories[category] < 10 for category in ("quantity", "price", "receipt", "duplicate")) \
                    or clean < 10 or eligible < 10:
                fail("Quality holdout lacks required positive, clean or eligible cases")
        if status == "sealed" and split == "development" and revisions < 3:
            fail("Development lacks three dated supplier or purchasing-rule revisions")
        if status == "sealed" and split == "time_study" and (eligible < 10 or len(records) - eligible < 10):
            fail("Time study lacks ten eligible and ten exception outcomes")
        report["cohorts"][split] = {**actual, "category_positives": dict(categories),
                                    "clean_ready": clean, "eligible": eligible}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--require-sealed", action="store_true")
    parser.add_argument("--skip-pdf-text", action="store_true", help="Fast hash/count check only")
    args = parser.parse_args()
    print(json.dumps(audit(args.pack, require_sealed=args.require_sealed,
                           inspect_pdf_text=not args.skip_pdf_text), indent=2))


if __name__ == "__main__":
    main()
