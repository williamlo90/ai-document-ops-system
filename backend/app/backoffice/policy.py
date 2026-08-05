from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.backoffice.models import (
    ActionRiskLevel,
    ActionType,
    AutonomyLevel,
    PolicyDecision,
    WorkItem,
)
from app.core.security import SecurityContext


@dataclass(frozen=True)
class ActionPolicyRule:
    autonomy_level: AutonomyLevel
    risk_level: ActionRiskLevel
    requires_confirmation: bool
    allowed_roles: frozenset[str]
    reason: str


ACTION_POLICY_RULES: Mapping[ActionType, ActionPolicyRule] = MappingProxyType(
    {
        ActionType.INSPECT_QUEUE: ActionPolicyRule(
            autonomy_level=AutonomyLevel.READ_ONLY,
            risk_level=ActionRiskLevel.LOW,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Read-only queue inspection does not mutate workflow state.",
        ),
        ActionType.EXPLAIN_DOCUMENT: ActionPolicyRule(
            autonomy_level=AutonomyLevel.READ_ONLY,
            risk_level=ActionRiskLevel.LOW,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Document explanation is read-only and scoped to the caller workspace.",
        ),
        ActionType.RECOMMEND_REVIEW: ActionPolicyRule(
            autonomy_level=AutonomyLevel.RECOMMEND,
            risk_level=ActionRiskLevel.LOW,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Recommendation creates no side effect and requires evidence.",
        ),
        ActionType.DRAFT_ACCOUNTING_NOTE: ActionPolicyRule(
            autonomy_level=AutonomyLevel.DRAFT,
            risk_level=ActionRiskLevel.MEDIUM,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Drafting an accounting note has no external side effect until approved.",
        ),
        ActionType.DRAFT_VENDOR_MESSAGE: ActionPolicyRule(
            autonomy_level=AutonomyLevel.DRAFT,
            risk_level=ActionRiskLevel.MEDIUM,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Drafting a vendor message is reviewable and does not send anything.",
        ),
        ActionType.PROCESS_DOCUMENT: ActionPolicyRule(
            autonomy_level=AutonomyLevel.CONFIRM_EXECUTE,
            risk_level=ActionRiskLevel.HIGH,
            requires_confirmation=True,
            allowed_roles=frozenset({"admin", "operator"}),
            reason="Processing mutates document workflow state and requires confirmation.",
        ),
        ActionType.EXPORT_APPROVED_INVOICE: ActionPolicyRule(
            autonomy_level=AutonomyLevel.CONFIRM_EXECUTE,
            risk_level=ActionRiskLevel.HIGH,
            requires_confirmation=True,
            allowed_roles=frozenset({"admin"}),
            reason="Export is a high-risk business action and requires admin confirmation.",
        ),
        ActionType.ESCALATE_TO_HUMAN: ActionPolicyRule(
            autonomy_level=AutonomyLevel.RECOMMEND,
            risk_level=ActionRiskLevel.MEDIUM,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Human escalation is allowed when evidence or confidence is insufficient.",
        ),
        ActionType.BLOCK_UNSAFE_REQUEST: ActionPolicyRule(
            autonomy_level=AutonomyLevel.BLOCKED,
            risk_level=ActionRiskLevel.BLOCKED,
            requires_confirmation=False,
            allowed_roles=frozenset({"admin", "operator", "reviewer"}),
            reason="Unsafe requests must be refused instead of routed to execution.",
        ),
    }
)


class UnsupportedBackofficeActionError(ValueError):
    pass


class AutonomyPolicyEngine:
    def decide(
        self,
        *,
        work_item: WorkItem,
        action_type: ActionType | str,
        context: SecurityContext,
        action_step_id=None,
        target_workspace_id: str | None = None,
        evidence_sufficient: bool = True,
        confirmed: bool = False,
    ) -> PolicyDecision:
        action = self._normalize_action(action_type)
        rule = ACTION_POLICY_RULES[action]

        blocked_reason = self._blocked_reason(
            work_item=work_item,
            action=action,
            rule=rule,
            context=context,
            target_workspace_id=target_workspace_id,
            evidence_sufficient=evidence_sufficient,
            confirmed=confirmed,
        )
        if blocked_reason is not None:
            return PolicyDecision(
                workspace_id=work_item.workspace_id,
                work_item_id=work_item.id,
                action_type=action,
                action_step_id=action_step_id,
                autonomy_level=AutonomyLevel.BLOCKED,
                risk_level=ActionRiskLevel.BLOCKED,
                allowed=False,
                requires_confirmation=rule.requires_confirmation and not confirmed,
                reason=blocked_reason,
            )

        return PolicyDecision(
            workspace_id=work_item.workspace_id,
            work_item_id=work_item.id,
            action_type=action,
            action_step_id=action_step_id,
            autonomy_level=rule.autonomy_level,
            risk_level=rule.risk_level,
            allowed=True,
            requires_confirmation=rule.requires_confirmation and not confirmed,
            reason=rule.reason,
        )

    def _normalize_action(self, action_type: ActionType | str) -> ActionType:
        try:
            return ActionType(action_type)
        except ValueError as exc:
            raise UnsupportedBackofficeActionError(f"Unsupported action: {action_type}") from exc

    def _blocked_reason(
        self,
        *,
        work_item: WorkItem,
        action: ActionType,
        rule: ActionPolicyRule,
        context: SecurityContext,
        target_workspace_id: str | None,
        evidence_sufficient: bool,
        confirmed: bool,
    ) -> str | None:
        if action == ActionType.BLOCK_UNSAFE_REQUEST:
            return "Action is explicitly classified as unsafe and must be blocked."
        if context.workspace_id != work_item.workspace_id:
            return "Caller workspace does not match the work item workspace."
        if target_workspace_id is not None and target_workspace_id != work_item.workspace_id:
            return "Cross-workspace action target is not allowed."
        if context.role == "admin" and not context.is_admin:
            return "Claimed admin role does not have admin access."
        if context.role not in rule.allowed_roles:
            return "Current role is not allowed to perform this action."
        if not evidence_sufficient and rule.autonomy_level != AutonomyLevel.READ_ONLY:
            return "Insufficient evidence; escalate to a human before continuing."
        if rule.requires_confirmation and not confirmed:
            return "Explicit confirmation is required before this action can execute."
        return None
