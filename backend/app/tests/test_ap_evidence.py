from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.security import SecurityContext, UnauthorizedError
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    NotFoundError,
)
from app.documents.sqlite_store import SqliteStore
from app.extraction.schemas import InvoiceData, InvoiceExtraction, InvoiceLineItem, FieldConfidence
from app.providers.contracts import ExtractionResult
from app.validation.invoice import validate_invoice
from app.procurement.repository import VersionRepository
from app.procurement.service import EvidenceService, EvidenceConflict, key
from app.procurement.models import (
    Mapping,
    Policy,
    EvidenceUpdate,
    FieldEvidence,
    SnapshotInput,
    ProcurementRecord,
)
from app.procurement.erpnext import read_procurement


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SqliteStore(Path(self.tmp.name) / "db.sqlite")
        self.addCleanup(self.store.close)
        self.repo = VersionRepository(self.store)
        self.docs = InMemoryDocumentRepository()
        self.extractions = InMemoryExtractionRepository()
        self.admin = SecurityContext("Admin", role="admin", is_admin=True)
        self.reviewer = SecurityContext("Reviewer", role="reviewer")
        self.approver = SecurityContext("Approver", role="ap_approver")
        self.doc = DocumentRecord(
            original_filename="invoice.pdf",
            storage_key="invoice.pdf",
            content_type="application/pdf",
        )
        self.docs.save(self.doc)
        self.invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="I-1",
            invoice_date=date(2026, 10, 14),
            subtotal=Decimal("10"),
            tax=Decimal("0"),
            total=Decimal("10"),
            currency="USD",
            line_items=(
                InvoiceLineItem(
                    description="Widget",
                    quantity=Decimal("1"),
                    unit_price=Decimal("10"),
                    amount=Decimal("10"),
                    uom="EA",
                    line_id="line-1",
                ),
            ),
        )
        self.save(self.invoice)
        self.service = EvidenceService(self.repo, self.docs, self.extractions)

    def save(self, data):
        self.extractions.save(
            self.doc.id, ExtractionResult(InvoiceExtraction(data), "test"), validate_invoice(data)
        )

    def test_capture_preserves_line_provider_anchor_without_auto_attestation(self):
        self.extractions.save(
            self.doc.id,
            ExtractionResult(
                InvoiceExtraction(
                    self.invoice,
                    confidence=(
                        FieldConfidence(
                            "line_items[0].quantity",
                            Decimal("1"),
                            source_page=1,
                            source_text="Qty 1",
                        ),
                    ),
                ),
                "test",
            ),
            validate_invoice(self.invoice),
        )
        revision = self.service.capture(self.doc.id, self.reviewer)
        value = revision["fields"]["lines.line-1.quantity"]
        self.assertEqual((value["page"], value["excerpt"]), (1, "Qty 1"))
        self.assertEqual(value["kind"], "unknown")
        self.assertNotEqual(value.get("attestation"), "reviewer_verified")

    def source(self, kind="po", version="1", status="submitted"):
        return {
            "company": "AC",
            "kind": kind,
            "source_system": "manual",
            "source_id": "PO1" if kind == "po" else "R1",
            "source_version": version,
            "supplier_id": "SUP1",
            "currency": "USD",
            "status": status,
            "source_updated_at": datetime.now(UTC).isoformat(),
            "lines": [
                {
                    "source_line_id": "p1" if kind == "po" else "r1",
                    "item_id": "W",
                    "uom": "EA",
                    "quantity": "1",
                    "unit_price": "10",
                    "amount": "10",
                    **({"po_id": "PO1", "po_line_id": "p1"} if kind == "receipt" else {}),
                }
            ],
        }

    def prepare(self):
        s = self.service
        r = s.capture(self.doc.id, self.reviewer)
        updates = {
            p: FieldEvidence(
                kind="corrected",
                raw=str(v["effective"]),
                normalized=v["effective"],
                effective=v["effective"],
                page=1,
                excerpt=str(v["effective"]),
                reason="Checked source",
            )
            for p, v in r["fields"].items()
            if v["effective"] is not None
        }
        r = s.attest(
            self.doc.id,
            EvidenceUpdate(
                expected_revision=r["version"], fields=updates, reason="Verified against PDF"
            ),
            self.reviewer,
        )
        s.configure(
            "mapping",
            Mapping(
                company="AC",
                supplier_aliases={"Acme": "SUP1"},
                item_mappings={"Widget": "W"},
                reason="Master data checked",
            ),
            self.admin,
        )
        s.configure(
            "policy", Policy(company="AC", currency="USD", reason="Same currency only"), self.admin
        )
        s.import_records([self.source(), self.source("receipt")], self.admin)
        request = SnapshotInput(
            company="AC",
            source_system="manual",
            expected_revision=r["version"],
            po_ids=["PO1"],
            receipt_ids=["R1"],
            allocations={"line-1": "PO1:p1"},
        )
        return s.snapshot(self.doc.id, request, self.reviewer)

    def test_immutable_approval_and_cancelled_receipt(self):
        snapshot = self.prepare()
        self.assertEqual(snapshot["blockers"], [])
        approval = self.service.approve(snapshot["id"], snapshot["payload_hash"], self.approver)
        self.assertEqual(
            self.service.approval_status(snapshot["id"], self.approver)["status"], "approved"
        )
        self.service.import_records([self.source("receipt", "2", "cancelled")], self.admin)
        self.assertEqual(
            self.service.approval_status(snapshot["id"], self.approver)["status"], "stale"
        )
        self.assertEqual(self.repo.latest("default", "approval", snapshot["id"]), approval)
        self.assertFalse(
            self.service.approval_status(snapshot["id"], self.approver)["posting_ready"]
        )

    def test_invoice_revision_stales_snapshot_and_preserves_original(self):
        snap = self.prepare()
        original = self.repo.history("default", "invoice", str(self.doc.id))[0]
        self.save(replace(self.invoice, total=Decimal("12")))
        self.assertEqual(self.service.approval_status(snap["id"], self.approver)["status"], "stale")
        self.assertEqual(original, self.repo.history("default", "invoice", str(self.doc.id))[0])
        with self.assertRaises(EvidenceConflict):
            self.service.approve(snap["id"], snap["payload_hash"], self.approver)

    def test_policy_and_mapping_changes_stale(self):
        snap = self.prepare()
        self.service.configure(
            "policy",
            Policy(company="AC", currency="USD", max_age_hours=12, reason="New freshness policy"),
            self.admin,
        )
        self.assertEqual(self.service.approval_status(snap["id"], self.approver)["status"], "stale")

    def test_rbac_tenant_and_hash(self):
        snap = self.prepare()
        with self.assertRaises(UnauthorizedError):
            self.service.approve(snap["id"], snap["payload_hash"], self.reviewer)
        with self.assertRaises(EvidenceConflict):
            self.service.approve(snap["id"], "0" * 64, self.approver)
        other = replace(self.admin, workspace_id="other")
        with self.assertRaises(NotFoundError):
            self.service.capture(self.doc.id, other)
        with self.assertRaises(NotFoundError):
            self.service.approve(snap["id"], snap["payload_hash"], other)
        with self.assertRaises(UnauthorizedError):
            self.service.import_records([self.source()], self.reviewer)

    def test_legacy_unknown_and_freshness_block(self):
        rev = self.service.capture(self.doc.id, self.reviewer)
        self.assertTrue(all(f["kind"] == "unknown" for f in rev["fields"].values()))
        snap = self.prepare()
        with patch(
            "app.procurement.service.now", return_value=datetime.now(UTC) + timedelta(days=2)
        ):
            self.assertEqual(
                self.service.approval_status(snap["id"], self.approver)["status"], "stale"
            )

    def test_invalid_decimal_alias_and_csv(self):
        for value in ["NaN", "Infinity", "1,25", "0.123456789", 0.1, True]:
            row = self.source()
            row["lines"][0]["quantity"] = value
            with self.assertRaises(ValueError):
                ProcurementRecord.model_validate(row)
        with self.assertRaises(ValueError):
            Mapping(company="AC", supplier_aliases={"Acme": "1", " acme ": "2"}, reason="Test")
        for text in ["bad,columns\na,b", "company,company\na,b"]:
            with self.assertRaises(EvidenceConflict):
                self.service.import_csv(text, self.admin)

    def test_duplicate_source_and_atomic_batch(self):
        self.service.import_records([self.source()], self.admin)
        with self.assertRaises(EvidenceConflict):
            self.service.import_records([self.source("receipt"), self.source()], self.admin)
        self.assertIsNone(self.repo.latest("default", "receipt", key("AC", "manual", "R1")))
        with self.assertRaises(EvidenceConflict):
            self.service.import_records([self.source(), self.source()], self.admin)

    def test_evidence_revision_conflict_and_wrong_value(self):
        rev = self.service.capture(self.doc.id, self.reviewer)
        field = FieldEvidence(kind="observed", effective="wrong", page=1, excerpt="wrong")
        with self.assertRaises(EvidenceConflict):
            self.service.attest(
                self.doc.id,
                EvidenceUpdate(
                    expected_revision=rev["version"], fields={"total": field}, reason="Verify"
                ),
                self.reviewer,
            )
        with self.assertRaises(EvidenceConflict):
            self.service.attest(
                self.doc.id,
                EvidenceUpdate(expected_revision=0, fields={}, reason="Verify"),
                self.reviewer,
            )

    def test_sqlite_restart_additive_and_immutable_reads(self):
        snap = self.prepare()
        before = self.repo.latest("default", "snapshot", snap["id"])
        before["inputs"]["invoice"]["fields"]["total"]["effective"] = "999"
        other = SqliteStore(Path(self.tmp.name) / "db.sqlite")
        self.addCleanup(other.close)
        self.assertEqual(
            VersionRepository(other).latest("default", "snapshot", snap["id"])["inputs"]["invoice"][
                "fields"
            ]["total"]["effective"],
            "10",
        )
        self.assertIsNotNone(
            other.query_one("SELECT name FROM sqlite_master WHERE name='documents'")
        )

    def test_readonly_erp_adapter_and_source_identity(self):
        client = Mock()
        client._request.return_value = {
            "data": {
                "name": "PO1",
                "company": "AC",
                "supplier": "SUP1",
                "currency": "USD",
                "docstatus": 1,
                "modified": "2026-10-14T10:00:00",
                "items": [
                    {
                        "name": "p1",
                        "item_code": "W",
                        "uom": "EA",
                        "qty": 1,
                        "rate": 10,
                        "amount": 10,
                    }
                ],
            }
        }
        r = read_procurement(client, "po", "PO1", "Asia/Jakarta")
        self.assertEqual(r.source_id, "PO1")
        self.assertEqual(client._request.call_args.args[0], "GET")
        self.assertFalse(client._request.call_args.kwargs["write_request"])
        with self.assertRaises(ValueError):
            read_procurement(client, "po", "other", "Asia/Jakarta")

    def test_csv_round_trip_and_mapping_change(self):
        import csv
        import io

        source = self.source()
        line = source.pop("lines")[0]
        output = io.StringIO()
        row = dict(source, **line)
        writer = csv.DictWriter(output, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        imported = self.service.import_csv(output.getvalue(), self.admin)
        self.assertEqual(imported[0]["record"]["lines"][0]["quantity"], "1")

    def test_mapping_revision_invalidates_approval(self):
        snap = self.prepare()
        self.service.approve(snap["id"], snap["payload_hash"], self.approver)
        self.service.configure(
            "mapping",
            Mapping(company="AC", supplier_aliases={"Acme": "SUP2"}, reason="Supplier corrected"),
            self.admin,
        )
        self.assertEqual(self.service.approval_status(snap["id"], self.approver)["status"], "stale")

    def test_concurrent_approval_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor

        snap = self.prepare()

        def attempt():
            try:
                self.service.approve(snap["id"], snap["payload_hash"], self.approver)
                return True
            except EvidenceConflict:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: attempt(), range(2))), [False, True])

    def test_unchanged_erp_refresh_preserves_identity_and_rejects_silent_change(self):
        source = self.source()
        source["source_updated_at"] = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        first = self.service.import_records([source], self.admin)[0]
        second = self.service.import_records([source], self.admin, refresh_unchanged=True)[0]
        self.assertEqual(first["record"], second["record"])
        self.assertEqual(second["version"], 2)
        source["lines"][0]["quantity"] = "3"
        with self.assertRaises(EvidenceConflict):
            self.service.import_records([source], self.admin, refresh_unchanged=True)

    def test_removed_line_is_visible_in_revision_diff(self):
        original = self.service.capture(self.doc.id, self.reviewer)
        self.save(replace(self.invoice, line_items=()))
        changed = self.service.capture(self.doc.id, self.reviewer, reason="Removed duplicate line")
        self.assertEqual(changed["changes"]["lines.line-1.quantity"]["after"]["kind"], "removed")
        self.assertEqual(original["line_ids"], ["line-1"])
