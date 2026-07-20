# Client-Deliverable UI Reference

Status: Design approval in progress.

These images are the visual source of truth for the next frontend conversion. The current
frontend remains functional, but it is not the final presentation target.

## Approved Direction

- Product style: modern finance-operations SaaS
- Overview reference: [modern-operations-overview.png](assets/ui-reference/modern-operations-overview.png)
- Invoices reference: [modern-operations-invoices.png](assets/ui-reference/modern-operations-invoices.png)
- Review Queue reference: [modern-operations-review-queue.png](assets/ui-reference/modern-operations-review-queue.png)
- Invoice Review Workspace reference: [modern-operations-invoice-review-workspace.png](assets/ui-reference/modern-operations-invoice-review-workspace.png)

## Working Concept Batch

Seven original desktop page concepts and their handoff instructions are available in
[`ui-concept-handoff.md`](ui-concept-handoff.md). These files extend the approved direction but
remain drafts until revised images are explicitly accepted as final references. The original
Invoices concept is superseded by the saved Invoices redesign reference above.

## Motion Specifications

The first three page-level motion and interaction handoffs are stored separately and mapped to
their matching visual references:

- [Overview motion specification](ui-motion-specs/overview-motion-spec.md)
- [Invoices motion specification](ui-motion-specs/invoices-motion-spec.md)
- [Review Queue motion specification](ui-motion-specs/review-queue-motion-spec.md)
- [Invoice Review Workspace motion specification](ui-motion-specs/invoice-review-workspace-motion-spec.md)

These documents describe intended behavior only. They do not indicate that motion has already
been implemented.

## Design Contract

- Use one persistent application shell with a left navigation rail and a compact top bar.
- Organize the product by business capability: Overview, Invoices, Review Queue, Exceptions,
  Exports, Evaluation, System, and Settings.
- Use white and light-neutral surfaces, dark navy text, teal primary actions, red for blocking
  risk, amber for attention, and blue for informational states.
- Make tables and work queues the dominant operational surfaces. Avoid decorative card grids.
- Keep the active invoice visible beside its extracted data, evidence, preview, and decision
  controls wherever space permits.
- Keep technical diagnostics behind Evaluation or System. Primary finance screens use plain
  business language.
- Preserve consistent spacing, iconography, status chips, filter controls, and action hierarchy
  across every page.
- Treat generated data, metrics, AI findings, and confidence values as layout examples only;
  implementation must use observed application data and must not invent claims.

## Approval Workflow

Create and review one page mockup at a time. A page is implemented only after it is explicitly
approved. Revisions remain in the mockup stage until the layout and business flow are accepted.

Planned sequence:

1. Overview
2. Invoices
3. Review Queue
4. Invoice Review Workspace
5. Exceptions
6. Exports
7. Evaluation
8. System
9. Settings
