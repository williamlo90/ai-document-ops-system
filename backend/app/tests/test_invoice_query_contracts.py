from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.api.invoices import (
    _export_state,
    _invoice_business_status,
    _invoice_insights,
    _invoice_sort_key,
    _invoice_summary,
    _matches_invoice_date,
    _matches_invoice_search,
    _matches_invoice_status,
    _matches_invoice_vendor,
)
from app.benchmark.datasets import _is_relative_to
from app.backoffice.models import WorkItem, WorkItemStatus
from app.backoffice.workflow_projection import project_workflow_state
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.invoices.queries import InvoiceListQuery, SqliteInvoiceQueryRepository
import app.documents.jobs as jobs_module


def _document(status: DocumentStatus = DocumentStatus.UPLOADED) -> DocumentRecord:
    return DocumentRecord(
        original_filename="invoice.pdf",
        storage_key="invoice.pdf",
        content_type="application/pdf",
        status=status,
    )


def _extraction(
    *,
    vendor: str | None = "Acme Logistics",
    invoice_number: str | None = "INV-001",
    invoice_date: date | None = date(2026, 7, 30),
    total: Decimal | None = Decimal("100.00"),
    issue_codes: tuple[str, ...] = (),
):
    data = SimpleNamespace(
        vendor_name=vendor,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        total=total,
    )
    issues = tuple(SimpleNamespace(code=code) for code in issue_codes)
    return SimpleNamespace(
        extraction_result=SimpleNamespace(extraction=SimpleNamespace(data=data)),
        validation_report=SimpleNamespace(issues=issues),
    )


class InvoiceQueryContractTests(unittest.TestCase):
    def test_sql_query_reports_an_impossible_missing_aggregate(self) -> None:
        store = SimpleNamespace(
            query=lambda *_args, **_kwargs: [],
            query_one=lambda *_args, **_kwargs: None,
        )
        repository = SqliteInvoiceQueryRepository(store)

        with self.assertRaisesRegex(RuntimeError, "aggregate rows"):
            repository.list(InvoiceListQuery(workspace_id="default"))

    def test_sql_query_builder_covers_every_supported_filter(self) -> None:
        repository = SqliteInvoiceQueryRepository(SimpleNamespace())
        lower = date(2026, 7, 1)
        upper = date(2026, 7, 31)
        query = InvoiceListQuery(
            workspace_id="default",
            owner_user_id="operator",
            search=" ACME ",
            status="open",
            vendor=" Logistics ",
            submitted_by=" Operator ",
            created_from=lower,
            created_to=upper,
            invoice_date_from=lower,
            invoice_date_to=upper,
        )

        common_sql, common_params = repository._common_query(query)
        filters, params = repository._filters(query)

        self.assertIn("d.submitted_by = ?", common_sql)
        self.assertEqual(common_params, ("default", "default", "operator"))
        self.assertIn("business_status NOT IN", filters)
        self.assertEqual(
            params,
            (
                "%acme%",
                "%logistics%",
                "operator",
                "2026-07-01",
                "2026-07-31",
                "2026-07-01",
                "2026-07-31",
            ),
        )

        completed_sql, _ = repository._filters(
            InvoiceListQuery(workspace_id="default", status="completed")
        )
        exact_sql, exact_params = repository._filters(
            InvoiceListQuery(workspace_id="default", status="approved")
        )
        empty_sql, empty_params = repository._filters(InvoiceListQuery(workspace_id="default"))

        self.assertIn("business_status IN", completed_sql)
        self.assertIn("business_status = ?", exact_sql)
        self.assertEqual(exact_params, ("approved",))
        self.assertEqual((empty_sql, empty_params), ("", ()))

    def test_in_memory_invoice_filters_and_sort_keys_match_business_contract(self) -> None:
        extraction = _extraction()
        missing_data = _extraction(vendor=None, invoice_date=None, total=None)
        document = _document()
        document.created_at = datetime(2026, 7, 29, tzinfo=UTC)
        document.updated_at = datetime(2026, 7, 30, tzinfo=UTC)

        self.assertTrue(_matches_invoice_search("invoice.pdf", None, ""))
        self.assertTrue(_matches_invoice_search("invoice.pdf", extraction, "acme"))
        self.assertFalse(_matches_invoice_search("invoice.pdf", None, "missing"))
        self.assertTrue(_matches_invoice_status("queued", ""))
        self.assertTrue(_matches_invoice_status("queued", "open"))
        self.assertTrue(_matches_invoice_status("approved", "completed"))
        self.assertTrue(_matches_invoice_status("approved", "approved"))
        self.assertTrue(_matches_invoice_vendor(None, ""))
        self.assertTrue(_matches_invoice_vendor(extraction, "acme"))
        self.assertFalse(_matches_invoice_vendor(None, "acme"))
        self.assertTrue(_matches_invoice_date(None, None, None))
        self.assertFalse(_matches_invoice_date(None, date(2026, 7, 1), None))
        self.assertTrue(
            _matches_invoice_date(
                extraction,
                date(2026, 7, 1),
                date(2026, 7, 31),
            )
        )
        self.assertFalse(
            _matches_invoice_date(
                extraction,
                date(2026, 8, 1),
                None,
            )
        )

        self.assertEqual(_invoice_sort_key(document, extraction, "created"), document.created_at)
        self.assertEqual(
            _invoice_sort_key(document, extraction, "invoice_date"),
            (True, date(2026, 7, 30)),
        )
        self.assertEqual(_invoice_sort_key(document, extraction, "vendor"), "acme logistics")
        self.assertEqual(
            _invoice_sort_key(document, extraction, "amount"),
            (True, Decimal("100.00")),
        )
        self.assertEqual(
            _invoice_sort_key(document, missing_data, "amount"),
            (False, Decimal("0")),
        )
        self.assertEqual(_invoice_sort_key(document, None, "vendor"), "")
        self.assertEqual(_invoice_sort_key(document, extraction, "updated"), document.updated_at)

    def test_invoice_summaries_and_insights_cover_each_business_state(self) -> None:
        documents = [_document() for _ in range(5)]
        statuses = {
            documents[0].id: "needs_review",
            documents[1].id: "needs_correction",
            documents[2].id: "approved",
            documents[3].id: "exported",
            documents[4].id: "queued",
        }
        extractions = {
            documents[0].id: _extraction(issue_codes=("duplicate_invoice", "tax_mismatch")),
            documents[1].id: _extraction(issue_codes=("missing_vendor",)),
        }

        self.assertEqual(
            _invoice_summary(documents, statuses),
            {
                "all": 5,
                "waiting_review": 1,
                "needs_correction": 1,
                "approved": 1,
                "exported": 1,
            },
        )
        self.assertEqual(
            _invoice_insights(documents, extractions),
            {
                "flagged": 2,
                "duplicates_suspected": 1,
                "tax_amount_issues": 1,
            },
        )
        self.assertEqual(
            _invoice_business_status(DocumentStatus.FAILED, False),
            "needs_correction",
        )
        self.assertEqual(
            _invoice_business_status(DocumentStatus.NEEDS_REVIEW, True),
            "needs_correction",
        )
        self.assertEqual(
            _invoice_business_status(DocumentStatus.APPROVED, False),
            "approved",
        )
        self.assertEqual(_export_state(DocumentStatus.EXPORTED), "exported")
        self.assertEqual(_export_state(DocumentStatus.APPROVED), "eligible")
        self.assertEqual(_export_state(DocumentStatus.QUEUED), "not_eligible")

    def test_dataset_path_boundary_rejects_a_sibling_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "dataset"
            sibling = Path(temp_dir) / "outside.pdf"

            self.assertFalse(_is_relative_to(sibling, parent))

    def test_job_timestamps_remain_monotonic_when_the_clock_moves_back(self) -> None:
        previous = jobs_module._last_timestamp
        future = datetime.now(UTC) + timedelta(days=1)
        try:
            jobs_module._last_timestamp = future

            timestamp = jobs_module._monotonic_timestamp()

            self.assertEqual(timestamp, future + timedelta(microseconds=1))
        finally:
            jobs_module._last_timestamp = previous


