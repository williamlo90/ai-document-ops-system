from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "examples" / "erpnext" / "purchase_invoice_contract.json"
BENCHMARK_PATH = ROOT / "examples" / "erpnext" / "benchmark_cases.json"


class ERPNextDesignContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    def test_contract_is_draft_only(self) -> None:
        resource = self.contract["resource"]
        allowed = set(resource["allowed_operations"])
        forbidden = set(resource["forbidden_operations"])

        self.assertFalse(allowed & forbidden)
        self.assertEqual(self.contract["safety"]["provider_docstatus"], 0)
        self.assertEqual(self.contract["request_example"]["docstatus"], 0)
        self.assertEqual(self.contract["response_invariants"]["docstatus"], 0)
        self.assertEqual(self.contract["safety"]["success_copy"], "ERP draft created")

    def test_contract_requires_human_approval_evidence(self) -> None:
        safety = self.contract["safety"]

        self.assertEqual(safety["required_document_status"], "approved")
        self.assertEqual(safety["required_review_status"], "approved")
        self.assertEqual(set(safety["required_review_evidence"]), {"reviewed_by", "reviewed_at"})
        self.assertEqual(safety["required_validation_errors"], 0)

    def test_contract_uses_locked_benchmark_master_data(self) -> None:
        mapping = self.contract["benchmark_mapping"]

        self.assertEqual(self.contract["schema_version"], 3)
        self.assertEqual(mapping["item_code"], self.benchmark["default_item_code"])
        self.assertEqual(mapping["company"], "Invoice Review Assisted Benchmark")
        self.assertEqual(
            mapping["payable_accounts"],
            {"USD": "Creditors - IRA", "EUR": "Creditors EUR - IRA"},
        )
        self.assertEqual(mapping["expense_account"], "Professional Services - IRA")
        self.assertEqual(mapping["posting_date_policy"], "trial_date")
        self.assertEqual(set(mapping["tax_templates"]), {"0", "10", "20"})

    def test_provider_identity_fields_are_required_in_response(self) -> None:
        identity = self.contract["identity"]
        required = set(self.contract["required_response_fields"])

        self.assertIn(identity["provider_delivery_key_field"], required)
        self.assertIn(identity["provider_document_id_field"], required)
        self.assertIn(identity["provider_payload_hash_field"], required)


if __name__ == "__main__":
    unittest.main()
