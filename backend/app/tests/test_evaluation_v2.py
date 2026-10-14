from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import unittest

from app.benchmark.service import invoice_data_to_fields
from app.evaluation.external_holdout import build_external_evaluation_summary
from app.evaluation.invoice import evaluate_invoices, report_to_dict
from app.extraction.schemas import InvoiceData, InvoiceLineItem


def invoice() -> dict:
    record = {
        "document_id": "invoice-1",
        "vendor_name": "Supplier A",
        "invoice_number": "INV-01",
        "invoice_date": "2026-10-01",
        "due_date": None,
        "subtotal": "125.00",
        "tax": "0",
        "total": "125",
        "currency": "USD",
        "expected_validation_codes": [],
        "line_items": [
            {"description": "Bolts", "quantity": "2", "unit_price": "50", "amount": "100"},
            {"description": "Nuts", "quantity": "1", "unit_price": "25", "amount": "25"},
        ],
    }
    for row in record["line_items"]:
        row["uom"] = "EA"
    for row in [record, *record["line_items"]]:
        keys = (
            (
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "due_date",
                "subtotal",
                "tax",
                "total",
                "currency",
            )
            if row is record
            else ("description", "uom", "quantity", "unit_price", "amount")
        )
        row["provenance"] = {
            k: {"kind": "observed", "page": 1, "excerpt": str(row[k])}
            for k in keys
            if row[k] is not None
        }
    return record


def score(expected: dict, predicted: dict | None) -> dict:
    return report_to_dict(evaluate_invoices([expected], [predicted] if predicted else []))


def observation(predicted: dict | None = None) -> dict:
    return {
        "document_id": "invoice-1",
        "predicted_fields": predicted or invoice(),
        "predicted_validation_codes": [],
        "error": None,
    }


def summary(expected: list, observations: list) -> dict:
    return build_external_evaluation_summary(
        expected, observations, split="diagnostic", provider="fixture"
    )


