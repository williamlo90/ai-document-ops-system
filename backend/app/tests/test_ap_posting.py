from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import unittest

from app.core.security import SecurityContext, UnauthorizedError
from app.integrations.models import IntegrationDeliveryError
from app.procurement.models import ERPPostingProfile, SnapshotInput, MatchPolicy
from app.procurement.posting import PostingService
from app.procurement.service import EvidenceConflict, now
from app.tests import test_ap_matching as fixture


class FakeERP:
    def __init__(self):
        self.docs = {}
        self.create_count = 0
        self.submit_count = 0
        self.create_allowed = True
        self.submit_allowed = True
        self.lose_create_response = False
        self.lose_submit_response = False
        self.ledger_mismatch = False
        self.crash_before_create = False
        self.sources = {}

    def has_permission(self, doctype, action, *, name=""):
        return self.create_allowed if action == "create" else self.submit_allowed

    def create_purchase_invoice(self, request):
        if self.crash_before_create:
            self.crash_before_create = False
            raise SystemExit("injected crash before remote write")
        self.create_count += 1
        name = f"PINV-{self.create_count}"
        rows = [
            {**row, "amount": str(Decimal(str(row["qty"])) * Decimal(str(row["rate"])))}
            for row in request["items"]
        ]
        subtotal = sum((Decimal(row["amount"]) for row in rows), Decimal(0))
        tax = sum((Decimal(str(row["tax_amount"])) for row in request.get("taxes", [])), Decimal(0))
        discount = Decimal(str(request.get("discount_amount", 0)))
        self.docs[name] = {
            **deepcopy(request),
            "name": name,
            "items": rows,
            "net_total": str(subtotal),
            "grand_total": str(subtotal + tax - discount),
            "discount_amount": str(discount),
            "modified": "2026-10-14 09:00:00",
            "docstatus": 0,
        }
        if self.lose_create_response:
            self.lose_create_response = False
            raise IntegrationDeliveryError(
                "response lost", code="timeout", retryable=False, outcome_unknown=True
            )
        return deepcopy(self.docs[name])

    def get_purchase_invoice(self, name):
        return deepcopy(self.docs[name])

    def get_procurement_document(self, kind, name):
        return deepcopy(self.sources[(kind, name)])

    def find_purchase_invoices_by_delivery_key(self, key):
        return [
            {"name": name}
            for name, row in self.docs.items()
            if row.get("custom_invoice_review_delivery_key") == key
        ]

    def submit_purchase_invoice(self, document):
        self.submit_count += 1
        target = self.docs[document["name"]]
        target["docstatus"] = 1
        target["modified"] = "2026-10-14 09:01:00"
        if self.lose_submit_response:
            self.lose_submit_response = False
            raise IntegrationDeliveryError(
                "response lost", code="timeout", retryable=False, outcome_unknown=True
            )
        return deepcopy(target)

    def get_gl_entries(self, name):
        row = self.docs[name]
        total = Decimal(str(row["grand_total"]))
        credit = total - (Decimal("1") if self.ledger_mismatch else Decimal(0))
        common = {
            "company": row["company"],
            "voucher_type": "Purchase Invoice",
            "voucher_no": name,
            "is_cancelled": 0,
            "posting_date": row["posting_date"],
        }
        return [
            {
                **common,
                "name": "GL-1",
                "account": row["items"][0]["expense_account"],
                "debit": str(total),
                "credit": "0",
            },
            {
                **common,
                "name": "GL-2",
                "account": row["credit_to"],
                "debit": "0",
                "credit": str(credit),
            },
        ]


