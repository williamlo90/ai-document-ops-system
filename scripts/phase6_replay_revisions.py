"""Replay three dated development changes against the real evidence and match services."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.security import SecurityContext  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.integrations.erpnext_client import ERPNextClient  # noqa: E402
from app.documents.models import DocumentRecord  # noqa: E402
from app.documents.repositories import InMemoryDocumentRepository, InMemoryExtractionRepository  # noqa: E402
from app.documents.sqlite_store import SqliteStore  # noqa: E402
from app.extraction.schemas import InvoiceExtraction  # noqa: E402
from app.procurement.matching import MatchService  # noqa: E402
from app.procurement.models import EvidenceUpdate, FieldEvidence, Mapping, MatchPolicy, Policy, SnapshotInput  # noqa: E402
from app.procurement.models import ERPPostingProfile  # noqa: E402
from app.procurement.posting import PostingService  # noqa: E402
from app.procurement.repository import VersionRepository  # noqa: E402
from app.procurement.service import EvidenceService  # noqa: E402
from app.providers.contracts import ExtractionResult  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402
from phase6_reference_match import invoice_data, run as reference_run  # noqa: E402
from phase6_validate_pack import audit, load_json  # noqa: E402
from phase6_end_to_end import independent_readback  # noqa: E402

COMPANY = "Invoice Review Assisted Benchmark"


def run_revision(pack: Path, family: dict, erp=None, profile=None) -> dict:
    directory = pack / "development" / family["family_id"]
    revision = load_json(directory / "corrections.json")["events"][0]
    label = load_json(directory / "invoice-labels.json")[0]
    source = load_json(directory / "procurement.json")
    expectation = load_json(directory / "expected-match.json")[0]
    po, receipt = source["purchase_order"], source["purchase_receipt"]
    item = po["lines"][0]["item_id"]
    aliases = {po["supplier_id"]: po["supplier_id"]}
    if revision["kind"] == "supplier_alias_change":
        label["vendor_name"] = revision["new_vendor_name"]
    admin = SecurityContext("Phase 6 replay admin", role="admin", is_admin=True)
    reviewer = SecurityContext("Phase 6 replay reviewer", role="reviewer")
    approver = SecurityContext("Phase 6 replay approver", role="ap_approver")
    if erp is not None:
        persistent = pack.parent / "phase6-replay-state" / (family["family_id"] + "-" + uuid4().hex[:8])
        persistent.mkdir(parents=True)
        state_context = nullcontext(str(persistent))
    else:
        state_context = tempfile.TemporaryDirectory()
    with state_context as temporary:
        store = SqliteStore(Path(temporary) / "replay.db")
        try:
            documents = InMemoryDocumentRepository()
            extractions = InMemoryExtractionRepository()
            evidence = EvidenceService(VersionRepository(store), documents, extractions)
            matcher = MatchService(evidence)
            evidence.configure("mapping", Mapping(company=COMPANY, supplier_aliases=aliases,
                item_mappings={item: item}, reason="Initial synthetic supplier master"), admin)
            evidence.configure("policy", Policy(company=COMPANY, currency="USD",
                reason="Synthetic reference currency policy"), admin)
            matcher.configure_policy(MatchPolicy(company=COMPANY,
                effective_from=datetime(2026, 1, 1, tzinfo=UTC), mode="ordered",
                reason="Initial zero-tolerance purchasing rule"), admin)
            evidence.import_records([po, receipt], admin)
            document = DocumentRecord(original_filename="synthetic.pdf", storage_key=label["document_id"],
                                      content_type="application/pdf")
            documents.save(document)
            data = invoice_data(label)
            extractions.save(document.id, ExtractionResult(InvoiceExtraction(data), "phase6_reference"),
                             validate_invoice(data))
            revision_row = evidence.capture(document.id, reviewer)
            fields = {path: FieldEvidence(kind="observed", raw=str(value["effective"]),
                effective=value["effective"], page=1, excerpt=str(value["effective"]))
                for path, value in revision_row["fields"].items() if value["effective"] is not None}
            revision_row = evidence.attest(document.id, EvidenceUpdate(
                expected_revision=revision_row["version"], fields=fields,
                reason="Reviewer verified synthetic reference"), reviewer)

            def take_snapshot():
                return evidence.snapshot(document.id, SnapshotInput(company=COMPANY,
                    expected_revision=revision_row["version"], source_system="erpnext",
                    po_ids=[po["source_id"]], receipt_ids=[receipt["source_id"]],
                    allocations={"L1": expectation["po_allocation"]}), reviewer)

            before_snapshot = take_snapshot()
            before_blockers = before_snapshot["blockers"]
            before_match = None
            if not before_blockers:
                evidence.approve(before_snapshot["id"], before_snapshot["payload_hash"], approver)
                before_match = matcher.assess(before_snapshot["id"], reviewer)
            before_action = "hold" if before_blockers or before_match["recommendation"] != "ready_for_approval" else "submit"
            if revision["kind"] == "supplier_alias_change":
                aliases[revision["new_vendor_name"]] = po["supplier_id"]
                evidence.configure("mapping", Mapping(company=COMPANY, supplier_aliases=aliases,
                    item_mappings={item: item}, reason="Dated supplier alias correction"), admin)
            elif revision["kind"] == "price_tolerance_change":
                matcher.configure_policy(MatchPolicy(company=COMPANY,
                    effective_from=datetime.fromisoformat(revision["at"]), mode="ordered",
                    price_tolerance_absolute=revision["absolute_tolerance"],
                    reason="Dated approved price tolerance"), admin)
            else:
                if "corrected_purchase_receipt" in source:
                    corrected = source["corrected_purchase_receipt"]
                    po = source["corrected_purchase_order"]
                    evidence.import_records([po, corrected], admin, refresh_unchanged=True)
                else:
                    corrected = json.loads(json.dumps(receipt))
                    corrected["source_version"] = revision["at"]
                    corrected["source_updated_at"] = revision["at"]
                    corrected["lines"][0]["quantity"] = revision["corrected_received_quantity"]
                    corrected["lines"][0]["amount"] = str(Decimal(corrected["lines"][0]["quantity"])
                                                          * Decimal(corrected["lines"][0]["unit_price"]))
                    evidence.import_records([corrected], admin)
                receipt = corrected
            stale = (evidence.approval_status(before_snapshot["id"], reviewer)["status"] == "stale"
                     if not before_blockers else None)
            old_match_stale = (matcher.status(before_match["id"], reviewer)["status"] == "stale"
                               if before_match else None)
            after_snapshot = take_snapshot()
            after_blockers = after_snapshot["blockers"]
            after_match = None
            if not after_blockers:
                evidence.approve(after_snapshot["id"], after_snapshot["payload_hash"], approver)
                after_match = matcher.assess(after_snapshot["id"], reviewer)
            after_action = "hold" if after_blockers or after_match["recommendation"] != "ready_for_approval" else "submit"
            if after_action == "submit":
                matcher.approve(after_match["id"], after_match["basis_hash"], approver)
            posting_result = {"status": "not_measured"}
            if erp is not None and after_action == "submit":
                posting = PostingService(evidence, erp, sandbox_enabled=True)
                posting.configure_profile(ERPPostingProfile.model_validate(profile), admin)
                draft = posting.create_draft(after_match["id"], after_match["basis_hash"], {}, approver)
                posting_result = {"status": "draft_" + draft["state"], "target": draft.get("target"),
                                  "error_code": draft.get("error_code"), "error_detail": draft.get("error_detail")}
                if draft["state"] == "confirmed":
                    approval = posting.approve_submit(after_match["id"], draft["id"], draft["verification_hash"],
                        "Synthetic revision fixture independently reviewed before sandbox submit", approver)
                    submitted = posting.submit_draft(after_match["id"], approval["approval_hash"], approver)
                    posting_result.update(status="submit_" + submitted["state"], posted_verified=submitted.get("posted_verified", False),
                                          error_code=submitted.get("error_code"), error_detail=submitted.get("error_detail"))
                    actual = erp.get_purchase_invoice(submitted["target"])
                    if actual.get("docstatus") == 1:
                        oracle_source = {"purchase_order": po, "purchase_receipt": receipt}
                        mismatches = independent_readback(label, oracle_source, profile, actual, erp.get_gl_entries(submitted["target"]))
                        posting_result["oracle_mismatches"] = mismatches
                        posting_result["independently_verified"] = not mismatches
                    posting_result["erp_target_count"] = len(erp.find_purchase_invoices_by_delivery_key(draft["idempotency_key"]))
            return {"revision_id": revision["revision_id"], "at": revision["at"],
                    "kind": revision["kind"], "before_action": before_action,
                    "after_action": after_action, "expected_before": "hold",
                    "expected_after": "submit", "before_issue_codes": sorted({i["code"] for i in before_match["issues"]}) if before_match else [],
                    "after_issue_codes": sorted({i["code"] for i in after_match["issues"]}) if after_match else [],
                    "before_blockers": before_blockers, "after_blockers": after_blockers,
                    "old_snapshot_stale": stale, "old_match_stale": old_match_stale,
                    "approval_after": after_action == "submit", "posting_verification": posting_result,
                    "persistent_state": str(Path(temporary) / "replay.db") if erp else None,
                    "correct": before_action == "hold" and after_action == "submit"}
        finally:
            store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-erp", action="store_true")
    parser.add_argument("--revision-id", help="Isolated development diagnostic only")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite replay output")
    audit(args.pack, inspect_pdf_text=False)
    families = next(c["families"] for c in load_json(args.pack / "manifest.json")["cohorts"]
                    if c["split"] == "development")
    revised = [family for family in families if family["counts"]["rule_revisions"]]
    if len(revised) < 3:
        raise SystemExit("Three development revisions are required")
    if args.revision_id:
        revised = [family for family in revised if any(revision["revision_id"] == args.revision_id
                   for revision in load_json(args.pack / "development" / family["family_id"] / "corrections.json")["events"])]
        if len(revised) != 1:
            raise SystemExit("Unknown development revision")
    erp = profile = None
    if args.verify_erp:
        from urllib.parse import urlparse
        settings = load_settings()
        if (not settings.accounting_sandbox_mode or not settings.erpnext_sandbox_posting_enabled
                or urlparse(settings.erpnext_base_url).hostname not in {"localhost", "127.0.0.1"}):
            raise SystemExit("Explicit local ERP sandbox flags required")
        erp = ERPNextClient(settings.erpnext_base_url, api_key=settings.erpnext_api_key,
            api_secret=settings.erpnext_api_secret, allowed_hosts=settings.erpnext_allowed_hosts, timeout_seconds=60)
        profile = load_json(args.pack / "erp-profile.json")
    observations = [run_revision(args.pack, family, erp, profile) for family in revised]
    baseline = reference_run(args.pack, "development")
    regressions = []
    applied = []
    changed_ids = set()
    for family, observation in zip(revised, observations, strict=True):
        applied.append(observation["revision_id"])
        changed_ids.update(label["document_id"] for label in
                           load_json(args.pack / "development" / family["family_id"] / "invoice-labels.json"))
        replay = reference_run(args.pack, "development", tuple(applied))
        unaffected = [row for row in replay["observations"] if row["document_id"] not in changed_ids]
        regressions.append({"revision_id": observation["revision_id"], "scheduled": replay["scheduled"],
            "exact_issue_set": replay["exact_issue_set"], "unaffected_scheduled": len(unaffected),
            "unaffected_retained": sum(row["expected_issue_codes"] == row["actual_issue_codes"] for row in unaffected)})
    report = {"scope": "development reference input, dated service replay" + (" + local ERP/ledger verification" if erp else "; no OCR or ERP write"),
              "revisions": observations, "correct": sum(row["correct"] for row in observations),
              "scheduled": len(observations),
              "baseline": {"scheduled": baseline["scheduled"], "exact_issue_set": baseline["exact_issue_set"]},
              "cumulative_regression": regressions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