class InvoiceEvaluationV2Tests(unittest.TestCase):
    def test_line_only_mutation_cannot_keep_full_invoice_perfect(self):
        expected = invoice()
        for field in ("quantity", "unit_price", "amount"):
            with self.subTest(field=field):
                predicted = deepcopy(expected)
                predicted["line_items"][0][field] = "999"
                result = score(expected, predicted)
                self.assertEqual(result["field_accuracy"], 1)
                self.assertEqual(result["full_invoice_exact_match_rate"], 0)
                self.assertEqual(result["line_items"]["fields_matched"], 9)
                self.assertEqual(result["line_items"]["recall"], 0.5)

    def test_missing_extra_and_changed_description_are_reported(self):
        expected = invoice()
        missing = deepcopy(expected)
        missing["line_items"].pop()
        result = score(expected, missing)
        self.assertEqual(result["line_items"]["missing_lines"], 1)
        self.assertEqual(result["line_items"]["field_accuracy"], 0.5)
        extra = deepcopy(expected)
        extra["line_items"].append(deepcopy(extra["line_items"][0]))
        result = score(expected, extra)
        self.assertEqual(result["line_items"]["extra_lines"], 1)
        self.assertEqual(result["line_items"]["precision"], 0.6667)
        self.assertEqual(result["full_invoice_exact_match_rate"], 0)
        renamed = deepcopy(expected)
        renamed["line_items"][0]["description"] = "Washers"
        self.assertEqual(score(expected, renamed)["line_items"]["missing_lines"], 1)

    def test_reordering_and_repeated_descriptions_are_multisets(self):
        expected = invoice()
        expected["line_items"][1] = deepcopy(expected["line_items"][0])
        expected["line_items"].append(deepcopy(expected["line_items"][0]))
        predicted = deepcopy(expected)
        predicted["line_items"].reverse()
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 1)
        predicted["line_items"].pop()
        self.assertEqual(score(expected, predicted)["line_items"]["missing_lines"], 1)

    def test_normalization_preserves_meaning_and_unit_price_precision(self):
        expected = invoice()
        predicted = deepcopy(expected)
        predicted.update(vendor_name=" SUPPLIER   A ", currency="usd", invoice_date="20261001")
        predicted["line_items"][0].update(description=" BOLTS ", quantity="2.0", amount="100.00")
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 1)
        predicted["line_items"][0]["unit_price"] = "50.001"
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_unknown_lines_are_not_the_same_as_labeled_empty_lines(self):
        expected = invoice()
        del expected["line_items"]
        result = score(expected, expected)
        self.assertIsNone(result["full_invoice_exact_match_rate"])
        self.assertEqual(result["line_items"]["status"], "not_labeled")
        expected["line_items"] = []
        self.assertEqual(score(expected, expected)["full_invoice_exact_match_rate"], 1)
        predicted = deepcopy(expected)
        del predicted["line_items"]
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_invalid_prediction_fails_without_aborting_other_documents(self):
        expected = invoice()
        for value in (None, "bad", [None]):
            predicted = deepcopy(expected)
            predicted["line_items"] = value
            self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)
        for value in ("NaN", "Infinity", "not-a-number"):
            predicted = deepcopy(expected)
            predicted["line_items"][0]["quantity"] = value
            predicted["total"] = value
            self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)
        predicted["invoice_date"] = "not-a-date"
        self.assertEqual(score(expected, predicted)["header_exact_match_rate"], 0)

    def test_missing_field_key_cannot_match_null_label(self):
        expected = invoice()
        predicted = deepcopy(expected)
        del predicted["due_date"]
        self.assertEqual(score(expected, predicted)["header_exact_match_rate"], 0)
        expected["line_items"][0]["amount"] = None
        predicted = deepcopy(expected)
        del predicted["line_items"][0]["amount"]
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_empty_and_partial_label_denominators(self):
        result = report_to_dict(evaluate_invoices([], []))
        self.assertIsNone(result["header_field_accuracy"])
        self.assertIsNone(result["full_invoice_exact_match_rate"])
        self.assertIsNone(result["line_items"]["field_accuracy"])
        legacy = invoice()
        legacy["document_id"] = "legacy"
        del legacy["line_items"]
        result = report_to_dict(evaluate_invoices([invoice(), legacy], [invoice(), legacy]))
        self.assertEqual(result["full_invoice_documents_total"], 1)
        self.assertEqual(result["full_invoice_label_coverage"], 0.5)

    def test_invalid_expected_labels_and_duplicate_ids_are_rejected(self):
        for value in (None, {}, [{"description": "Bolts"}]):
            bad = invoice()
            bad["line_items"] = value
            with self.assertRaises(ValueError):
                score(bad, invoice())
        for expected, predicted in (
            ([invoice(), invoice()], []),
            ([invoice()], [invoice(), invoice()]),
        ):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                evaluate_invoices(expected, predicted)
        for identity in (None, "", " x "):
            bad = invoice()
            bad["document_id"] = identity
            with self.assertRaises(ValueError):
                score(bad, None)

    def test_provenance_is_required_and_wrong_anchor_fails(self):
        expected = invoice()
        for mutate in (
            lambda p: p.pop("provenance"),
            lambda p: p["provenance"]["total"].update(page=99),
            lambda p: p["line_items"][0]["provenance"].pop("quantity"),
            lambda p: p["line_items"][0].update(uom="BOX"),
        ):
            predicted = deepcopy(expected)
            mutate(predicted)
            self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)
        expected.pop("provenance")
        self.assertIsNone(score(expected, expected)["full_invoice_exact_match_rate"])

    def test_ambiguous_rows_fail_but_stable_references_disambiguate(self):
        expected = invoice()
        expected["line_items"][1]["description"] = "Bolts"
        predicted = deepcopy(expected)
        self.assertEqual(score(expected, predicted)["line_items"]["ambiguous_groups"], 1)
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)
        for i, row in enumerate(expected["line_items"]):
            row["line_reference"] = str(i)
        predicted = deepcopy(expected)
        predicted["line_items"].reverse()
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 1)

    def test_applicable_tax_and_reference_must_match(self):
        expected = invoice()
        for field, value in (("tax", "10"), ("purchase_order", "PO-1")):
            expected["line_items"][0][field] = value
            expected["line_items"][0]["provenance"][field] = {
                "kind": "observed",
                "page": 1,
                "excerpt": value,
            }
        predicted = deepcopy(expected)
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 1)
        del predicted["line_items"][0]["tax"]
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_half_up_and_ambiguous_locale_not_guessed(self):
        expected = invoice()
        expected["total"] = "125.005"
        predicted = deepcopy(expected)
        predicted["total"] = "125.01"
        self.assertEqual(score(expected, predicted)["header_exact_match_rate"], 1)
        predicted["total"] = "125,005"
        self.assertEqual(score(expected, predicted)["header_exact_match_rate"], 0)

    def test_line_provenance_affects_exact_line_precision(self):
        expected = invoice()
        predicted = deepcopy(expected)
        predicted["line_items"][0].pop("provenance")
        result = score(expected, predicted)
        self.assertEqual(result["line_items"]["field_accuracy"], 1)
        self.assertEqual(result["line_items"]["precision"], 0.5)
        self.assertEqual(result["full_invoice_exact_match_rate"], 0)

    def test_derived_value_cannot_claim_observed_evidence(self):
        expected = invoice()
        expected["line_items"][0]["provenance"]["amount"] = {
            "kind": "derived",
            "formula": "quantity * unit_price",
            "inputs": ["quantity", "unit_price"],
        }
        predicted = deepcopy(expected)
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 1)
        predicted["line_items"][0]["provenance"]["amount"] = {
            "kind": "observed",
            "page": 1,
            "excerpt": "100",
        }
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_failed_record_with_residual_fields_cannot_pass(self):
        expected = invoice()
        predicted = deepcopy(expected)
        predicted["error"] = "timeout"
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_blank_does_not_equal_explicit_null(self):
        expected = invoice()
        predicted = deepcopy(expected)
        predicted["due_date"] = ""
        self.assertEqual(score(expected, predicted)["full_invoice_exact_match_rate"], 0)

    def test_provider_serialization_preserves_line_data(self):
        fields = invoice_data_to_fields(
            InvoiceData(
                invoice_date=date(2026, 10, 1),
                line_items=(
                    InvoiceLineItem(
                        description="Bolts",
                        quantity=Decimal("2.5"),
                        unit_price=Decimal("0.1234"),
                        amount=None,
                    ),
                ),
            )
        )
        self.assertEqual(
            fields["line_items"],
            [
                {
                    "description": "Bolts",
                    "quantity": "2.5",
                    "unit_price": "0.1234",
                    "amount": None,
                    "line_id": None,
                    "uom": None,
                    "tax": None,
                    "discount": None,
                }
            ],
        )


