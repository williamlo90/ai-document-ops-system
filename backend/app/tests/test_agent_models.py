from __future__ import annotations

import unittest
from decimal import Decimal
from uuid import uuid4

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolRisk,
)
from app.agent.models import (
    DEFAULT_PROMPT_VERSION,
    AgentRun,
    AgentTokenUsage,
    AgentToolCallTrace,
)
from app.agent.repositories import InMemoryAgentRunRepository
from app.documents.repositories import NotFoundError


class AgentModelTests(unittest.TestCase):
    def test_agent_run_carries_project35_evaluation_fields(self) -> None:
        run = AgentRun(
            workspace_id="acme",
            actor="operator-1",
            request="What needs review?",
            intent="summarize_attention",
            confidence=AgentConfidence.HIGH,
            expected_tool=AgentToolName.LIST_REVIEW_QUEUE,
            selected_tool=AgentToolName.LIST_REVIEW_QUEUE,
            selection_reason="The request asks for documents needing human review.",
            why_not="Export is not recommended because review is still pending.",
            token_usage=AgentTokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                estimated_cost=Decimal("0.001"),
            ),
        )

        self.assertEqual(run.prompt_version, DEFAULT_PROMPT_VERSION)
        self.assertEqual(
            run.tool_selection_pair,
            (AgentToolName.LIST_REVIEW_QUEUE, AgentToolName.LIST_REVIEW_QUEUE),
        )
        self.assertEqual(run.token_usage.estimated_cost, Decimal("0.001"))
        self.assertIn("review", run.why_not or "")

    def test_agent_run_tracks_tool_calls_blocked_actions_and_completion(self) -> None:
        run = AgentRun(
            workspace_id="default",
            actor="admin",
            request="Export this",
            intent="export_request",
            selected_tool=AgentToolName.EXPORT_APPROVED_CSV,
        )
        trace = AgentToolCallTrace(
            tool_name=AgentToolName.EXPORT_APPROVED_CSV,
            risk=AgentToolRisk.ADMIN_ACTION,
            status="failed",
            summary="Confirmation required",
            confidence=AgentConfidence.LOW,
            failure_type=AgentFailureType.CONFIRMATION_REQUIRED,
            human_escalation_reason="Human confirmation is required before export.",
        )

        before_update = run.updated_at
        run.add_tool_call(trace)
        run.block_action("export requires confirmation")
        run.complete("Export was not executed.")

        self.assertEqual(run.tool_calls, [trace])
        self.assertEqual(run.blocked_actions, ["export requires confirmation"])
        self.assertEqual(run.final_summary, "Export was not executed.")
        self.assertTrue(run.has_human_escalation)
        self.assertGreater(run.updated_at, before_update)

    def test_repository_saves_gets_and_lists_recent_by_workspace(self) -> None:
        repository = InMemoryAgentRunRepository()
        acme_old = repository.add(
            AgentRun(
                workspace_id="acme",
                actor="admin",
                request="old",
                intent="summary",
            )
        )
        other = repository.add(
            AgentRun(
                workspace_id="other",
                actor="admin",
                request="other",
                intent="summary",
            )
        )
        acme_new = repository.add(
            AgentRun(
                workspace_id="acme",
                actor="admin",
                request="new",
                intent="summary",
            )
        )

        self.assertEqual(repository.get(acme_old.id), acme_old)
        self.assertEqual(repository.get(other.id), other)
        self.assertEqual(repository.list_recent("acme"), [acme_new, acme_old])
        self.assertEqual(repository.list_recent("acme", limit=1), [acme_new])
        self.assertEqual(repository.list_recent("missing"), [])

    def test_repository_unknown_run_is_not_found(self) -> None:
        repository = InMemoryAgentRunRepository()

        with self.assertRaises(NotFoundError):
            repository.get(uuid4())


if __name__ == "__main__":
    unittest.main()
