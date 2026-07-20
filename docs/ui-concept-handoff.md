# Modern Operations UI Concept Handoff

Status: Working concepts pending external critique and final approval.

The four current visual references establish the product shell:

- [Overview reference](assets/ui-reference/modern-operations-overview.png)
- [Invoices reference](assets/ui-reference/modern-operations-invoices.png)
- [Review Queue reference](assets/ui-reference/modern-operations-review-queue.png)
- [Invoice Review Workspace reference](assets/ui-reference/modern-operations-invoice-review-workspace.png)

The saved Invoices and Invoice Review Workspace references supersede their original concepts
below. Those concepts remain available only as iteration history.

The following concepts extend that direction across the rest of the product. They are not final
implementation references yet:

| Page | Product purpose | Concept |
| --- | --- | --- |
| Invoices | Find and inspect every invoice without making a reviewer decision. | [invoices.png](assets/ui-concepts/modern-operations-v1/invoices.png) |
| Invoice Review Workspace | Compare the PDF, extracted data, blockers, and human decision in one focused workspace. | [invoice-review-workspace.png](assets/ui-concepts/modern-operations-v1/invoice-review-workspace.png) |
| Exceptions | Investigate and resolve processing blockers across invoices. | [exceptions.png](assets/ui-concepts/modern-operations-v1/exceptions.png) |
| Exports | Select approved invoices, verify eligibility, and track controlled export runs. | [exports.png](assets/ui-concepts/modern-operations-v1/exports.png) |
| Evaluation | Explain synthetic test quality, limitations, failures, coverage, and estimated cost. | [evaluation.png](assets/ui-concepts/modern-operations-v1/evaluation.png) |
| System | Show service availability, processing activity, integrations, and actionable failures in plain language. | [system.png](assets/ui-concepts/modern-operations-v1/system.png) |
| Settings | Configure organization defaults, review rules, notifications, access, and data policy. | [settings.png](assets/ui-concepts/modern-operations-v1/settings.png) |

## Prompt Set

Every concept used the saved Overview and Review Queue images as strict references for the
application shell, typography, spacing, palette, iconography, controls, and information density.
The page-specific briefs were:

1. **Invoices:** a searchable invoice library with status filters, a dominant table, and an
   inspection-only details drawer.
2. **Invoice Review Workspace:** a three-column workspace with a large PDF viewer, editable
   extracted data and validation checks, and explicit human decision controls.
3. **Exceptions:** a risk-prioritized issue table with a plain-language exception inspector and
   no final approval controls.
4. **Exports:** an approved-invoice selection table, eligibility checklist, export configuration,
   and recent run status.
5. **Evaluation:** a clearly labeled synthetic-test summary with performance trends, field and
   scenario coverage, known limits, recent runs, and estimated cost.
6. **System:** an administrator overview of core processing, service status, connected services,
   recent jobs, and actionable degradation without exposing engineering internals.
7. **Settings:** business-facing organization, review, schedule, notification, access, and data
   settings using standard form controls.

## Review Instructions

Review each page for business purpose, navigation structure, task completion, information
hierarchy, and consistency before discussing colors or visual polish. Proposed revisions must:

- preserve the existing approval and role boundaries
- keep one clear business purpose per page
- avoid duplicating Invoices, Review Queue, and Exceptions
- keep technical diagnostics out of primary finance work
- use real application data when implemented; concept metrics are layout examples only
- retain desktop information density while defining a usable tablet and mobile adaptation

Return revised pages as individual PNG files with stable names. The revised images replace these
concepts as final references only after explicit approval.
