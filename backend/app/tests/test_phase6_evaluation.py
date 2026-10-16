"""Evaluation checks that protect the scheduled denominator and independent ERP oracle."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from phase6_end_to_end import independent_readback, summarize, _grounded_fields  # noqa: E402
from phase6_provider_run import RateAwareParser, BoundedExtractor  # noqa: E402
from app.providers.contracts import ProviderError  # noqa: E402
from phase6_time_study import verify_terminal  # noqa: E402
from phase6_validate_pack import file_digest  # noqa: E402
from phase6_provider_run import physical_ocr_attempts  # noqa: E402


class Phase6EvaluationTests(unittest.TestCase):
    def test_key_failovers_count_physical_requests_without_double_counting_cooldown(self):
        stage = {"status": "succeeded", "attempts": [
            {"credential_attempts": [{"http_status": 429}, {"status": "succeeded"}]}]}
        self.assertEqual(len(physical_ocr_attempts(stage)), 2)
        self.assertEqual(sum(a.get("http_status") == 429 for a in physical_ocr_attempts(stage)), 1)
        self.assertEqual(physical_ocr_attempts({"status": "failed", "attempts": [{"credential_attempts": []}]}), [])

    def test_extractor_retries_transport_once_with_same_input_and_never_retries_bad_answers(self):
        provider = Mock(provider_name="llm_json")
        source, result = object(), object()
        provider.extract_invoice.side_effect = [ProviderError("extractor_request_failed", "llm_json", retryable=True), result]
        sleep = Mock()
        extractor = BoundedExtractor(provider, sleep=sleep)
        self.assertIs(extractor.extract_invoice(source), result)
        self.assertEqual([call.args for call in provider.extract_invoice.call_args_list], [(source,), (source,)])
        sleep.assert_called_once_with(5)
        for error in (ProviderError("invalid_extractor_response", "llm_json"),
                      ProviderError("quota", "llm_json", retryable=True, http_status=429)):
            provider.extract_invoice.reset_mock()
            provider.extract_invoice.side_effect = error
            with self.assertRaises(ProviderError):
                extractor.extract_invoice(source)
            self.assertEqual(provider.extract_invoice.call_count, 1)
        provider.extract_invoice.reset_mock()
        provider.extract_invoice.side_effect = ProviderError("extractor_request_failed", "llm_json", retryable=True)
        with self.assertRaises(ProviderError):
            extractor.extract_invoice(source)
        self.assertEqual(provider.extract_invoice.call_count, 2)

    def test_study_terminal_requires_bound_actual_evidence_and_matching_disposition(self):
        self.assertFalse(verify_terminal(Path("."), None, "manual", "posted_verified", "ERP-123"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = root / "_local_docs"
            pack.mkdir()
            (pack / "manifest.json").write_text("{}")
            (pack / "procurement.json").write_text(json.dumps({
                "manual_purchase_order": {"source_id": "PO1"}, "manual_purchase_receipt": {"source_id": "PR1"}}))
            (pack / "expected-match.json").write_text(json.dumps([{"document_id": "d1", "issue_codes": ["receipt_shortfall"]}]))
            document = SimpleNamespace(document_id="d1", source_path=pack / "invoice.pdf")
            proof = {"document_id": "d1", "condition": "manual", "source_refs": ["PO1", "PR1"],
                "manifest_sha256": file_digest(pack / "manifest.json"),
                "dispositions": [{"code": "receipt_shortfall", "state": "needs_info", "authorizer": "William",
                                  "reason": "Receipt incomplete", "evidence_refs": ["PO1", "PR1"]}]}
            evidence = pack / "readback.json"
            with patch("phase6_time_study.ROOT", root):
                evidence.write_text(json.dumps(proof))
                self.assertFalse(verify_terminal(pack, document, "manual", "exception_resolved", str(evidence)))
                proof["dispositions"][0]["state"] = "rejected"
                evidence.write_text(json.dumps(proof))
                self.assertTrue(verify_terminal(pack, document, "manual", "exception_resolved", str(evidence)))
                proof["condition"] = "assisted"
                evidence.write_text(json.dumps(proof))
                self.assertFalse(verify_terminal(pack, document, "manual", "exception_resolved", str(evidence)))

    def test_rate_limit_retry_preserves_input_and_honors_cooldown(self):
        provider = Mock(provider_name="ocr_space")
        parsed, source = object(), object()
        provider.parse.side_effect = [ProviderError("quota", "ocr_space", retryable=True,
            http_status=429, retry_after_seconds=65), parsed]
        sleep = Mock()
        parser = RateAwareParser(provider, sleep=sleep)
        self.assertIs(parser.parse(source), parsed)
        self.assertEqual([call.args for call in provider.parse.call_args_list], [(source,), (source,)])
        self.assertEqual(sum(call.args[0] for call in sleep.call_args_list), 67)
        self.assertEqual(len(parser.last_attempts), 2)
        self.assertEqual(parser.last_attempts[0]["http_status"], 429)

    def test_retry_is_bounded_and_requires_explicit_rate_limit_delay(self):
        for status, delay, attempts in ((429, 2, 2), (429, None, 1), (503, 2, 1), (429, 4000, 1)):
            with self.subTest(status=status, delay=delay):
                provider = Mock(provider_name="ocr_space")
                provider.parse.side_effect = ProviderError("quota", "ocr_space", retryable=True,
                    http_status=status, retry_after_seconds=delay)
                parser = RateAwareParser(provider, sleep=Mock())
                with self.assertRaises(ProviderError):
                    parser.parse(object())
                self.assertEqual(provider.parse.call_count, attempts)

    def label(self, document_id):
        values = {"document_id": document_id, "vendor_name": "Harbor Components", "invoice_number": "INV-1",
                  "invoice_date": "2026-10-10", "due_date": "2026-11-10", "currency": "USD",
                  "subtotal": "100.00", "tax": "0.00", "total": "100.00"}
        values["provenance"] = {key: {"kind": "observed", "page": 1, "excerpt": str(value)}
                                for key, value in values.items() if key != "document_id"}
        line = {"description": "Kit", "uom": "EA", "quantity": "2", "unit_price": "50.00", "amount": "100.00"}
        line["provenance"] = {key: {"kind": "observed", "page": 1, "excerpt": value} for key, value in line.items()}
        values["line_items"] = [line]
        return values

    def test_unobserved_cases_remain_in_eligible_and_hold_denominators(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory)
            (pack / "manifest.json").write_text("{}")
            documents = []
            for index in range(2):
                family = pack / str(index)
                family.mkdir()
                label = self.label(str(index))
                (family / "expected-match.json").write_text(json.dumps([{
                    "document_id": str(index), "expected_action": "submit" if index == 0 else "hold",
                    "issue_codes": [] if index == 0 else ["quantity_exceeds_available"]}]))
                documents.append(SimpleNamespace(document_id=str(index), expected_fields=label,
                                                  source_path=family / "invoice.pdf"))
            report = summarize(pack, "quality_holdout", SimpleNamespace(documents=documents), [], {})
            self.assertEqual(report["documents_count"], 2)
            self.assertEqual(report["pipeline"]["eligible_scheduled"], 1)
            self.assertEqual(report["pipeline"]["false_holds"], {"numerator": 1, "denominator": 1})
            self.assertEqual(report["pipeline"]["category_matrices"]["quantity"]["FN"], 1)
            self.assertIsNone(report["pipeline"]["posting_correctness"])

    def test_independent_oracle_rejects_due_date_and_ledger_mismatch(self):
        label = self.label("d1")
        source = {"purchase_order": {"source_id": "PO1", "lines": [{"source_line_id": "POL1"}]},
                  "purchase_receipt": {"source_id": "PR1", "lines": [{"source_line_id": "PRL1"}]}}
        profile = {"erp_company": "Company", "payable_accounts": {"USD": "Payable"},
                   "expense_accounts": {"Kit": "Expense"}}
        actual = {"name": "PI1", "docstatus": 1, "company": "Company", "supplier": label["vendor_name"],
                  "bill_no": "INV-1", "bill_date": label["invoice_date"], "posting_date": label["invoice_date"],
                  "due_date": label["due_date"], "currency": "USD", "credit_to": "Payable",
                  "conversion_rate": 1, "net_total": 100, "grand_total": 100, "total_taxes_and_charges": 0,
                  "items": [{"item_code": "Kit", "description": "Kit", "uom": "EA", "qty": 2, "rate": 50,
                             "amount": 100, "purchase_order": "PO1", "po_detail": "POL1",
                             "purchase_receipt": "PR1", "pr_detail": "PRL1", "expense_account": "Expense"}]}
        ledger = [{"company": "Company", "voucher_no": "PI1", "voucher_type": "Purchase Invoice",
                   "is_cancelled": 0, "account": account, "debit": debit, "credit": credit}
                  for account, debit, credit in (("Expense", 100, 0), ("Payable", 0, 100))]
        self.assertEqual(independent_readback(label, source, profile, actual, ledger), [])
        actual["due_date"] = "2026-12-10"
        ledger[0]["debit"] = 99
        self.assertEqual(independent_readback(label, source, profile, actual, ledger),
                         ["due_date", "ledger_accounts_or_amounts"])

    def test_correct_hold_without_authorized_disposition_is_not_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory)
            (pack / "manifest.json").write_text("{}")
            label = self.label("held")
            (pack / "expected-match.json").write_text(json.dumps([{
                "document_id": "held", "expected_action": "hold", "issue_codes": ["receipt_shortfall"]}]))
            dataset = SimpleNamespace(documents=[SimpleNamespace(document_id="held", expected_fields=label,
                                                                 source_path=pack / "invoice.pdf")])
            observation = {"document_id": "held", "predicted_fields": label, "stages": [],
                "workflow": {"action": "hold", "state": "match_hold", "issue_codes": ["receipt_shortfall"]}}
            report = summarize(pack, "quality_holdout", dataset, [observation], {})["pipeline"]
            self.assertEqual(report["correct_hold_decisions"], 1)
            self.assertEqual(report["strict_correct_terminal"], 0)
            observation["workflow"].update(state="exception_resolved", disposition_status="rejected",
                dispositions=[{"state": "rejected", "authorizer": "Approver", "evidence_refs": ["source1"]}])
            report = summarize(pack, "quality_holdout", dataset, [observation], {})["pipeline"]
            self.assertEqual(report["strict_correct_terminal"], 1)
            self.assertEqual(report["completed_exception_dispositions"], 1)

    def test_missing_or_unrelated_source_anchor_cannot_be_attested(self):
        revision = {"fields": {"vendor_name": {"effective": "Harbor Components"},
                                "total": {"effective": "100.00"}}}
        predicted = {"provenance": {"vendor_name": {"page": 1, "excerpt": "Other Components"},
                                    "total": {"page": 2, "excerpt": "100.00"}}}
        self.assertEqual(_grounded_fields(revision, predicted, {1: "Other Components 100.00"}), {})


if __name__ == "__main__":
    unittest.main()
