from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.backoffice.models import (
    ActionStep,
    ActionType,
    TaskPlan,
    WorkItem,
    WorkType,
)
from app.backoffice.policy import ACTION_POLICY_RULES, AutonomyPolicyEngine
from app.core.security import SecurityContext


PLANNER_VERSION = "deterministic-backoffice-v1"


@dataclass(frozen=True)
class PlanningInput:
    requested_outcome: str | None = None
    evidence_sufficient: bool = True
    approved_for_export: bool = False
    missing_fields: tuple[str, ...] = ()
    selected_document_id: UUID | None = None


class BackofficePlanner:
    def __init__(self, policy: AutonomyPolicyEngine | None = None) -> None:
        self.policy = policy or AutonomyPolicyEngine()

    def plan(
        self,
        *,
        work_item: WorkItem,
        context: SecurityContext,
        planning_input: PlanningInput | None = None,
    ) -> TaskPlan:
        inputs = planning_input or PlanningInput()
        work_type = work_item.work_type or self.classify_work_type(work_item, inputs)
        if work_item.work_type is None:
            work_item.classify(work_type)

        plan = TaskPlan(
            workspace_id=work_item.workspace_id,
            work_item_id=work_item.id,
            planner_version=PLANNER_VERSION,
            overall_confidence=self._confidence_for(work_item, inputs),
        )

        if work_type == WorkType.INSUFFICIENT_EVIDENCE or not inputs.evidence_sufficient:
            plan.escalation_reason = "Insufficient evidence for autonomous planning."
            plan.add_step(
                self._step(
                    work_item=work_item,
                    action_type=ActionType.ESCALATE_TO_HUMAN,
                    context=context,
                    evidence_sufficient=True,
                    why_this="Human review is safer when evidence is missing or confidence is low.",
                    why_not="Do not create mutating or outbound actions without enough evidence.",
                )
            )
            work_item.set_current_plan(plan.id)
            return plan

        if work_type == WorkType.INVOICE_REVIEW:
            self._add_invoice_review_steps(plan, work_item, context, inputs)
        elif work_type == WorkType.INVOICE_EXPORT:
            self._add_invoice_export_steps(plan, work_item, context, inputs)
        elif work_type == WorkType.ACCOUNTING_NOTE:
            self._add_accounting_note_steps(plan, work_item, context, inputs)
        elif work_type == WorkType.VENDOR_FOLLOW_UP:
            self._add_vendor_follow_up_steps(plan, work_item, context, inputs)
        else:
            plan.escalation_reason = (
                f"Unsupported work type for deterministic planner: {work_type}."
            )
            plan.add_step(
                self._step(
                    work_item=work_item,
                    action_type=ActionType.ESCALATE_TO_HUMAN,
                    context=context,
                    evidence_sufficient=True,
                    why_this="The planner does not have a safe deterministic workflow for this case.",
                    why_not="Do not invent an autonomous workflow outside the supported playbook.",
                )
            )

        work_item.set_current_plan(plan.id)
        return plan

    def classify_work_type(self, work_item: WorkItem, inputs: PlanningInput) -> WorkType:
        requested = (inputs.requested_outcome or "").strip().lower()
        context_values = " ".join(work_item.business_context.values()).lower()
        combined = f"{requested} {context_values}"

        if inputs.missing_fields or "missing" in combined or "follow" in combined:
            return WorkType.VENDOR_FOLLOW_UP
        if "export" in combined:
            return WorkType.INVOICE_EXPORT
        if "accounting note" in combined or "note" in combined:
            return WorkType.ACCOUNTING_NOTE
        if work_item.linked_document_ids or "invoice" in combined:
            return WorkType.INVOICE_REVIEW
        return WorkType.INSUFFICIENT_EVIDENCE

    def _add_invoice_review_steps(
        self,
        plan: TaskPlan,
        work_item: WorkItem,
        context: SecurityContext,
        inputs: PlanningInput,
    ) -> None:
        plan.add_step(
            self._step(
                work_item=work_item,
                action_type=ActionType.EXPLAIN_DOCUMENT,
                context=context,
                evidence_sufficient=bool(work_item.linked_document_ids),
                why_this="Review starts by explaining the linked document and validation evidence.",
                why_not="Do not approve or export before review evidence is understood.",
            )
        )
        plan.add_step(
            self._step(
                work_item=work_item,
                action_type=ActionType.RECOMMEND_REVIEW,
                context=context,
                evidence_sufficient=inputs.evidence_sufficient,
                why_this="The next safe step is a recommendation, not direct mutation.",
                why_not="Direct execution is unnecessary for an invoice review plan.",
            )
        )

    def _add_invoice_export_steps(
        self,
        plan: TaskPlan,
        work_item: WorkItem,
        context: SecurityContext,
        inputs: PlanningInput,
    ) -> None:
        plan.add_step(
            self._step(
                work_item=work_item,
                action_type=ActionType.INSPECT_QUEUE,
                context=context,
                evidence_sufficient=True,
                why_this="Export planning should first inspect available approved work.",
                why_not="Do not export until approval state has been checked.",
            )
        )
        if not inputs.approved_for_export:
            plan.escalation_reason = "Invoice export requires approved invoice evidence."
            step = self._base_step(
                action_type=ActionType.EXPORT_APPROVED_INVOICE,
                why_this="Export was requested.",
                why_not="Not recommended: export requires an approved invoice first.",
            )
            step.block("Invoice is not approved for export.")
            plan.add_step(step)
            return

        plan.add_step(
            self._step(
                work_item=work_item,
                action_type=ActionType.EXPORT_APPROVED_INVOICE,
                context=context,
                evidence_sufficient=True,
                why_this="Approved invoice evidence exists, so export can be prepared.",
                why_not="Do not run export without explicit admin confirmation.",
            )
        )

    def _add_accounting_note_steps(
        self,
        plan: TaskPlan,
        work_item: WorkItem,
        context: SecurityContext,
        inputs: PlanningInput,
    ) -> None:
        if work_item.linked_document_ids:
            plan.add_step(
                self._step(
                    work_item=work_item,
                    action_type=ActionType.EXPLAIN_DOCUMENT,
                    context=context,
                    evidence_sufficient=True,
                    why_this="The accounting note should be grounded in document evidence.",
                    why_not="Do not draft a note from unsupported assumptions.",
                )
            )
        plan.add_step(
            self._step(
                work_item=work_item,
                action_type=ActionType.DRAFT_ACCOUNTING_NOTE,
                context=context,
                evidence_sufficient=inputs.evidence_sufficient,
                why_this="Drafting a note creates a reviewable artifact without external side effects.",
                why_not="Do not post the note automatically.",
            )
        )

    def _add_vendor_follow_up_steps(
        self,
        plan: TaskPlan,
        work_item: WorkItem,
        context: SecurityContext,
        inputs: PlanningInput,
    ) -> None:
        if work_item.linked_document_ids:
            plan.add_step(
                self._step(
                    work_item=work_item,
                    action_type=ActionType.EXPLAIN_DOCUMENT,
                    context=context,
                    evidence_sufficient=True,
                    why_this="The follow-up draft should cite the missing document evidence.",
                    why_not="Do not ask the vendor for fields that are already present.",
                )
            )
        missing = ", ".join(inputs.missing_fields) if inputs.missing_fields else "missing evidence"
        plan.add_step(
            self._step(
                work_item=work_item,
                action_type=ActionType.DRAFT_VENDOR_MESSAGE,
                context=context,
                evidence_sufficient=True,
                why_this=f"Draft a vendor follow-up for {missing}.",
                why_not="Do not send the message automatically; keep it reviewable.",
            )
        )

    def _step(
        self,
        *,
        work_item: WorkItem,
        action_type: ActionType,
        context: SecurityContext,
        evidence_sufficient: bool,
        why_this: str,
        why_not: str,
    ) -> ActionStep:
        decision = self.policy.decide(
            work_item=work_item,
            action_type=action_type,
            context=context,
            evidence_sufficient=evidence_sufficient,
        )
        step = self._base_step(
            action_type=action_type,
            why_this=why_this,
            why_not=why_not,
        )
        if decision.requires_confirmation:
            step.requires_approval = True
            step.mark_waiting_for_approval()
            step.why_not = decision.reason
        elif not decision.allowed:
            step.risk_level = decision.risk_level
            step.block(decision.reason)
        else:
            step.risk_level = decision.risk_level
        return step

    def _base_step(
        self,
        *,
        action_type: ActionType,
        why_this: str,
        why_not: str,
    ) -> ActionStep:
        rule = ACTION_POLICY_RULES[action_type]
        return ActionStep(
            action_type=action_type,
            risk_level=rule.risk_level,
            requires_approval=rule.requires_confirmation,
            why_this=why_this,
            why_not=why_not,
        )

    def _confidence_for(self, work_item: WorkItem, inputs: PlanningInput) -> str:
        if not inputs.evidence_sufficient:
            return "low"
        if inputs.missing_fields:
            return "medium"
        if work_item.work_type is not None or work_item.linked_document_ids:
            return "high"
        return "medium"
