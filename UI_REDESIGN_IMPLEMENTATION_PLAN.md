# UI Redesign Implementation Plan

Status: approved for implementation after low-fidelity review.

Source artifact:

- `outputs/invoice-review-low-fidelity-redesign.pptx`

## Verdict

The old user-facing UI should not be preserved as the main experience. It exposes too much engineering vocabulary and makes ordinary invoice work feel like operating an internal workflow engine.

The correct direction is a main UI rebuilt around the business flow:

```text
Upload -> Invoices -> Review -> Decide -> History
```

Technical features stay in the product, but they move out of the primary path. Agent traces, raw evidence, provider health, schemas, and worker diagnostics are admin/developer diagnostics, not the default demo story.

## Product Rule

Every primary screen must answer one plain-language question:

- Upload: "How do I add an invoice?"
- Invoices: "Where is my invoice and what state is it in?"
- Review: "What did the system read, and is it correct?"
- Decide: "Should this invoice be approved, rejected, or sent back?"
- History: "What happened to this invoice?"

If a feature does not support one of those questions, it must be hidden from the main UI.

## Sprint UX-1 - App Shell And Navigation

Goal:
Replace the old technical sitemap with the approved business navigation.

Scope:

- Main navigation becomes `Upload`, `Invoices`, `Approvals`, `History`.
- Default reviewer landing becomes `Invoices` or `Approvals`, not a technical work queue.
- Rename visible copy away from `Review Queue`, `Work Queue`, `Next Steps`, `Record`, `Workflow`, `AgentOps`, `Schema`, and `Provider Health`.
- Keep role switch for demo only: `Uploader` and `Reviewer`.
- Hide diagnostic pages from the primary sidebar.

Acceptance criteria:

- A non-technical user can identify where to upload, where to find invoices, and where approvals live within 10 seconds.
- The primary sidebar has no engineering vocabulary.
- Existing backend APIs remain unchanged.

## Sprint UX-2 - Upload And Invoice List

Goal:
Make document intake and invoice discovery feel reliable.

Scope:

- Make upload completion lead to a visible invoice list state.
- Ensure uploaded invoices appear under `Invoices`, not only a separate document library.
- Replace confusing empty states with direct business copy.
- Use statuses: `Reading invoice`, `Needs review`, `Waiting approval`, `Approved`, `Rejected`, `Needs correction`.
- Add search/filter copy that matches ordinary invoice work.

Acceptance criteria:

- After upload, the user can see the invoice they just submitted.
- Empty states explain what to do next.
- Status labels do not expose backend state names.

## Sprint UX-3 - Review And Decision Flow

Goal:
Collapse the old multi-tab detail page into one understandable review path.

Scope:

- Review screen shows PDF preview and invoice fields side by side.
- Decision screen offers only three business decisions: approve, reject, ask for correction.
- Remove the old 4-option "what should happen next" picker from the main flow.
- Remove or hide old tabs that do not help ordinary review: `Next Steps`, `Record`, raw evidence views, and agent trace views.
- Keep auditability as short source snippets and human-readable history.

Acceptance criteria:

- The user can make a decision without understanding plans, gates, schemas, or evidence models.
- Approving an invoice does not surprise the user by skipping required review context.
- Technical records remain reachable only through diagnostics.

## Sprint UX-4 - History, Diagnostics Hiding, And Demo QA

Goal:
Make the app demo-safe end to end.

Scope:

- Build simple invoice history as a receipt-style timeline.
- Move technical screens behind a clearly separated admin/developer route or hide them from navigation.
- Run full frontend tests.
- Do manual demo QA across uploader and reviewer roles.
- Update README/demo notes if the main UI flow changes.

Acceptance criteria:

- Demo path can be explained in 1-2 minutes.
- No primary screen uses engineering-first language.
- Tests and build pass.

## Non-Goals

- Do not redesign backend data models in this UI sprint.
- Do not delete backend audit, evidence, trace, provider, or policy capabilities.
- Do not optimize the visual brand before the flow is stable.
- Do not keep old UI screens just because they already exist.

## Implementation Order

1. Implement Sprint UX-1.
2. Commit and push.
3. Implement Sprint UX-2.
4. Commit and push.
5. Implement Sprint UX-3.
6. Commit and push.
7. Implement Sprint UX-4.
8. Commit and push.