class WorkflowProjectionContractTests(unittest.TestCase):
    def test_document_only_states_have_explicit_business_outcomes(self) -> None:
        expected_stages = {
            DocumentStatus.FAILED: "failed",
            DocumentStatus.UPLOADED: "extracting",
            DocumentStatus.QUEUED: "extracting",
            DocumentStatus.PROCESSING: "extracting",
            DocumentStatus.REJECTED: "rejected",
            DocumentStatus.CANCELLED: "cancelled",
            DocumentStatus.NEEDS_REVIEW: "needs_verification",
            DocumentStatus.EXPORTED: "completed",
            DocumentStatus.APPROVED: "ready_to_submit",
        }

        for status, expected_stage in expected_stages.items():
            with self.subTest(status=status):
                projection = project_workflow_state(
                    _document(status),
                    None,
                    pending_for_item=False,
                )
                self.assertEqual(projection.current_stage, expected_stage)

    def test_work_item_states_have_explicit_business_outcomes(self) -> None:
        document = _document(DocumentStatus.APPROVED)
        cases = (
            ({"correction_state": "requested"}, WorkItemStatus.NEW, False, "correction_requested"),
            ({"correction_state": "submitted"}, WorkItemStatus.NEW, False, "waiting_approval"),
            ({}, WorkItemStatus.NEW, True, "waiting_approval"),
            ({}, WorkItemStatus.AWAITING_HUMAN, False, "needs_attention"),
            ({}, WorkItemStatus.BLOCKED, False, "failed"),
            ({}, WorkItemStatus.FAILED, False, "failed"),
            ({}, WorkItemStatus.RESOLVED, False, "completed"),
            ({}, WorkItemStatus.PLANNING, False, "planning"),
        )

        for context, status, pending, expected_stage in cases:
            with self.subTest(status=status, context=context, pending=pending):
                work_item = WorkItem(
                    workspace_id="default",
                    title="Invoice review",
                    status=status,
                    business_context=context,
                )
                projection = project_workflow_state(
                    document,
                    work_item,
                    pending_for_item=pending,
                )
                self.assertEqual(projection.current_stage, expected_stage)


if __name__ == "__main__":
    unittest.main()
