# AI Document Operation System - Frontend Sprint Plan

Status: Frontend-specific execution plan. Use `blueprint.md` and `SPRINT_PLAN.md` as source-of-truth context.

Purpose: make the product immediately legible as an AI Document Operations System while preserving current behavior and local/mock defaults.

## Frontend Strategy

The frontend should be refactored before broad backend generalization, but only at the presentation layer.

Correct order:

```text
baseline inventory
-> product identity and labels
-> information architecture
-> document queue/workspace clarity
-> exception and approval UX
-> technical evidence UX
-> visual polish and portfolio screenshots
```

Do not invent backend capabilities. If a control depends on behavior that is not implemented, disable it with truthful copy or defer it.

## Frontend Sprint 0 - UI Inventory And Baseline

### Goal

Map all user-facing UI surfaces that still say invoice/backoffice/autonomous and classify what should change.

### Work

- Inventory visible labels, sidebar items, page titles, buttons, tabs, empty states, notices, badges, and test expectations.
- Identify UI surfaces that are safe copy-only changes.
- Identify UI surfaces that depend on backend domain changes and must wait.
- Capture baseline screenshots if the app runs.

### Likely Files

- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/src/test/App.test.tsx`
- `frontend/e2e/*.spec.ts`
- `docs/pivot/KEEP_REFACTOR_REMOVE_REBUILD.md`
- `docs/pivot/BASELINE_VERIFICATION.md`

### Verification

- `cd frontend`
- `npm test`
- `npm run build`
- `npx playwright test` if available and environment-ready.

### Done

- UI inventory exists.
- Baseline test/screenshot status recorded.
- No UI behavior changes yet.

## Frontend Sprint 1 - Product Identity And Navigation

### Goal

Make the app read as AI Document Operation System on first impression.

### Work

- Rename product branding from autonomous/backoffice wording to AI Document Operation System.
- Reframe navigation around:
  - Document Intake
  - Document Queue
  - Exceptions
  - Approvals
  - Exports
  - Evidence
  - Settings
- Rename safe labels:
  - New Invoice -> New Document
  - My Submissions -> My Documents
  - All Invoices -> Document Library
  - Invoice Intake -> Document Intake
  - Invoice Review -> Document Review
- Add explicit `Invoice` document-type badge wherever current workflow is invoice-only.
- Remove or soften any broad autonomous claims.

### Constraints

- Do not rename backend routes.
- Do not claim support for non-invoice documents.
- Do not add external credentials.
- Keep current user flows working.

### Verification

- Frontend unit tests.
- Build.
- Playwright smoke for login, intake, library, reviewer inbox, work item detail if available.

### Done

- Recruiter can identify the product category in 60 seconds.
- Existing invoice flow still works.
- No visible enabled control claims unsupported generic document behavior.

## Frontend Sprint 2 - Document Queue First Screen

### Goal

Make the primary screen feel like an operations queue, not a generic admin console.

### Work

- Make Document Queue the central operational view.
- Improve table hierarchy around:
  - document name;
  - vendor;
  - amount;
  - document type;
  - status;
  - risk/attention reason;
  - owner;
  - updated time;
  - next action.
- Add or refine summary counts:
  - pending review;
  - exceptions;
  - awaiting approval;
  - export ready;
  - blocked.
- Make filters clear and compact.
- Keep density professional and enterprise-oriented.

### Constraints

- Use existing backend data only.
- Do not fabricate metrics.
- If a metric is derived from local fixtures, label it truthfully.

### Verification

- Component/unit tests where present.
- E2E smoke for table/filter path if present.
- Browser screenshot review.

### Done

- The first screen shows document operations value without reading docs.
- Table and summary states are coherent and non-decorative.

## Frontend Sprint 3 - Document Workspace And Evidence UX

### Goal

Make the document detail screen explain extraction, validation, evidence, proposed action, and activity clearly.

### Work

- Refactor workspace layout into clear regions:
  - document preview;
  - extracted fields;
  - validation issues;
  - line items for invoice type;
  - evidence/citations;
  - proposed action;
  - workflow activity.
- Make confidence, severity, and risk badges consistent.
- Keep invoice-specific detail inside invoice evidence panels.
- Make missing evidence or validation failures visually prominent.

### Constraints

- Do not invent extraction fields.
- Do not show fake citations.
- Do not imply non-invoice schemas are complete.

### Verification

- Frontend tests.
- Screenshot review at desktop and laptop widths.
- No text overlap or layout instability.

### Done

- Hiring manager can see where AI is used and where deterministic validation applies.
- Risk and evidence are more prominent than decorative AI labels.

## Frontend Sprint 4 - Exception And Approval UX

### Goal

Make human-in-the-loop workflow obvious and credible.

### Work

- Improve exception queue/detail presentation.
- Highlight exception types:
  - missing field;
  - total mismatch;
  - duplicate candidate;
  - vendor mismatch;
  - low confidence.
- Refine approval screen:
  - proposal/version;
  - evidence snapshot;
  - risk triggers;
  - decision reason;
  - approve/reject/needs-info.
- Ensure all risky actions look approval-gated.

### Constraints

- Approval authority remains backend/domain logic.
- Frontend controls are presentation only.
- Do not add unsupported approval states.

### Verification

- Existing approval/reviewer tests.
- E2E smoke for approve/reject paths if available.
- Accessibility check for forms and disabled states.

### Done

- User can tell what needs human review and why.
- Decision controls do not imply unsafe autonomy.

## Frontend Sprint 5 - Technical Evidence UX

### Goal

Make the technical evidence page useful for hiring managers without overwhelming operators.

### Work

- Reframe AgentOps/Evaluation labels around document operations.
- Show evaluation cases, metrics, known failures, and limitations.
- Link metrics to underlying cases where available.
- Keep technical evidence secondary to operations workflow.

### Constraints

- No production telemetry claim.
- No real provider claim unless verified.
- No fake model quality metrics.

### Verification

- Frontend tests.
- Browser screenshot review.

### Done

- Hiring manager can inspect reliability proof in 10 minutes.
- Known limitations remain visible.

## Frontend Sprint 6 - Visual Polish And Portfolio Capture

### Goal

Make the UI portfolio-ready after behavior and wording are correct.

### Work

- Tighten spacing, typography, badges, tables, panels, focus states, loading/empty/error states.
- Remove visual noise.
- Capture screenshots:
  - Document Queue;
  - Document Workspace;
  - Exception Review;
  - Approval Review;
  - Technical Evidence.
- Update demo script references if needed.

### Constraints

- No new backend behavior.
- No broad redesign that breaks tested flows.
- No marketing landing page.

### Verification

- Frontend tests.
- Build.
- Screenshot review across desktop/laptop.

### Done

- UI feels like a serious enterprise operations product.
- Screenshots are usable for README/portfolio.

## Frontend Execution Rule

Run one frontend sprint at a time. Do not combine Sprint 1 and Sprint 2 unless explicitly approved.

