# UI Plan - Plain Operator Experience With Technical Evidence

Status: active UX simplification plan.

## Goal

Make the app understandable for a non-technical operator while preserving enough technical evidence for engineers, reviewers, and portfolio evaluation.

Target outcome:

```text
The default UI explains what to do next in business language.
Technical AgentOps, scenario, dataset, policy, and trace evidence remains available, but it does not dominate the main workflow.
```

## Product Principle

The product is not a generic analytics dashboard. It is an operator console for document work.

The first screen should answer:

- What needs attention?
- What should I do next?
- What evidence supports the decision?
- What happens after I approve, reject, correct, or export?

Technical users can still inspect:

- policy gates
- AgentOps traces
- deterministic scenario checks
- dataset contracts
- API/runtime status

## Audience Modes

### Operator View

Default mode.

For users who need to process and review document work without understanding AgentOps internals.

Primary navigation:

- Work Queue
- Exceptions
- Approvals
- Documents
- Settings

Default language:

- "Needs review" instead of "awaiting_human"
- "Suggested next step" instead of "proposed action"
- "Approval needed" instead of "policy gate"
- "Document evidence" instead of "extraction confidence"
- "Reliability checks" instead of "evaluation cases"

### Technical Evidence View

Secondary mode.

For reviewers, engineers, and portfolio evaluation.

Keep available:

- System Reliability
- Reliability Checks
- Test Scenarios
- AgentOps trace links
- Policy and safety details
- Provider/runtime status

These areas should be reachable, but not required to understand the main document workflow.

## Sprint Plan

### UX Sprint 1 - Navigation And IA Simplification

Status: complete.

Goal:
Make the main navigation feel like a business workflow, not a technical sitemap.

Changes:

- Make Work Queue the default landing view.
- Group AgentOps, Reliability Checks, Test Scenarios, and runtime diagnostics under Technical Evidence.
- Keep Settings and Integrations separate from daily operator work.
- Review all page titles and nav labels for business readability.

Acceptance criteria:

- A new user can identify the main queue without reading documentation.
- Technical Evidence remains available to admin/reviewer roles.
- No backend API behavior changes.

### UX Sprint 2 - Work Item Detail Simplification

Status: complete.

Goal:
Make the detail page answer "what happened, what is next, and what should I decide?"

Changes:

- Promote status, priority, owner, next action, and approval requirement above technical tabs.
- Reduce visible tab count in the default operator path.
- Keep Plan, Governance, Activity, and Technical Evidence available as secondary details.
- Rename dense technical labels to business language.

Acceptance criteria:

- The top of the detail page shows status, next action, and required human decision.
- Approve/reject/correction choices are visible only where they are actionable.
- Technical trace links remain available.

### UX Sprint 3 - Evidence And Approval Guidance

Status: complete.

Goal:
Make the approval flow understandable without knowing the internal policy engine.

Changes:

- Show a concise evidence summary before approve/reject.
- Explain why approval is required in business terms.
- Keep source excerpts and validation findings visible.
- Clarify what rejection and correction do.

Acceptance criteria:

- Approval page explains the decision, supporting evidence, and risk reason.
- Users can distinguish reject, correction, and approve.
- The UI does not introduce unsupported approval states.

### UX Sprint 4 - Technical Evidence Rewording

Status: complete.

Goal:
Preserve rigor while making reliability pages less intimidating.

Changes:

- Rename "Evaluation Cases" to "Reliability Checks".
- Rename "Test Datasets" to "Test Scenarios".
- Rename "Reliability Evidence" to "System Reliability".
- Keep AgentOps details as expandable technical context.
- Keep deterministic/local limitation copy visible.

Acceptance criteria:

- Technical pages still expose scenario results, datasets, and run traces.
- Labels are understandable to a non-engineer.
- Evidence limitation language remains honest.

### UX Sprint 5 - Empty, Loading, And Error States

Status: complete.

Goal:
Make the app self-guiding when there is no data or an action fails.

Changes:

- Replace generic empty states with next-step guidance.
- Make upload/process/review errors actionable.
- Make missing evidence states tell the user what to check.

Acceptance criteria:

- Empty queue tells the user to upload or create a task.
- Missing evidence tells the user to compare with source document.
- API errors do not expose internal implementation details.

## Non-Goals

- Do not hide auditability.
- Do not remove AgentOps.
- Do not claim production SaaS readiness.
- Do not add fake workflows or unsupported document types just to make the UI look broader.
- Do not remove invoice compatibility routes.

## Definition Of Done

The UI simplification work is done when:

- Main operator workflow can be demoed without explaining AgentOps first.
- Technical reviewers can still inspect evidence, policies, traces, scenarios, and datasets.
- Frontend tests cover the simplified navigation and approval path.
- Production build passes.
- README/demo language matches the simplified workflow.