class EvaluationExecutionTests(unittest.TestCase):
    def test_failed_missing_and_unexecuted_validation_cannot_pass(self):
        failed = observation()
        failed["error"] = "timeout"
        no_validation = observation()
        del no_validation["predicted_validation_codes"]
        explicitly_unrun = observation()
        explicitly_unrun["validation_completed"] = False
        for observations in ([], [failed], [no_validation], [explicitly_unrun]):
            with self.subTest(observations=observations):
                metrics = summary([invoice()], observations)["metrics"]
                self.assertEqual(metrics["validation_code_exact_match_rate"], 0)
                self.assertEqual(metrics["approval_blocker_accuracy"], 0)
                self.assertEqual(metrics["validation_completion_rate"], 0)
        self.assertEqual(
            summary([invoice()], [failed])["metrics"]["full_invoice_exact_match_rate"], 0
        )

    def test_empty_outputs_not_success_and_empty_dataset_na(self):
        obs = observation()
        obs["predicted_fields"] = {}
        self.assertEqual(summary([invoice()], [obs])["metrics"]["provider_success_rate"], 0)
        metrics = summary([], [])["metrics"]
        self.assertIsNone(metrics["provider_success_rate"])
        self.assertIsNone(metrics["validation_code_exact_match_rate"])
        self.assertIsNone(metrics["header_field_accuracy"])

    def test_duplicates_unknown_ids_and_invalid_validation_labels_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summary([invoice()], [observation(), observation()])
        obs = observation()
        obs["document_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "manifest"):
            summary([invoice()], [obs])
        expected = invoice()
        expected["expected_validation_codes"] = None
        with self.assertRaises(ValueError):
            summary([expected], [observation()])

    def test_aggregate_is_private_and_header_alias_is_still_header_only(self):
        predicted = invoice()
        predicted["line_items"][0]["amount"] = "900"
        report = summary([invoice()], [observation(predicted)])
        self.assertEqual(report["report_version"], "2.1")
        self.assertEqual(report["metrics"]["document_exact_match_rate"], 1)
        self.assertEqual(report["metrics"]["full_invoice_exact_match_rate"], 0)
        self.assertNotIn("invoice-1", str(report))
        self.assertNotIn("Bolts", str(report))

    def test_warning_is_not_automatically_an_approval_blocker(self):
        expected = invoice()
        expected["expected_validation_codes"] = ["warning"]
        expected["expected_approval_blocked"] = False
        obs = observation()
        obs["predicted_validation_codes"] = ["warning"]
        obs["predicted_approval_blocked"] = False
        self.assertEqual(summary([expected], [obs])["metrics"]["approval_blocker_accuracy"], 1)


class FrozenReplayTests(unittest.TestCase):
    def test_rule_scope_does_not_leak_to_other_family_or_layout(self):
        import json
        from pathlib import Path
        from scripts.evaluate_phase1_regressions import apply_rule, replay_corrections

        root = (
            Path(__file__).resolve().parents[3] / "examples/benchmark/datasets/invoice_quality_v2"
        )
        timeline = json.loads((root / "correction-timeline.json").read_text())
        for field in ("family_id", "layout_family"):
            other = deepcopy(timeline["original_proposal"])
            other[field] = "different"
            self.assertEqual(apply_rule(other, timeline, "decimal_comma_v1"), other)
        alternative = deepcopy(timeline["original_proposal"])
        alternative["line_items"][0]["provenance"]["quantity"]["excerpt"] = "12,50"
        self.assertEqual(
            apply_rule(alternative, timeline, "decimal_comma_v1")["line_items"][0]["quantity"],
            "12.5",
        )
        result = replay_corrections(
            json.loads((root / "expected.json").read_text()), root / "correction-timeline.json"
        )
        self.assertTrue(result["original_preserved"])
        self.assertTrue(
            all(
                r["previously_correct_retained"] == r["previously_correct_total"]
                for r in result["revisions"]
            )
        )

    def test_diagnostic_transport_enforces_budget_before_network(self):
        from scripts.run_phase1_diagnostic import bounded_post, MAX_OUTPUT_TOKENS
        from app.providers.contracts import ProviderError

        calls = []

        def post(url, payload, headers):
            calls.append(payload)
            return {}

        send = bounded_post(post)
        with self.assertRaises(ProviderError):
            send("https://example.invalid", {"messages": ["x" * 30000]}, {})
        self.assertEqual(calls, [])
        send("https://example.invalid", {"messages": ["short"]}, {})
        self.assertEqual(calls[0]["max_completion_tokens"], MAX_OUTPUT_TOKENS)


if __name__ == "__main__":
    unittest.main()
