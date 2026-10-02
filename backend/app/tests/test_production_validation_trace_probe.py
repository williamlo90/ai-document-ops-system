from __future__ import annotations

import unittest

from scripts.production_validation.trace_probe import build_trace_query, evaluate_trace_rows


class ProductionValidationTraceProbeTests(unittest.TestCase):
    def test_query_is_scoped_to_exact_trace_id(self) -> None:
        trace_id = "a" * 32

        query = build_trace_query(trace_id)

        self.assertIn(trace_id, query)
        self.assertIn("ContainerAppConsoleLogs_CL", query)
        with self.assertRaises(ValueError):
            build_trace_query("not-a-trace")

    def test_complete_chain_requires_api_publish_worker_and_terminal_events(self) -> None:
        rows = [
            {"Log_s": "request_completed"},
            {"Log_s": "queue_wakeup_published"},
            {"Log_s": "queue_message_completed"},
            {"Log_s": "processing_succeeded"},
        ]

        evaluation = evaluate_trace_rows(rows)

        self.assertTrue(evaluation["passed"])

    def test_missing_terminal_event_fails(self) -> None:
        rows = [
            {"Log_s": "request_completed"},
            {"Log_s": "queue_wakeup_published"},
            {"Log_s": "queue_message_completed"},
        ]

        evaluation = evaluate_trace_rows(rows)

        self.assertFalse(evaluation["passed"])
        self.assertFalse(evaluation["stages"]["terminal"]["passed"])


if __name__ == "__main__":
    unittest.main()
