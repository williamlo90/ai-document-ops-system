from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from erpnext_setup.dataset import load_benchmark_dataset  # noqa: E402


MANIFEST = ROOT / "examples/erpnext/benchmark_cases.json"


class ERPNextMasterDataTests(unittest.TestCase):
    def test_locked_dataset_is_complete_and_reproducible(self) -> None:
        dataset = load_benchmark_dataset(ROOT, MANIFEST)

        self.assertEqual(dataset.dataset_id, "invoice-manual-benchmark-t01-t10")
        self.assertEqual(
            dataset.fingerprint,
            "ca37538cd0f823acf811f23b92ffcda9e74c56000ed7f580def37bee75420407",
        )
        self.assertEqual(
            [case.case_id for case in dataset.cases],
            [f"T{index:02d}" for index in range(1, 11)],
        )
        self.assertEqual(sum(case.erp_outcome == "draft_eligible" for case in dataset.cases), 6)
        self.assertEqual({case.currency for case in dataset.cases}, {"USD", "EUR"})
        self.assertEqual(len(dataset.suppliers), 8)

    def test_locked_dataset_rejects_changed_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
            first_case = raw["cases"][0]
            changed = temp_path / "changed.pdf"
            changed.write_bytes(b"not the locked invoice")
            first_case["source_file"] = str(changed)
            first_case["source_sha256"] = hashlib.sha256(changed.read_bytes()).hexdigest()
            manifest = temp_path / "manifest.json"
            manifest.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "fingerprint"):
                load_benchmark_dataset(ROOT, manifest)
