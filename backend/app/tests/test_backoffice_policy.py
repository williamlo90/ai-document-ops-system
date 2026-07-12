from __future__ import annotations

import unittest

from app.backoffice.models import (
    ActionRiskLevel,
    ActionType,
    AutonomyLevel,
    WorkItem,
)
from app.backoffice.policy import (
    ACTION_POLICY_RULES,
    AutonomyPolicyEngine,
    UnsupportedBackofficeActionError,
)
from app.core.security import SecurityContext


class AutonomyPolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = AutonomyPolicyEngine()
        self.work_item = WorkItem(workspace_id="acme", title="Invoice follow-up")

    def test_read_only_action_can_proceed_without_confirmation(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.INSPECT_QUEUE,
            context=SecurityContext(actor="reviewer", workspace_id="acme", role="reviewer"),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.READ_ONLY)
        self.assertEqual(decision.risk_level, ActionRiskLevel.LOW)
        self.assertFalse(decision.requires_confirmation)

    def test_draft_action_has_no_external_side_effect_confirmation(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.DRAFT_VENDOR_MESSAGE,
            context=SecurityContext(actor="operator", workspace_id="acme", role="operator"),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.DRAFT)
        self.assertEqual(decision.risk_level, ActionRiskLevel.MEDIUM)
        self.assertFalse(decision.requires_confirmation)

    def test_high_risk_action_requires_confirmation_before_execution(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.PROCESS_DOCUMENT,
            context=SecurityContext(actor="operator", workspace_id="acme", role="operator"),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.BLOCKED)
        self.assertTrue(decision.requires_confirmation)
        self.assertIn("confirmation", decision.reason.lower())

    def test_confirmed_high_risk_action_can_proceed_for_allowed_role(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.PROCESS_DOCUMENT,
            context=SecurityContext(actor="operator", workspace_id="acme", role="operator"),
            confirmed=True,
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.CONFIRM_EXECUTE)
        self.assertEqual(decision.risk_level, ActionRiskLevel.HIGH)
        self.assertFalse(decision.requires_confirmation)

    def test_admin_only_export_blocks_operator_even_when_confirmed(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.EXPORT_APPROVED_INVOICE,
            context=SecurityContext(actor="operator", workspace_id="acme", role="operator"),
            confirmed=True,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, ActionRiskLevel.BLOCKED)
        self.assertIn("role", decision.reason.lower())

    def test_cross_workspace_target_is_blocked(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.EXPLAIN_DOCUMENT,
            context=SecurityContext(
                actor="admin", workspace_id="acme", role="admin", is_admin=True
            ),
            target_workspace_id="other",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.BLOCKED)
        self.assertIn("cross-workspace", decision.reason.lower())

    def test_mismatched_context_workspace_is_blocked(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.INSPECT_QUEUE,
            context=SecurityContext(
                actor="admin", workspace_id="other", role="admin", is_admin=True
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("workspace", decision.reason.lower())

    def test_insufficient_evidence_blocks_non_read_only_action(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.RECOMMEND_REVIEW,
            context=SecurityContext(actor="operator", workspace_id="acme", role="operator"),
            evidence_sufficient=False,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.BLOCKED)
        self.assertIn("insufficient evidence", decision.reason.lower())

    def test_explicitly_unsafe_action_is_blocked(self) -> None:
        decision = self.engine.decide(
            work_item=self.work_item,
            action_type=ActionType.BLOCK_UNSAFE_REQUEST,
            context=SecurityContext(
                actor="admin", workspace_id="acme", role="admin", is_admin=True
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, ActionRiskLevel.BLOCKED)
        self.assertIn("unsafe", decision.reason.lower())

    def test_unsupported_action_raises_clear_error(self) -> None:
        with self.assertRaises(UnsupportedBackofficeActionError):
            self.engine.decide(
                work_item=self.work_item,
                action_type="wire_money",
                context=SecurityContext(
                    actor="admin", workspace_id="acme", role="admin", is_admin=True
                ),
            )

    def test_all_action_types_have_policy_rules(self) -> None:
        self.assertEqual(set(ACTION_POLICY_RULES), set(ActionType))


if __name__ == "__main__":
    unittest.main()
