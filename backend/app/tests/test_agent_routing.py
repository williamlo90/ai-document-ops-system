from __future__ import annotations

import unittest
from uuid import uuid4

from app.agent.contracts import AgentToolName
from app.agent.routing import CopilotIntentRouter
from app.agent.types import CopilotRequest


class CopilotIntentRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = CopilotIntentRouter()

    def test_routes_supported_requests_from_ordered_rules(self) -> None:
        cases = (
            ("Is storage healthy?", AgentToolName.GET_READINESS),
            ("Show the human review queue", AgentToolName.LIST_REVIEW_QUEUE),
            ("Summarize workflow cost", AgentToolName.GET_METRICS_SUMMARY),
            ("List every invoice", AgentToolName.LIST_DOCUMENTS),
            ("What is happening?", AgentToolName.GET_METRICS_SUMMARY),
        )

        for message, expected_tool in cases:
            with self.subTest(message=message):
                route = self.router.route(CopilotRequest(message=message))
                self.assertEqual(route.tool_name, expected_tool)

    def test_explicit_execution_and_document_context_take_precedence(self) -> None:
        execute_route = self.router.route(
            CopilotRequest(
                message="Show document health",
                document_id=uuid4(),
                execute_tool=AgentToolName.PROCESS_DOCUMENT,
            )
        )
        detail_route = self.router.route(
            CopilotRequest(message="Show storage health", document_id=uuid4())
        )

        self.assertEqual(execute_route.tool_name, AgentToolName.PROCESS_DOCUMENT)
        self.assertEqual(execute_route.intent, "execute_controlled_tool")
        self.assertEqual(detail_route.tool_name, AgentToolName.GET_DOCUMENT_DETAIL)

    def test_overlapping_keywords_use_declared_rule_order(self) -> None:
        route = self.router.route(CopilotRequest(message="Review current workflow status"))

        self.assertEqual(route.tool_name, AgentToolName.LIST_REVIEW_QUEUE)

    def test_mutation_detection_is_table_driven(self) -> None:
        cases = (
            ("Approve this invoice", True),
            ("Please export approved invoices", True),
            ("Explain this invoice", False),
        )

        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(self.router.is_mutation_request(message), expected)


if __name__ == "__main__":
    unittest.main()
