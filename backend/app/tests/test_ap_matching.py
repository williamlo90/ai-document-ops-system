from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.core.security import SecurityContext, UnauthorizedError
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    NotFoundError,
)
from app.documents.sqlite_store import SqliteStore
from app.extraction.schemas import InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.procurement.matching import MatchService
from app.procurement.models import (
    EvidenceUpdate,
    FieldEvidence,
    Mapping,
    MatchPolicy,
    Policy,
    SnapshotInput,
)
from app.procurement.repository import VersionRepository
from app.procurement.service import EvidenceConflict, EvidenceService
from app.providers.contracts import ExtractionResult
from app.validation.invoice import validate_invoice


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SqliteStore(Path(self.temp.name) / "match.db")
        self.addCleanup(self.store.close)
        self.repo = VersionRepository(self.store)
        self.docs = InMemoryDocumentRepository()
        self.extractions = InMemoryExtractionRepository()
        self.evidence = EvidenceService(self.repo, self.docs, self.extractions)
        self.match = MatchService(self.evidence)
        self.admin = SecurityContext("Admin", role="admin", is_admin=True)
        self.reviewer = SecurityContext("Reviewer", role="reviewer")
        self.approver = SecurityContext("Approver", role="ap_approver")
        self.evidence.configure(
            "mapping",
            Mapping(
                company="AC",
                supplier_aliases={"Vendor": "SUP"},
                item_mappings={"Widget": "W"},
                reason="Verified master",
            ),
            self.admin,
        )
        self.evidence.configure(
            "policy",
            Policy(company="AC", currency="USD", reason="Verified source policy"),
            self.admin,
        )
        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                reason="Exact received quantity",
            ),
            self.admin,
        )
        self.source("po", "PO1", "p1", "100", "5000")
        self.source("receipt", "R1", "r1", "70", "3500")

    def source(
        self,
        kind,
        source_id,
        line_id,
        qty,
        amount,
        *,
        version="1",
        status="submitted",
        uom="EA",
        po_id="PO1",
        po_line_id="p1",
    ):
        record = {
            "company": "AC",
            "kind": kind,
            "source_system": "manual",
            "source_id": source_id,
            "source_version": version,
            "supplier_id": "SUP",
            "currency": "USD",
            "status": status,
            "source_updated_at": datetime.now(UTC).isoformat(),
            "lines": [
                {
                    "source_line_id": line_id,
                    "item_id": "W",
                    "uom": uom,
                    "quantity": qty,
                    "unit_price": "50",
                    "amount": amount,
                    **({"po_id": po_id, "po_line_id": po_line_id} if kind == "receipt" else {}),
                }
            ],
        }
        return self.evidence.import_records([record], self.admin)[0]

    def invoice(self, quantity="20", price="50", *, line_id="l1", second_quantity=None):
        doc = DocumentRecord(
            original_filename="synthetic.pdf",
            storage_key="synthetic",
            content_type="application/pdf",
        )
        self.docs.save(doc)
        amount = Decimal(quantity) * Decimal(price)
        if second_quantity is not None:
            amount += Decimal(second_quantity) * Decimal(price)
        lines = [
            InvoiceLineItem(
                description="Widget",
                uom="EA",
                line_id=line_id,
                quantity=Decimal(quantity),
                unit_price=Decimal(price),
                amount=Decimal(quantity) * Decimal(price),
            )
        ]
        if second_quantity is not None:
            lines.append(
                InvoiceLineItem(
                    description="Widget",
                    uom="EA",
                    line_id="l2",
                    quantity=Decimal(second_quantity),
                    unit_price=Decimal(price),
                    amount=Decimal(second_quantity) * Decimal(price),
                )
            )
        data = InvoiceData(
            vendor_name="Vendor",
            invoice_number=f"I-{doc.id}",
            invoice_date=date(2026, 10, 14),
            subtotal=amount,
            tax=Decimal(0),
            total=amount,
            currency="USD",
            line_items=tuple(lines),
        )
        self.extractions.save(
            doc.id, ExtractionResult(InvoiceExtraction(data), "test"), validate_invoice(data)
        )
        revision = self.evidence.capture(doc.id, self.reviewer)
        fields = {
            path: FieldEvidence(
                kind="observed",
                raw=str(v["effective"]),
                effective=v["effective"],
                page=1,
                excerpt=str(v["effective"]),
            )
            for path, v in revision["fields"].items()
            if v["effective"] is not None
        }
        revision = self.evidence.attest(
            doc.id,
            EvidenceUpdate(
                expected_revision=revision["version"],
                fields=fields,
                reason="Synthetic verified fixture",
            ),
            self.reviewer,
        )
        request = SnapshotInput(
            company="AC",
            expected_revision=revision["version"],
            source_system="manual",
            po_ids=["PO1"],
            receipt_ids=["R1"],
            allocations={line.line_id: "PO1:p1" for line in lines},
        )
        snapshot = self.evidence.snapshot(doc.id, request, self.reviewer)
        self.assertEqual(snapshot["blockers"], [])
        self.evidence.approve(snapshot["id"], snapshot["payload_hash"], self.approver)
        return doc, snapshot

    def test_price_and_receipt_variance_are_separate(self):
        _, snapshot = self.invoice("100", "55")
        result = self.match.assess(snapshot["id"], self.reviewer)
        codes = {i["code"] for i in result["issues"]}
        self.assertIn("price_variance", codes)
        self.assertIn("quantity_exceeds_available", codes)
        self.assertEqual(result["lines"][0]["price_delta"], "5")
        self.assertEqual(result["lines"][0]["received"], "70")
        self.assertEqual(result["recommendation"], "hold")
        with self.assertRaises(EvidenceConflict):
            self.match.approve(result["id"], result["basis_hash"], self.approver)

    def test_effective_policy_price_threshold_boundary(self):
        _, snapshot = self.invoice("1", "55")
        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                price_tolerance_absolute="4.99",
                reason="Narrow tolerance",
            ),
            self.admin,
        )
        narrow = self.match.assess(snapshot["id"], self.reviewer)
        self.assertIn("price_variance", {i["code"] for i in narrow["issues"]})
        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                price_tolerance_absolute="5",
                reason="Approved wider tolerance",
            ),
            self.admin,
        )
        wide = self.match.assess(snapshot["id"], self.reviewer)
        self.assertEqual(wide["recommendation"], "ready_for_approval")
        self.assertEqual(self.match.status(narrow["id"], self.approver)["status"], "stale")

    def test_committed_billing_and_reservation_prevent_overallocation(self):
        self.match.import_billings(
            [
                {
                    "company": "AC",
                    "source_system": "manual",
                    "billing_id": "B1",
                    "source_version": "1",
                    "source_updated_at": datetime.now(UTC).isoformat(),
                    "po_id": "PO1",
                    "po_line_id": "p1",
                    "quantity": "50",
                    "uom": "EA",
                    "status": "committed",
                }
            ],
            self.admin,
        )
        _, snapshot = self.invoice("30")
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.assertEqual(result["lines"][0]["available"], "20")
        self.assertEqual(result["recommendation"], "hold")

    def test_quantity_boundary_never_reports_unsafe_ready(self):
        for qty in ("1", "20", "69", "70", "70.00000001", "71", "100"):
            with self.subTest(qty=qty):
                _, snapshot = self.invoice(qty)
                result = self.match.assess(snapshot["id"], self.reviewer)
                self.assertEqual(
                    result["recommendation"] == "ready_for_approval", Decimal(qty) <= 70
                )
                if Decimal(qty) > 70:
                    with self.assertRaises(EvidenceConflict):
                        self.match.approve(result["id"], result["basis_hash"], self.approver)

    def test_repeated_item_lines_share_one_po_capacity(self):
        _, snapshot = self.invoice("40", second_quantity="40")
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.assertEqual(len(result["lines"]), 2)
        self.assertEqual(result["quantities"]['["PO1","p1"]'], "80")
        self.assertEqual(result["recommendation"], "hold")

    def test_split_receipts_and_two_purchase_orders(self):
        self.source("receipt", "R2", "r2", "20", "1000")
        self.source("po", "PO2", "p2", "30", "1500")
        self.source("receipt", "R3", "r3", "30", "1500", po_id="PO2", po_line_id="p2")
        _, original = self.invoice("20", second_quantity="30")
        request = SnapshotInput(
            company="AC",
            expected_revision=original["inputs"]["invoice"]["version"],
            source_system="manual",
            po_ids=["PO1", "PO2"],
            receipt_ids=["R1", "R2", "R3"],
            allocations={"l1": "PO1:p1", "l2": "PO2:p2"},
        )
        updated = self.evidence.snapshot(original["document_id"], request, self.reviewer)
        self.assertEqual(updated["blockers"], [])
        self.evidence.approve(updated["id"], updated["payload_hash"], self.approver)
        result = self.match.assess(updated["id"], self.reviewer)
        self.assertEqual(result["recommendation"], "ready_for_approval")
        self.assertEqual({r["source_ref"] for r in result["lines"]}, {"PO1:p1", "PO2:p2"})
        self.assertEqual(result["lines"][0]["received"], "90")

    def test_receipt_uom_mismatch_cannot_expand_capacity(self):
        self.source("receipt", "R1", "r1", "70", "3500", version="2", uom="BOX")
        _, snapshot = self.invoice("20")
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.assertIn("receipt_uom_mismatch", {i["code"] for i in result["issues"]})
        self.assertEqual(result["lines"][0]["received"], "0")
        self.assertNotEqual(result["recommendation"], "ready_for_approval")

    def test_unverified_line_tax_requires_review(self):
        doc, original = self.invoice("20")
        data = self.extractions.get_for_document(doc.id).extraction_result.extraction.data
        corrected = replace(
            data,
            tax=Decimal("2"),
            total=Decimal("1002"),
            line_items=(replace(data.line_items[0], tax=Decimal("2")),),
        )
        self.extractions.save(
            doc.id,
            ExtractionResult(InvoiceExtraction(corrected), "test"),
            validate_invoice(corrected),
        )
        revision = self.evidence.capture(doc.id, self.reviewer)
        fields = {
            path: FieldEvidence(
                kind="observed",
                raw=str(v["effective"]),
                effective=v["effective"],
                page=1,
                excerpt=str(v["effective"]),
            )
            for path, v in revision["fields"].items()
            if v["effective"] is not None and v["kind"] == "unknown"
        }
        revision = self.evidence.attest(
            doc.id,
            EvidenceUpdate(
                expected_revision=revision["version"], fields=fields, reason="Synthetic tax review"
            ),
            self.reviewer,
        )
        request = SnapshotInput(
            company="AC",
            expected_revision=revision["version"],
            source_system="manual",
            po_ids=["PO1"],
            receipt_ids=["R1"],
            allocations={"l1": "PO1:p1"},
        )
        snapshot = self.evidence.snapshot(doc.id, request, self.reviewer)
        self.evidence.approve(snapshot["id"], snapshot["payload_hash"], self.approver)
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.assertIn("unverified_line_tax", {i["code"] for i in result["issues"]})
        self.assertEqual(result["recommendation"], "needs_review")

    def test_missing_source_is_visible_and_never_approved(self):
        _, existing = self.invoice("20")
        for po_ids, receipt_ids, code in (
            ([], ["R1"], "missing_po_source"),
            (["PO1"], ["absent"], "missing_receipt_source:absent"),
        ):
            with self.subTest(code=code):
                request = SnapshotInput(
                    company="AC",
                    expected_revision=existing["inputs"]["invoice"]["version"],
                    source_system="manual",
                    po_ids=po_ids,
                    receipt_ids=receipt_ids,
                    allocations={"l1": "PO1:p1"},
                )
                snap = self.evidence.snapshot(existing["document_id"], request, self.reviewer)
                self.assertIn(code, snap["blockers"])
                match = self.match.assess(snap["id"], self.reviewer)
                self.assertEqual(match["recommendation"], "assessment_incomplete")
                with self.assertRaises(EvidenceConflict):
                    self.match.approve(match["id"], match["basis_hash"], self.approver)

    def test_sequential_and_concurrent_approvals(self):
        _, first_snapshot = self.invoice("50")
        first = self.match.assess(first_snapshot["id"], self.reviewer)
        self.assertEqual(first["recommendation"], "ready_for_approval")
        self.match.approve(first["id"], first["basis_hash"], self.approver)
        self.assertEqual(self.match.status(first["id"], self.approver)["status"], "approved")
        _, next_snapshot = self.invoice("30")
        next_match = self.match.assess(next_snapshot["id"], self.reviewer)
        self.assertEqual(next_match["lines"][0]["available"], "20")
        self.assertEqual(next_match["recommendation"], "hold")
        self.match.release(
            first["id"], "Reconciled synthetic cancellation", "ERP-CANCEL-1", self.admin
        )
        self.assertEqual(self.match.status(first["id"], self.approver)["status"], "released")
        left, left_snap = self.invoice("40")
        right, right_snap = self.invoice("40")
        candidates = [self.match.assess(s["id"], self.reviewer) for s in (left_snap, right_snap)]

        def approve(match):
            try:
                self.match.approve(match["id"], match["basis_hash"], self.approver)
                return True
            except EvidenceConflict:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(approve, candidates)), [False, True])
        active = [
            r for r in self.repo.all_latest("default", "reservation") if r["status"] == "active"
        ]
        self.assertEqual(sum(Decimal(r["quantity"]) for r in active), Decimal("40"))
        self.assertNotEqual(left.id, right.id)

    def test_reservation_survives_new_repository_and_policy_change(self):
        _, snapshot = self.invoice("60")
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.match.approve(result["id"], result["basis_hash"], self.approver)
        if isinstance(self.repo.store, SqliteStore):
            other = SqliteStore(Path(self.temp.name) / "match.db")
        else:
            from app.postgres.store import PostgresStore

            other = PostgresStore(self.repo.store.database_url, pool_size=1)
        try:
            rows = VersionRepository(other).all_latest("default", "reservation")
            self.assertEqual([r["quantity"] for r in rows if r["status"] == "active"], ["60"])
        finally:
            other.close()
        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                reason="Policy revision",
            ),
            self.admin,
        )
        self.assertEqual(self.match.status(result["id"], self.approver)["status"], "stale")
        self.assertEqual(self.repo.all_latest("default", "reservation")[0]["status"], "active")

    def test_policy_revision_and_cancelled_receipt_stale_match(self):
        _, snapshot = self.invoice("20")
        result = self.match.assess(snapshot["id"], self.reviewer)
        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                price_tolerance_absolute="2",
                reason="Revised tolerance",
            ),
            self.admin,
        )
        self.assertEqual(self.match.status(result["id"], self.approver)["status"], "stale")
        with self.assertRaises(EvidenceConflict):
            self.match.approve(result["id"], result["basis_hash"], self.approver)
        self.source("receipt", "R1", "r1", "70", "3500", version="2", status="cancelled")
        newer = self.match.assess(snapshot["id"], self.reviewer)
        self.assertEqual(newer["recommendation"], "assessment_incomplete")
        self.assertFalse(self.match.status(newer["id"], self.approver)["posting_ready"])

    def test_role_workspace_and_billing_version_boundaries(self):
        _, snapshot = self.invoice("20")
        result = self.match.assess(snapshot["id"], self.reviewer)
        with self.assertRaises(UnauthorizedError):
            self.match.approve(result["id"], result["basis_hash"], self.reviewer)
        outsider = SecurityContext("Outsider", role="ap_approver", workspace_id="other")
        with self.assertRaises(NotFoundError):
            self.match.status(result["id"], outsider)
        row = {
            "company": "AC",
            "source_system": "manual",
            "billing_id": "B1",
            "source_version": "1",
            "source_updated_at": datetime.now(UTC).isoformat(),
            "po_id": "PO1",
            "po_line_id": "p1",
            "quantity": "1",
            "uom": "EA",
            "status": "committed",
        }
        self.match.import_billings([row], self.admin)
        with self.assertRaises(EvidenceConflict):
            self.match.import_billings([row], self.admin)

    def test_match_api_exposes_lines_and_blocks_stale_approval(self):
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        from app.api.dependencies import get_container, require_authenticated_context
        from app.core.settings import Settings
        from app.main import create_app

        doc, snapshot = self.invoice("20")
        app = create_app(Settings("test", "admin-token", Path(self.temp.name), 10000))
        self.addCleanup(app.state.container.close)
        app.dependency_overrides[get_container] = lambda: SimpleNamespace(ap_service=self.evidence)
        app.dependency_overrides[require_authenticated_context] = lambda: self.admin
        client = TestClient(app)
        result = client.post(f"/ap/snapshots/{snapshot['id']}/match")
        self.assertEqual(result.status_code, 200, result.text)
        match = result.json()
        view = client.get(f"/ap/invoices/{doc.id}")
        self.assertEqual(view.status_code, 200, view.text)
        self.assertEqual(view.json()["match_status"]["match"]["id"], match["id"])
        self.assertEqual(len(view.json()["match_status"]["match"]["lines"]), 1)
        self.source("receipt", "R1", "r1", "70", "3500", version="2", status="cancelled")
        denied = client.post(
            f"/ap/matches/{match['id']}/approve", json={"basis_hash": match["basis_hash"]}
        )
        self.assertEqual(denied.status_code, 409, denied.text)
