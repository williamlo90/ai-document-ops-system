from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.production_validation.metrics import (
    evaluate_acceptance,
    evaluate_document_invariants,
    evaluate_upload_invariants,
    nearest_rank,
    summarize_samples,
    summarize_timeline,
)
from scripts.production_validation.models import AcceptanceThresholds, RequestSample
from scripts.production_validation.report import build_report, write_report
from scripts.production_validation.run import _parser, _request_identity, _validate_args


class ProductionValidationTests(unittest.TestCase):
    def test_nearest_rank_percentiles_are_deterministic(self) -> None:
        values = [100, 20, 40, 80, 60]

        self.assertEqual(nearest_rank(values, 50), 60.0)
        self.assertEqual(nearest_rank(values, 90), 100.0)
        self.assertEqual(nearest_rank([], 95), None)

    def test_summary_treats_explicit_conflict_as_expected(self) -> None:
        samples = [
            self._sample("approve_invoice", 200, (200, 409), 100),
            self._sample("approve_invoice", 409, (200, 409), 120),
        ]

        summary = summarize_samples(samples, elapsed_seconds=2)

        self.assertEqual(summary["availability_percent"], 100.0)
        self.assertEqual(summary["unexpected_failures"], 0)

    def test_timeline_uses_fixed_one_minute_windows(self) -> None:
        samples = [
            self._sample("read_invoices", 200, (200,), 10, second=0),
            self._sample("read_invoices", 200, (200,), 20, second=59),
            self._sample("read_invoices", 500, (200,), 30, second=60),
        ]

        timeline = summarize_timeline(samples)

        self.assertEqual([window["count"] for window in timeline], [2, 1])
        self.assertEqual(timeline[1]["unexpected_5xx"], 1)

    def test_acceptance_fails_slow_or_erroring_workload(self) -> None:
        samples = [
            self._sample("read_invoices", 500, (200,), 4_000),
            self._sample("upload_document", 200, (200,), 9_000, document_id="doc-1"),
        ]
        summary = summarize_samples(samples, elapsed_seconds=1)

        checks = evaluate_acceptance(summary, AcceptanceThresholds())

        failed_codes = {check.code for check in checks if not check.passed}
        self.assertIn("availability", failed_codes)
        self.assertIn("unexpected_5xx_rate", failed_codes)
        self.assertIn("read_invoices_p95_ms", failed_codes)
        self.assertIn("upload_document_p99_ms", failed_codes)

    def test_upload_invariant_rejects_duplicate_document_ids(self) -> None:
        samples = [
            self._sample("upload_document", 200, (200,), 100, document_id="same"),
            self._sample("upload_document", 200, (200,), 110, document_id="same"),
        ]

        checks = evaluate_upload_invariants(samples, expected_uploads=2)

        unique_check = next(check for check in checks if check.code == "upload_ids_unique")
        self.assertFalse(unique_check.passed)

    def test_document_invariant_rejects_unresolved_and_failed_work(self) -> None:
        samples = [
            self._sample("upload_document", 200, (200,), 100, document_id="doc-1"),
            self._sample("upload_document", 200, (200,), 110, document_id="doc-2"),
        ]

        checks = evaluate_document_invariants(samples, {"doc-1": "needs_review", "doc-2": "failed"})

        failed_codes = {check.code for check in checks if not check.passed}
        self.assertIn("uploaded_documents_converged", failed_codes)
        self.assertIn("zero_failed_documents", failed_codes)

    def test_report_excludes_credentials_and_target_url(self) -> None:
        request_id, trace_id, headers = _request_identity("secret-token")
        samples = [
            RequestSample(
                operation="read_invoices",
                started_at="2026-10-02T00:00:00Z",
                duration_ms=100,
                status_code=200,
                expected_statuses=(200,),
                request_id=request_id,
                trace_id=trace_id,
            ),
            self._sample("upload_document", 200, (200,), 200, document_id="doc-1"),
        ]
        summary = summarize_samples(samples, elapsed_seconds=1)
        checks = evaluate_acceptance(summary, AcceptanceThresholds())
        checks.extend(evaluate_upload_invariants(samples, expected_uploads=1))
        manifest = {
            "run_id": "test-run",
            "scope": "local-rehearsal",
            "target_label": "local",
            "source_revision": "abc123",
            "source_dirty": True,
            "started_at": "2026-10-02T00:00:00Z",
            "completed_at": "2026-10-02T00:00:01Z",
            "workload": {},
            "thresholds": {},
        }
        report = build_report(manifest=manifest, summary=summary, checks=checks, samples=samples)

        with tempfile.TemporaryDirectory() as temporary_directory:
            json_path, markdown_path = write_report(report, Path(temporary_directory) / "run")
            serialized = json_path.read_text(encoding="utf-8")
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertNotIn("secret-token", serialized)
        self.assertEqual(headers["X-Access-Token"], "secret-token")
        self.assertNotIn("http://127.0.0.1", serialized)
        self.assertIn('"status": "passed"', serialized)
        self.assertIn("Production Validation Report", markdown)

    def test_pg01_profile_rejects_short_rehearsal(self) -> None:
        args = _parser().parse_args(["--profile", "pg01", "--confirm-synthetic-target"])

        with self.assertRaisesRegex(SystemExit, "duration must be at least 3600"):
            _validate_args(args)

    @staticmethod
    def _sample(
        operation: str,
        status_code: int,
        expected_statuses: tuple[int, ...],
        duration_ms: float,
        *,
        document_id: str | None = None,
        second: int = 0,
    ) -> RequestSample:
        return RequestSample(
            operation=operation,
            started_at=(datetime(2026, 10, 2, tzinfo=UTC) + timedelta(seconds=second))
            .isoformat()
            .replace("+00:00", "Z"),
            duration_ms=duration_ms,
            status_code=status_code,
            expected_statuses=expected_statuses,
            request_id="request-id",
            trace_id="trace-id",
            document_id=document_id,
        )


if __name__ == "__main__":
    unittest.main()
