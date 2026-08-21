from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/prepare_erpnext_phase8.py"
SPEC = importlib.util.spec_from_file_location("prepare_erpnext_phase8", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
phase8 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phase8
SPEC.loader.exec_module(phase8)


class ERPNextPhase8ToolTests(unittest.TestCase):
    def test_prepare_creates_non_benchmark_fixture_and_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(phase8, "PRIVATE_ROOT", root),
                patch.object(phase8, "PRACTICE_PDF", root / "practice.pdf"),
                patch.object(phase8, "PRACTICE_EXPECTED", root / "expected.json"),
                patch.object(phase8, "DRY_RUN_RECORD", root / "record.json"),
            ):
                phase8._prepare()
                expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
                record = json.loads((root / "record.json").read_text(encoding="utf-8"))

        self.assertFalse(expected["formal_benchmark_case"])
        self.assertEqual(expected["invoice"]["invoice_number"], "PHASE8-PRACTICE-001")
        self.assertEqual(
            expected["expected_erp"]["supplier"],
            "Acme Logistics - Assisted Benchmark",
        )
        self.assertEqual(record["workflows"]["manual"]["status"], "pending")
        self.assertEqual(record["workflows"]["assisted"]["status"], "pending")

    def test_record_rejects_active_time_above_elapsed_time(self) -> None:
        args = argparse.Namespace(
            workflow="manual",
            elapsed_seconds=10,
            active_seconds=11,
            erp_id="ACC-PINV-1",
            notes="",
        )
        with self.assertRaisesRegex(SystemExit, "cannot exceed"):
            phase8._record(args)

    def test_freeze_requires_both_operator_rehearsals(self) -> None:
        record = {
            "workflows": {
                "manual": {"status": "completed", "draft_verified": True},
                "assisted": {"status": "pending", "draft_verified": False},
            }
        }
        with (
            patch.object(phase8, "_load_record", return_value=record),
            self.assertRaisesRegex(SystemExit, "assisted"),
        ):
            phase8._freeze()

    def test_application_reset_only_purges_the_practice_filename(self) -> None:
        documents = [
            {"id": "practice-id", "original_filename": "phase8-practice-invoice.pdf"},
            {"id": "formal-id", "original_filename": "01_standard_usd.pdf"},
        ]
        with patch.object(phase8, "_app_request", side_effect=[documents, {}]) as request:
            removed = phase8._reset_application_records("local-admin-token")

        self.assertEqual(removed, 1)
        request.assert_any_call(
            "DELETE",
            "/documents/practice-id",
            "local-admin-token",
            payload={"reason": "phase8_dry_run"},
        )


if __name__ == "__main__":
    unittest.main()