class PostingTests(unittest.TestCase):
    setUp = fixture.MatchTests.setUp
    source = fixture.MatchTests.source
    invoice = fixture.MatchTests.invoice

    def setup_posting(self):
        # Reimport the same synthetic PO/receipt under the ERPNext source namespace.
        for kind, source_id in (("po", "PO1"), ("receipt", "R1")):
            previous = next(
                row["record"]
                for row in self.repo.all_latest(self.admin.workspace_id, kind)
                if row["record"]["source_id"] == source_id
            )
            self.evidence.import_records(
                [
                    {
                        **previous,
                        "source_system": "erpnext",
                        "source_version": previous["source_updated_at"],
                    }
                ],
                self.admin,
            )
        doc, old = self.invoice("10")
        snapshot = self.evidence.snapshot(
            doc.id,
            SnapshotInput(
                company="AC",
                expected_revision=old["inputs"]["invoice"]["version"],
                source_system="erpnext",
                po_ids=["PO1"],
                receipt_ids=["R1"],
                allocations={"l1": "PO1:p1"},
            ),
            self.reviewer,
        )
        self.evidence.approve(snapshot["id"], snapshot["payload_hash"], self.approver)
        match = self.match.assess(snapshot["id"], self.reviewer)
        self.assertEqual(match["recommendation"], "ready_for_approval")
        self.match.approve(match["id"], match["basis_hash"], self.approver)
        erp = FakeERP()
        for kind in ("po", "receipt"):
            for source in snapshot["inputs"]["sources"][kind]:
                record = source["record"]
                erp.sources[(kind, record["source_id"])] = {
                    "name": record["source_id"],
                    "docstatus": 1,
                    "company": record["company"],
                    "supplier": record["supplier_id"],
                    "currency": record["currency"],
                    "modified": datetime.fromisoformat(record["source_version"])
                    .replace(tzinfo=None)
                    .isoformat(sep=" "),
                    "items": [
                        {
                            "name": line["source_line_id"],
                            "item_code": line["item_id"],
                            "qty": line["quantity"],
                            "uom": line["uom"],
                            "billed_amt": "0",
                        }
                        for line in record["lines"]
                    ],
                }
        posting = PostingService(self.evidence, erp, sandbox_enabled=True)
        posting.configure_profile(
            ERPPostingProfile(
                company="AC",
                erp_company="AC",
                supplier_ids={"SUP": "ERP-SUP"},
                item_codes={"W": "ERP-W"},
                expense_accounts={"W": "Expense - AC"},
                payable_accounts={"USD": "Creditors - AC"},
                exchange_rates={"USD": "1"},
                reason="Verified synthetic sandbox mappings",
            ),
            self.admin,
        )
        return doc, match, erp, posting

    def test_draft_submit_are_separate_and_verified_without_duplicate_write(self):
        _, match, erp, posting = self.setup_posting()
        with self.assertRaises(EvidenceConflict):
            posting.submit_draft(match["id"], "0" * 64, self.approver)
        draft = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        self.assertEqual(draft["state"], "confirmed")
        self.assertEqual(draft["receipt"]["docstatus"], 0)
        self.assertEqual(
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)["id"],
            draft["id"],
        )
        self.assertEqual(erp.create_count, 1)
        approval = posting.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Reviewed draft and source evidence",
            self.approver,
        )
        with self.assertRaises(EvidenceConflict):
            posting.approve_submit(
                match["id"],
                draft["id"],
                draft["verification_hash"],
                "Duplicate approval attempt",
                self.approver,
            )
        posted = posting.submit_draft(match["id"], approval["approval_hash"], self.approver)
        self.assertTrue(posted["posted_verified"])
        self.assertEqual(posted["receipt"]["docstatus"], 1)
        self.assertEqual(
            posting.submit_draft(match["id"], approval["approval_hash"], self.approver)["id"],
            posted["id"],
        )
        self.assertEqual(erp.submit_count, 1)
        self.assertEqual(erp.create_count, 1)

    def test_permissions_and_role_prevent_writes(self):
        _, match, erp, posting = self.setup_posting()
        erp.create_allowed = False
        with self.assertRaises(EvidenceConflict):
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        erp.create_allowed = True
        with self.assertRaises(UnauthorizedError):
            posting.create_draft(match["id"], match["basis_hash"], {}, self.reviewer)
        self.assertEqual(erp.create_count, 0)
        draft = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        approval = posting.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Checked draft before submit",
            self.approver,
        )
        erp.submit_allowed = False
        with self.assertRaises(EvidenceConflict):
            posting.submit_draft(match["id"], approval["approval_hash"], self.approver)
        self.assertEqual(erp.submit_count, 0)

    def test_unknown_create_and_submit_reconcile_after_restart_without_rewrite(self):
        _, match, erp, posting = self.setup_posting()
        erp.lose_create_response = True
        unknown = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        self.assertEqual(unknown["state"], "unknown")
        restarted = PostingService(self.evidence, erp, sandbox_enabled=True)
        draft = restarted.reconcile(match["id"], "create", self.approver)
        self.assertEqual(draft["state"], "confirmed")
        self.assertEqual(erp.create_count, 1)
        approval = restarted.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Verified recovered draft",
            self.approver,
        )
        erp.lose_submit_response = True
        submitted = restarted.submit_draft(match["id"], approval["approval_hash"], self.approver)
        self.assertEqual(submitted["state"], "unknown")
        final = PostingService(self.evidence, erp, sandbox_enabled=True).reconcile(
            match["id"], "submit", self.approver
        )
        self.assertTrue(final["posted_verified"])
        self.assertEqual((erp.create_count, erp.submit_count), (1, 1))

    def test_write_flag_rollback_preserves_read_only_reconciliation(self):
        _, match, erp, posting = self.setup_posting()
        draft = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        approval = posting.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Verified before rollback test",
            self.approver,
        )
        erp.lose_submit_response = True
        self.assertEqual(
            posting.submit_draft(match["id"], approval["approval_hash"], self.approver)["state"],
            "unknown",
        )
        disabled = PostingService(self.evidence, erp, sandbox_enabled=False)
        with self.assertRaises(EvidenceConflict):
            disabled.submit_draft(match["id"], approval["approval_hash"], self.approver)
        self.assertTrue(disabled.reconcile(match["id"], "submit", self.approver)["posted_verified"])
        self.assertEqual((erp.create_count, erp.submit_count), (1, 1))
        with self.assertRaises(UnauthorizedError):
            disabled.reconcile(match["id"], "submit", self.reviewer)

    def test_crash_before_remote_create_requires_absence_check_then_safe_retry(self):
        _, match, erp, posting = self.setup_posting()
        erp.crash_before_create = True
        with self.assertRaises(SystemExit):
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        pending = posting.status(match["id"], self.approver)["draft"]
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(erp.create_count, 0)
        self.assertEqual(
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)["state"],
            "pending",
        )
        with self.assertRaises(EvidenceConflict):
            posting.confirm_create_absent_for_retry(match["id"], self.admin)
        with self.repo.transaction(self.admin.workspace_id):
            self.repo.append(
                self.admin.workspace_id,
                "posting_operation",
                pending["id"],
                {**pending, "at": (now() - timedelta(minutes=1)).isoformat()},
            )
        authorized = posting.confirm_create_absent_for_retry(match["id"], self.admin)
        self.assertEqual(authorized["state"], "failed")
        self.assertTrue(authorized["retryable"])
        draft = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        self.assertEqual(draft["state"], "confirmed")
        self.assertEqual(erp.create_count, 1)

    def test_edited_draft_stale_source_and_ledger_mismatch(self):
        _, match, erp, posting = self.setup_posting()
        draft = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        erp.docs[draft["target"]]["items"][0]["rate"] = "49"
        with self.assertRaises(EvidenceConflict):
            posting.approve_submit(
                match["id"],
                draft["id"],
                draft["verification_hash"],
                "Draft modified after review",
                self.approver,
            )
        erp.docs[draft["target"]]["items"][0]["rate"] = "50"
        approval = posting.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Restored verified draft",
            self.approver,
        )
        erp.ledger_mismatch = True
        result = posting.submit_draft(match["id"], approval["approval_hash"], self.approver)
        self.assertEqual(result["state"], "reconciliation_required")
        self.assertFalse(result.get("posted_verified", False))
        erp.ledger_mismatch = False
        self.assertTrue(posting.reconcile(match["id"], "submit", self.approver)["posted_verified"])

    def test_changed_match_policy_blocks_draft_even_when_old_approval_exists(self):
        _, match, erp, posting = self.setup_posting()
        from datetime import UTC, datetime

        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                reason="Changed before posting",
            ),
            self.admin,
        )
        with self.assertRaises(EvidenceConflict):
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        self.assertEqual(erp.create_count, 0)

    def test_remote_billing_and_receipt_race_block_before_write(self):
        _, match, erp, posting = self.setup_posting()
        erp.sources[("po", "PO1")]["items"][0]["billed_amt"] = "100"
        with self.assertRaises(EvidenceConflict):
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        self.assertEqual(erp.create_count, 0)
        erp.sources[("po", "PO1")]["items"][0]["billed_amt"] = "0"
        draft = posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        approval = posting.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Verified current draft and receipt",
            self.approver,
        )
        erp.sources[("receipt", "R1")]["modified"] = "2026-10-14 11:30:00"
        with self.assertRaises(EvidenceConflict):
            posting.submit_draft(match["id"], approval["approval_hash"], self.approver)
        self.assertEqual(erp.submit_count, 0)

    def test_cross_company_erp_profile_blocks_create(self):
        _, match, erp, posting = self.setup_posting()
        posting.configure_profile(
            ERPPostingProfile(
                company="AC",
                erp_company="Other Company",
                supplier_ids={"SUP": "ERP-SUP"},
                item_codes={"W": "ERP-W"},
                expense_accounts={"W": "Expense - AC"},
                payable_accounts={"USD": "Creditors - AC"},
                exchange_rates={"USD": "1"},
                reason="Cross-company negative validation",
            ),
            self.admin,
        )
        with self.assertRaises(EvidenceConflict):
            posting.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        self.assertEqual(erp.create_count, 0)

    def test_sandbox_flag_and_cross_workspace_block(self):
        _, match, erp, posting = self.setup_posting()
        disabled = PostingService(self.evidence, erp, sandbox_enabled=False)
        with self.assertRaises(EvidenceConflict):
            disabled.create_draft(match["id"], match["basis_hash"], {}, self.approver)
        alien = SecurityContext("Other approver", role="ap_approver", workspace_id="other")
        with self.assertRaises(Exception):
            posting.create_draft(match["id"], match["basis_hash"], {}, alien)
        self.assertEqual(erp.create_count, 0)


if __name__ == "__main__":
    unittest.main()
