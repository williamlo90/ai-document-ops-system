from __future__ import annotations

import unittest

from app.agent.contracts import (
    BLOCKED_ACTIONS,
    TOOL_DEFINITIONS,
    TOOL_REGISTRY,
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolResponse,
    AgentToolRisk,
    allowed_tools_for_context,
    get_tool_definition,
    requires_confirmation,
)
from app.core.security import SecurityContext


class AgentToolContractTests(unittest.TestCase):
    def test_registry_contains_unique_initial_tools(self) -> None:
        names = [tool.name for tool in TOOL_DEFINITIONS]

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(AgentToolName))
        self.assertEqual(set(TOOL_REGISTRY), set(AgentToolName))

    def test_mutating_tools_require_confirmation(self) -> None:
        for tool in TOOL_DEFINITIONS:
            with self.subTest(tool=tool.name):
                if tool.risk == AgentToolRisk.READ_ONLY:
                    self.assertFalse(tool.requires_confirmation)
                else:
                    self.assertTrue(tool.requires_confirmation)

    def test_every_tool_maps_to_project2_capability(self) -> None:
        for tool in TOOL_DEFINITIONS:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.project2_capability)
                self.assertNotEqual(tool.risk, AgentToolRisk.BLOCKED)

    def test_tool_contracts_include_failure_taxonomy(self) -> None:
        for tool in TOOL_DEFINITIONS:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.failure_types)
                self.assertTrue(
                    all(isinstance(failure, AgentFailureType) for failure in tool.failure_types)
                )

    def test_role_gates_match_tool_risk(self) -> None:
        admin = SecurityContext(actor="admin", is_admin=True, role="admin")
        operator = SecurityContext(actor="operator", is_admin=False, role="operator")
        reviewer = SecurityContext(actor="reviewer", is_admin=False, role="reviewer")

        admin_tools = {tool.name for tool in allowed_tools_for_context(admin)}
        operator_tools = {tool.name for tool in allowed_tools_for_context(operator)}
        reviewer_tools = {tool.name for tool in allowed_tools_for_context(reviewer)}

        self.assertIn(AgentToolName.EXPORT_APPROVED_CSV, admin_tools)
        self.assertNotIn(AgentToolName.EXPORT_APPROVED_CSV, operator_tools)
        self.assertNotIn(AgentToolName.SEND_ACCOUNTING_INTEGRATION, reviewer_tools)
        self.assertIn(AgentToolName.LIST_DOCUMENTS, operator_tools)
        self.assertIn(AgentToolName.LIST_REVIEW_QUEUE, reviewer_tools)
        self.assertNotIn(AgentToolName.LIST_REVIEW_QUEUE, operator_tools)

    def test_fake_admin_role_without_admin_access_gets_no_admin_tools(self) -> None:
        fake_admin = SecurityContext(actor="fake", is_admin=False, role="admin")

        tools = {tool.name for tool in allowed_tools_for_context(fake_admin)}

        self.assertEqual(tools, set())

    def test_get_tool_and_confirmation_helpers(self) -> None:
        definition = get_tool_definition("process_document")

        self.assertEqual(definition.name, AgentToolName.PROCESS_DOCUMENT)
        self.assertTrue(requires_confirmation(AgentToolName.PROCESS_DOCUMENT))
        self.assertFalse(requires_confirmation("list_documents"))

    def test_blocked_actions_cover_unsafe_boundaries(self) -> None:
        expected = {
            "edit_database_record",
            "change_workspace_id",
            "read_env_file",
            "send_arbitrary_http_request",
            "invent_invoice_fields",
        }

        self.assertTrue(expected.issubset(set(BLOCKED_ACTIONS)))

    def test_escalated_response_uses_low_confidence_and_failure_type(self) -> None:
        response = AgentToolResponse.escalated(
            tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
            risk=AgentToolRisk.READ_ONLY,
            summary="Human review is required because evidence is insufficient",
        )

        self.assertEqual(response.status, "escalated")
        self.assertEqual(response.confidence, AgentConfidence.LOW)
        self.assertTrue(response.requires_follow_up)
        self.assertEqual(response.failure_type, AgentFailureType.INSUFFICIENT_EVIDENCE)
        self.assertIn("Human review", response.human_escalation_reason or "")


if __name__ == "__main__":
    unittest.main()
