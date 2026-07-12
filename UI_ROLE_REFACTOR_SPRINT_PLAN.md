# UI Role Refactor Sprint Plan

Status: UI-R1 and UI-R2 implemented; UI-R3 through UI-R6 pending.

Source inputs:

- `outputs/invoice-review-low-fidelity-redesign.pptx`
- Existing frontend screenshots from `outputs/ui-audit-screenshots/`
- Current gap: uploader and reviewer still share too much navigation and language.

## Verdict

The current UI is simpler than the old technical UI, but it is not yet demo-safe for ordinary users because the role model is blurry.

The next frontend work should not be more small cosmetic sprints. It should be one focused role-based refactor split into clear implementation checkpoints.

## Product Goal

Make the app understandable to a non-technical invoice user in 1-2 minutes:

1. Upload an invoice.
2. See where it went.
3. Let a reviewer decide.
4. See the result and history.

Technical concepts stay available only when they support trust or debugging. They must not appear in the primary demo path.

## Role Model

### Uploader

Main question:

> Did my invoice upload correctly, and what is its status?

Primary navigation:

- Upload Invoice
- My Invoices
- History

Uploader must not see:

- Approvals inbox
- Approve / reject buttons
- Review decision language
- Work queue language
- Technical evidence or execution language

### Reviewer

Main question:

> Which invoices need my decision?

Primary navigation:

- Approvals
- Invoices
- History

Reviewer must not see:

- Upload as a primary navigation item
- Intake wording
- Upload wizard as the default flow

Reviewer may still access invoice documents for context, but their job starts from approval decisions.

## Sprint UI-R1 - Role Navigation And Landing

Implementation status: completed.

Goal:
Make uploader and reviewer feel like different business users, not the same app with different labels.

Scope:

- Remove `Upload` from reviewer primary navigation.
- Make reviewer default landing page `Approvals`.
- Rename uploader `Invoices` to `My Invoices`.
- Keep role switch only as demo control.
- Make topbar role copy consistent with the selected role.
- Ensure route changes do not leave a reviewer on uploader-only screens.

Acceptance criteria:

- Uploader sidebar shows only `Upload Invoice`, `My Invoices`, `History`.
- Reviewer sidebar shows only `Approvals`, `Invoices`, `History`.
- Switching to reviewer lands on `Approvals`.
- Switching to uploader lands on `Upload Invoice`.

Risk:

- Existing frontend state may still allow stale screens after role switching. Fix by normalizing screen state on role change.

## Sprint UI-R2 - Uploader Status Experience

Implementation status: completed.

Goal:
Make uploader flow feel reliable after upload.

Scope:

- Replace uploader `Open review` button with `View status`.
- Keep uploader invoice cards status-focused.
- Hide reviewer-only decision actions from uploader views.
- Make post-submit state say the invoice was sent to a reviewer.
- Ensure uploaded invoices appear in `My Invoices` after submit or refresh.

Acceptance criteria:

- After sending an invoice for review, uploader can find it in `My Invoices`.
- Uploader never sees approve, reject, approval gate, or decision inbox wording.
- Empty states explain what happened and what to do next.

Risk:

- Backend status names may not map cleanly to business status. Add frontend display mapping without changing backend models.

## Sprint UI-R3 - Reviewer Approvals Workspace

Goal:
Make reviewer screen look like the main work area, not a broken narrow side panel.

Scope:

- Redesign `Approvals` as full-width desktop layout.
- Replace confusing metrics with:
  - Waiting decision
  - Needs correction
  - Completed
- Use a clear invoice table/list with vendor, invoice number, amount, status, and primary action.
- Primary action should be `Review invoice`.
- Remove technical labels such as gate, policy, work item, proposed action, and controlled execution from the main reviewer path.

Acceptance criteria:

- Reviewer can identify pending decisions within 10 seconds.
- No huge blank desktop layout on reviewer pages.
- Approval metrics match business meaning.

Risk:

- Some old admin diagnostic components still exist in `App.tsx`. Do not delete backend capabilities; hide or isolate them from the main role path.

## Sprint UI-R4 - Invoice Review And Decision Copy

Goal:
Make the final reviewer decision obvious and non-technical.

Scope:

- Keep review detail focused on:
  - Invoice preview
  - Detected invoice details
  - Review confidence in plain language
  - Decision buttons
- Decision options:
  - Approve invoice
  - Reject
  - Ask for correction
- Keep technical evidence as collapsed trust detail only if needed.
- Remove remaining labels like raw evidence, policy gate, action step, execution, schema, and trace from the main detail view.

Acceptance criteria:

- Reviewer can approve/reject without understanding the workflow engine.
- Approval does not feel like it happened automatically without context.
- Trust details are available but not visually dominant.

Risk:

- Too much hidden evidence can reduce trust for technical demos. Keep a small "Why this looks correct" area, but avoid raw tables.

## Sprint UI-R5 - Role-Specific History

Goal:
Make history read like a receipt, not a system log.

Scope:

- Uploader history copy:
  - Uploaded
  - Read by system
  - Sent for review
  - Approved / Rejected / Needs correction
- Reviewer history copy:
  - Review opened
  - Details checked
  - Approved / Rejected / Asked for correction
- Keep timestamps and actor names.
- Hide raw event names from the primary history UI.

Acceptance criteria:

- A non-technical user can understand what happened without asking what a workflow event means.
- History supports auditability without exposing internal implementation terms.

Risk:

- Existing events may be backend-native. Use a display mapping layer first.

## Sprint UI-R6 - Screenshot QA And Demo Readiness

Goal:
Prove the refactor visually, not just through code.

Scope:

- Capture screenshots for:
  - Uploader Upload Invoice
  - Uploader My Invoices
  - Uploader History
  - Reviewer Approvals
  - Reviewer Invoices
  - Reviewer History
  - Reviewer invoice decision detail
- Check desktop layout and mobile responsiveness.
- Run frontend tests and build.
- Update README demo path if needed.

Acceptance criteria:

- Screenshot audit has no role leakage.
- No primary screen has confusing technical language.
- Frontend tests/build pass.

Risk:

- Playwright/browser checks can be flaky. If automated screenshot flow fails, do manual browser screenshots and still record findings.

## Backend Audit Gate

Backend audit should happen after UI-R1 through UI-R6.

Reason:

The current biggest risk is not backend capability. It is that the app is hard to explain and the roles are confusing. Backend audit is still necessary, but auditing it before the role UI is fixed would optimize the wrong layer first.

Backend audit should check:

- Upload-to-review lifecycle correctness.
- Approval source of truth.
- Status transitions.
- Permission/role enforcement.
- Audit trail consistency.
- Error handling and recovery paths.

## Recommended Implementation Order

1. UI-R1 - Role Navigation And Landing
2. Commit and push
3. UI-R2 - Uploader Status Experience
4. Commit and push
5. UI-R3 - Reviewer Approvals Workspace
6. Commit and push
7. UI-R4 - Invoice Review And Decision Copy
8. Commit and push
9. UI-R5 - Role-Specific History
10. Commit and push
11. UI-R6 - Screenshot QA And Demo Readiness
12. Commit and push
13. Backend audit sprint

## Definition Of Done

The refactor is done only when all of these are true:

- A first-time user can explain the app as: upload invoice, check status, reviewer decides, history records it.
- Uploader and reviewer have different primary navigation.
- No role sees actions that do not belong to their job.
- Technical terms are hidden from the primary path.
- Screenshots prove the UI matches the intended role model.
- Tests/build pass.
