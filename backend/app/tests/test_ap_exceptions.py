from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.core.security import UnauthorizedError
from app.extraction.schemas import InvoiceExtraction
from app.procurement.exceptions import ExceptionService
from app.procurement.models import (
    EvidenceUpdate,
    ExceptionPolicy,
    ExceptionUpdate,
    FieldEvidence,
    Mapping,
    SnapshotInput,
)
from app.procurement.service import EvidenceConflict
from app.providers.contracts import ExtractionResult
from app.tests import test_ap_matching as fixture
from app.validation.invoice import validate_invoice


class ExceptionTests(unittest.TestCase):
    setUp = fixture.MatchTests.setUp
    source = fixture.MatchTests.source
    invoice = fixture.MatchTests.invoice

    def revise(self, doc, **changes):
        old = self.extractions.get_for_document(doc.id).extraction_result.extraction.data
        updated = replace(old, **changes)
        self.extractions.save(
            doc.id, ExtractionResult(InvoiceExtraction(updated), "test"), validate_invoice(updated)
        )
        revision = self.evidence.capture(doc.id, self.reviewer)
        unknown = {
            path: FieldEvidence(
                kind="observed",
                raw=str(value["effective"]),
                effective=value["effective"],
                page=1,
                excerpt=str(value["effective"]),
            )
            for path, value in revision["fields"].items()
            if value["effective"] is not None and value["kind"] == "unknown"
        }
        if unknown:
            revision = self.evidence.attest(
                doc.id,
                EvidenceUpdate(
                    expected_revision=revision["version"],
                    fields=unknown,
                    reason="Verified revised fixture",
                ),
                self.reviewer,
            )
        request = SnapshotInput(
            company="AC",
            expected_revision=revision["version"],
            source_system="manual",
            po_ids=["PO1"],
            receipt_ids=["R1"],
            allocations={line.line_id: "PO1:p1" for line in updated.line_items},
        )
        snapshot = self.evidence.snapshot(doc.id, request, self.reviewer)
        if not snapshot["blockers"]:
            self.evidence.approve(snapshot["id"], snapshot["payload_hash"], self.approver)
        return snapshot

    def decision(self, case, state, *, owner="Reviewer", ref="source:fixture"):
        return ExceptionUpdate(
            expected_version=case["version"],
            expected_match_id=case["match_id"],
            state=state,
            owner=owner,
            reason="Verified against the source invoice",
            evidence_refs=[ref],
        )

    def test_final_rejection_requires_approver_and_never_enables_posting(self):
        doc, snapshot = self.invoice("80")
        match = self.match.assess(snapshot["id"], self.reviewer)
        service = ExceptionService(self.evidence)
        cases = service.list_cases(self.reviewer, document_id=doc.id)
        self.assertTrue(cases)
        for case in cases:
            with self.assertRaises(UnauthorizedError):
                service.update(
                    case["id"], self.decision(case, "rejected"), self.reviewer, self.match
                )
            rejected = service.update(
                case["id"], self.decision(case, "rejected"), self.approver, self.match
            )
            self.assertEqual(rejected["authorizer"], self.approver.actor)
        status = self.match.status(match["id"], self.reviewer)
        self.assertEqual(status["status"], "rejected")
        self.assertFalse(status["posting_ready"])
        with self.assertRaises(EvidenceConflict):
            self.match.approve(match["id"], match["basis_hash"], self.approver)
        with self.assertRaises(ValueError):
            self.decision(cases[0], "rejected", ref="")

    def test_rejection_survives_same_basis_but_new_revision_reopens_issue(self):
        doc, snapshot = self.invoice("80")
        self.match.assess(snapshot["id"], self.reviewer)
        service = ExceptionService(self.evidence)
        for case in service.list_cases(self.reviewer, document_id=doc.id):
            rejected = service.update(
                case["id"], self.decision(case, "rejected"), self.approver, self.match
            )
            with self.assertRaises(EvidenceConflict):
                service.update(
                    case["id"], self.decision(rejected, "needs_info"), self.reviewer, self.match
                )
        repeated = self.match.assess(snapshot["id"], self.reviewer)
        self.assertEqual(self.match.status(repeated["id"], self.reviewer)["status"], "rejected")
        revised = self.revise(doc, invoice_number="REVISED-900")
        self.match.assess(revised["id"], self.reviewer)
        current = service.list_cases(self.reviewer, document_id=doc.id)
        self.assertTrue(
            all(case["state"] == "open" and case["authorizer"] is None for case in current)
        )

    def test_approved_or_remote_operation_requires_reconciliation_before_rejection(self):
        doc, snapshot = self.invoice("1", "55")
        service = ExceptionService(self.evidence)
        service.configure_policy(
            ExceptionPolicy(
                company="AC",
                allowed_waivers=["price_variance"],
                max_price_delta=Decimal("5"),
                reason="Controlled price waiver",
            ),
            self.admin,
        )
        match = self.match.assess(snapshot["id"], self.reviewer)
        case = next(
            case
            for case in service.list_cases(self.reviewer, document_id=doc.id)
            if case["code"] == "price_variance"
        )
        waived = service.update(case["id"], self.decision(case, "waived"), self.admin, self.match)
        self.match.approve(match["id"], match["basis_hash"], self.approver)
        with self.assertRaises(EvidenceConflict):
            service.update(case["id"], self.decision(waived, "rejected"), self.approver, self.match)

    def test_exact_punctuation_and_ocr_candidate_with_valid_negative_controls(self):
        first, first_snapshot = self.invoice("10")
        first_match = self.match.assess(first_snapshot["id"], self.reviewer)
        number = self.extractions.get_for_document(
            first.id
        ).extraction_result.extraction.data.invoice_number
        second, _ = self.invoice("10")
        punctuated = self.revise(second, invoice_number=number.replace("-", " / "))
        exact = self.match.assess(punctuated["id"], self.reviewer)
        self.assertIn("duplicate_confirmed", {issue["code"] for issue in exact["issues"]})
        self.assertEqual(self.match.status(first_match["id"], self.reviewer)["status"], "stale")
        case = next(
            c
            for c in ExceptionService(self.evidence).list_cases(
                self.reviewer, document_id=second.id
            )
            if c["code"] == "duplicate_confirmed"
        )
        with self.assertRaises(EvidenceConflict):
            ExceptionService(self.evidence).update(
                case["id"], self.decision(case, "resolved"), self.reviewer, self.match
            )
        with self.assertRaises(EvidenceConflict):
            self.match.approve(exact["id"], exact["basis_hash"], self.approver)

        # A single OCR ambiguity is reviewable, not automatically a confirmed duplicate.
        third, _ = self.invoice("10")
        ocr = number.replace("0", "O", 1) if "0" in number else number.replace("I", "1", 1)
        third_snapshot = self.revise(third, invoice_number=ocr)
        candidate = self.match.assess(third_snapshot["id"], self.reviewer)
        self.assertIn("duplicate_candidate", {issue["code"] for issue in candidate["issues"]})
        self.assertNotIn("duplicate_confirmed", {issue["code"] for issue in candidate["issues"]})

        fourth, _ = self.invoice("10")
        different = self.match.assess(
            self.repo.latest_for_document(self.reviewer.workspace_id, "snapshot", fourth.id)["id"],
            self.reviewer,
        )
        self.assertFalse(
            {"duplicate_confirmed", "duplicate_candidate"}
            & {i["code"] for i in different["issues"]}
        )

    def test_incomplete_prior_identity_on_same_po_blocks_copy_approval(self):
        first, _ = self.invoice("10")
        self.revise(first, invoice_number=None, invoice_date=None)
        second, snapshot = self.invoice("10")
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.assertIn("duplicate_candidate", {issue["code"] for issue in result["issues"]})
        self.assertNotIn("duplicate_confirmed", {issue["code"] for issue in result["issues"]})
        with self.assertRaises(EvidenceConflict):
            self.match.approve(result["id"], result["basis_hash"], self.approver)
        self.assertFalse(self.match.status(result["id"], self.reviewer)["posting_ready"])

    def test_incomplete_identity_different_po_or_amount_does_not_hold(self):
        first, _ = self.invoice("10")
        self.revise(first, invoice_number=None, invoice_date=None)
        _, different_amount = self.invoice("11")
        result = self.match.assess(different_amount["id"], self.reviewer)
        self.assertFalse(
            {"duplicate_confirmed", "duplicate_candidate"} & {i["code"] for i in result["issues"]}
        )
        self.source("po", "PO2", "p2", "100", "5000")
        self.source("receipt", "R2", "r2", "70", "3500", po_id="PO2", po_line_id="p2")
        second, _ = self.invoice("10")
        revision = self.repo.latest(self.reviewer.workspace_id, "invoice", str(second.id))
        snapshot = self.evidence.snapshot(
            second.id,
            SnapshotInput(
                company="AC",
                expected_revision=revision["version"],
                source_system="manual",
                po_ids=["PO2"],
                receipt_ids=["R2"],
                allocations={"l1": "PO2:p2"},
            ),
            self.reviewer,
        )
        self.evidence.approve(snapshot["id"], snapshot["payload_hash"], self.approver)
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.assertFalse(
            {"duplicate_confirmed", "duplicate_candidate"} & {i["code"] for i in result["issues"]}
        )

    def test_recurring_invoice_outside_window_and_supplier_alias_boundary(self):
        first, _ = self.invoice("10")
        number = self.extractions.get_for_document(
            first.id
        ).extraction_result.extraction.data.invoice_number
        later, _ = self.invoice("10")
        old_snapshot = self.revise(
            later, invoice_number=number, invoice_date=date(2026, 10, 14) - timedelta(days=60)
        )
        recurring = self.match.assess(old_snapshot["id"], self.reviewer)
        self.assertFalse(
            {"duplicate_confirmed", "duplicate_candidate"}
            & {i["code"] for i in recurring["issues"]}
        )

        self.evidence.configure(
            "mapping",
            Mapping(
                company="AC",
                supplier_aliases={"Vendor": "SUP", "Other Vendor": "OTHER"},
                item_mappings={"Widget": "W"},
                reason="Verified supplier split",
            ),
            self.admin,
        )
        other, _ = self.invoice("10")
        other_snapshot = self.revise(other, invoice_number=number, vendor_name="Other Vendor")
        split = self.match.assess(other_snapshot["id"], self.reviewer)
        self.assertFalse(
            {"duplicate_confirmed", "duplicate_candidate"} & {i["code"] for i in split["issues"]}
        )

    def test_similar_recurring_invoice_on_different_po_is_not_held(self):
        first, _ = self.invoice("10")
        number = self.extractions.get_for_document(
            first.id
        ).extraction_result.extraction.data.invoice_number
        self.source("po", "PO2", "p2", "100", "5000")
        self.source("receipt", "R2", "r2", "70", "3500", po_id="PO2", po_line_id="p2")
        recurring_doc, _ = self.invoice("10")
        self.revise(
            recurring_doc,
            invoice_number=number,
            invoice_date=date(2026, 10, 14) - timedelta(days=20),
        )
        revision = self.repo.latest(self.reviewer.workspace_id, "invoice", str(recurring_doc.id))
        different_po = self.evidence.snapshot(
            recurring_doc.id,
            SnapshotInput(
                company="AC",
                expected_revision=revision["version"],
                source_system="manual",
                po_ids=["PO2"],
                receipt_ids=["R2"],
                allocations={"l1": "PO2:p2"},
            ),
            self.reviewer,
        )
        self.evidence.approve(different_po["id"], different_po["payload_hash"], self.approver)
        result = self.match.assess(different_po["id"], self.reviewer)
        self.assertEqual(result["recommendation"], "ready_for_approval")
        self.assertFalse(
            {"duplicate_confirmed", "duplicate_candidate"} & {i["code"] for i in result["issues"]}
        )

    def test_waiver_policy_role_and_staleness(self):
        _, snapshot = self.invoice("1", "55")
        match = self.match.assess(snapshot["id"], self.reviewer)
        service = ExceptionService(self.evidence)
        case = next(c for c in service.list_cases(self.reviewer) if c["code"] == "price_variance")
        service.update(case["id"], self.decision(case, "needs_info"), self.reviewer, self.match)
        self.assertEqual(self.match.status(match["id"], self.reviewer)["status"], "hold")
        with self.assertRaises(EvidenceConflict):
            self.match.approve(match["id"], match["basis_hash"], self.approver)
        self.assertFalse(self.match.status(match["id"], self.reviewer)["posting_ready"])

        service.configure_policy(
            ExceptionPolicy(
                company="AC",
                allowed_waivers=["price_variance"],
                max_price_delta=Decimal("5"),
                reason="Controlled price waiver",
            ),
            self.admin,
        )
        match = self.match.assess(snapshot["id"], self.reviewer)
        case = next(c for c in service.list_cases(self.reviewer) if c["code"] == "price_variance")
        with self.assertRaises(UnauthorizedError):
            service.update(case["id"], self.decision(case, "waived"), self.reviewer, self.match)
        service.update(case["id"], self.decision(case, "waived"), self.admin, self.match)
        self.assertEqual(
            self.match.status(match["id"], self.reviewer)["status"], "ready_for_approval"
        )
        self.match.approve(match["id"], match["basis_hash"], self.approver)
        self.assertFalse(self.match.status(match["id"], self.reviewer)["posting_ready"])
        service.configure_policy(
            ExceptionPolicy(company="AC", allowed_waivers=[], reason="Waiver withdrawn"), self.admin
        )
        self.assertEqual(self.match.status(match["id"], self.reviewer)["status"], "stale")

    def test_corrected_source_supersedes_and_resolves_with_audit(self):
        doc, snapshot = self.invoice("80")
        held = self.match.assess(snapshot["id"], self.reviewer)
        service = ExceptionService(self.evidence)
        case = next(
            c
            for c in service.list_cases(self.reviewer)
            if c["code"] == "quantity_exceeds_available"
        )
        with self.assertRaises(EvidenceConflict):
            service.update(case["id"], self.decision(case, "resolved"), self.reviewer, self.match)
        corrected = self.revise(
            doc,
            line_items=(
                replace(
                    self.extractions.get_for_document(
                        doc.id
                    ).extraction_result.extraction.data.line_items[0],
                    quantity=Decimal("20"),
                    amount=Decimal("1000"),
                ),
            ),
            subtotal=Decimal("1000"),
            total=Decimal("1000"),
        )
        self.assertEqual(self.match.status(held["id"], self.reviewer)["status"], "stale")
        clean = self.match.assess(corrected["id"], self.reviewer)
        self.assertEqual(clean["recommendation"], "ready_for_approval")
        case = self.repo.latest(self.reviewer.workspace_id, "ap_exception", case["id"])
        self.assertEqual(case["state"], "superseded")
        resolved = service.update(
            case["id"], self.decision(case, "resolved"), self.reviewer, self.match
        )
        self.assertEqual(resolved["state"], "resolved")
        self.assertEqual(resolved["actor"], "Reviewer")
        self.assertEqual(resolved["evidence_refs"], ["source:fixture"])
        reopened_snapshot = self.revise(
            doc,
            line_items=(
                replace(
                    self.extractions.get_for_document(
                        doc.id
                    ).extraction_result.extraction.data.line_items[0],
                    quantity=Decimal("80"),
                    amount=Decimal("4000"),
                ),
            ),
            subtotal=Decimal("4000"),
            total=Decimal("4000"),
        )
        self.match.assess(reopened_snapshot["id"], self.reviewer)
        reopened = self.repo.latest(self.reviewer.workspace_id, "ap_exception", case["id"])
        self.assertEqual(reopened["state"], "open")
        self.assertGreater(reopened["version"], resolved["version"])

    def test_labeled_fixture_scores_actual_match_output(self):
        outcomes = []

        def score(category, expected, snapshot, positive_codes):
            result = self.match.assess(snapshot["id"], self.reviewer)
            detected = bool({issue["code"] for issue in result["issues"]} & positive_codes)
            outcomes.append((category, expected, detected, result["recommendation"]))
            return result

        baseline_doc, baseline = self.invoice("10")
        score("quantity", False, baseline, {"quantity_exceeds_available"})
        _, normal_price = self.invoice("1")
        score("price", False, normal_price, {"price_variance"})
        _, normal_receipt = self.invoice("1")
        score(
            "receipt",
            False,
            normal_receipt,
            {"receipt_shortfall", "receipt_uom_mismatch", "receipt_item_mismatch"},
        )
        baseline_number = self.extractions.get_for_document(
            baseline_doc.id
        ).extraction_result.extraction.data.invoice_number
        unique_doc, unique = self.invoice("10")
        score("duplicate", False, unique, {"duplicate_confirmed", "duplicate_candidate"})
        self.assertNotEqual(baseline_doc.id, unique_doc.id)

        _, excessive = self.invoice("80")
        score("quantity", True, excessive, {"quantity_exceeds_available"})
        _, expensive = self.invoice("1", "55")
        score("price", True, expensive, {"price_variance"})
        duplicate_doc, _ = self.invoice("10")
        duplicate = self.revise(duplicate_doc, invoice_number=baseline_number)
        score("duplicate", True, duplicate, {"duplicate_confirmed"})

        self.source("receipt", "R1", "r1", "70", "3500", version="2", uom="BOX")
        _, mismatched = self.invoice("1")
        score("receipt", True, mismatched, {"receipt_uom_mismatch", "receipt_item_mismatch"})

        expected_metrics = {
            category: {"TP": 1, "FN": 0, "FP": 0, "TN": 1}
            for category in ("quantity", "price", "receipt", "duplicate")
        }
        metrics = {
            category: {key: 0 for key in ("TP", "FN", "FP", "TN")} for category in expected_metrics
        }
        for category, label, detected, _ in outcomes:
            metrics[category][
                "TP" if label and detected else "FN" if label else "FP" if detected else "TN"
            ] += 1
        self.assertEqual(metrics, expected_metrics)
        false_holds = sum(
            recommendation != "ready_for_approval"
            for _, label, _, recommendation in outcomes
            if not label
        )
        self.assertEqual(false_holds, 0)

    def test_receipt_adjustment_requires_new_snapshot_and_reassessment(self):
        doc, original = self.invoice("80")
        held = self.match.assess(original["id"], self.reviewer)
        self.assertIn("quantity_exceeds_available", {issue["code"] for issue in held["issues"]})
        self.source("receipt", "R1", "r1", "90", "4500", version="2")
        self.assertEqual(self.match.status(held["id"], self.reviewer)["status"], "stale")
        request = SnapshotInput(
            company="AC",
            expected_revision=original["inputs"]["invoice"]["version"],
            source_system="manual",
            po_ids=["PO1"],
            receipt_ids=["R1"],
            allocations={"l1": "PO1:p1"},
        )
        updated = self.evidence.snapshot(doc.id, request, self.reviewer)
        self.evidence.approve(updated["id"], updated["payload_hash"], self.approver)
        clean = self.match.assess(updated["id"], self.reviewer)
        self.assertEqual(clean["recommendation"], "ready_for_approval")
        old_case = next(
            c
            for c in ExceptionService(self.evidence).list_cases(self.reviewer, document_id=doc.id)
            if c["code"] == "quantity_exceeds_available"
        )
        self.assertEqual(old_case["state"], "superseded")


if __name__ == "__main__":
    unittest.main()
