# Invoice Review Workspace Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-invoice-review-workspace.png](../assets/ui-reference/modern-operations-invoice-review-workspace.png)

## Purpose

This page is a verification and decision workspace, not a generic invoice detail page. The
reviewer's mental flow is:

```text
Inspect the source document
-> verify extracted data
-> understand evidence and blockers
-> make a human decision
-> record the audit consequence
```

The document is the source of truth. AI provides a recommendation and supporting evidence but
does not make the final decision. Every edit and decision must be auditable. Motion exists only
to clarify relationships, state changes, and feedback.

## 1. Layout And Hierarchy

The desktop reference uses three functional columns:

```text
Invoice preview   approximately 38%
Extracted data    approximately 29%
Decision panel    approximately 33%
```

Use responsive grid constraints rather than hard-coded percentages:

```css
grid-template-columns:
  minmax(420px, 1.2fr)
  minmax(320px, 0.9fr)
  minmax(340px, 1fr);
gap: 16px;
```

Additional layout rules:

- main content padding: `24px`
- page background: `#F7F9FC`
- surface background: `#FFFFFF`
- surface border: `1px solid #E4EAF0`
- surface radius: `8px`
- minimum workspace height: `calc(100vh - 250px)`

The Decision panel remains reachable while long content scrolls:

```css
position: sticky;
top: 84px;
max-height: calc(100vh - 108px);
overflow-y: auto;
```

Invoice Preview and Extracted Data may scroll independently. Avoid nested scroll areas when the
content fits naturally in the viewport.

## 2. Global Motion Tokens

```css
--motion-fast: 120ms;
--motion-standard: 180ms;
--motion-panel: 260ms;
--motion-page: 320ms;

--ease-enter: cubic-bezier(0.2, 0.8, 0.2, 1);
--ease-panel: cubic-bezier(0.16, 1, 0.3, 1);
--ease-exit: cubic-bezier(0.4, 0, 1, 1);
```

Usage:

- hover and focus: `120-150ms`
- tooltip and dropdown: `160-180ms`
- accordion: `200-240ms`
- modal and drawer: `240-280ms`
- page entrance: `280-320ms`

Do not use strong spring motion, repeated blocker animation, looping glow, unnecessary rotating
icons, floating surfaces, or bouncing buttons.

## 3. Page Entrance

Run the entrance sequence once when this route is first opened:

1. Header and metadata: `0ms`
2. Progress stepper: `50ms` delay
3. Invoice Preview: `100ms` delay
4. Extracted Data: `150ms` delay
5. Decision panel: `200ms` delay

Each section uses:

```css
opacity: 0 -> 1;
transform: translateY(10px) -> translateY(0);
transition-duration: 260ms;
transition-timing-function: var(--ease-enter);
```

Do not replay entrance motion after field edits, revalidation, or decision-state changes.

## 4. Invoice Header

The header contains the breadcrumb, `Review invoice`, status, vendor, dates, amount, and
`Back to queue`.

Breadcrumb hover changes blue from `#2563EB` to `#1D4ED8` and adds an underline over `120ms`.

The status badge remains still. Its tooltip appears after `250ms` and enters over `140ms`:

```text
Needs correction

Invoice cannot proceed until one blocking issue is resolved.
```

Tooltip width: `220px`; background: `#0F172A`; text: white; radius: `8px`; padding:
`10px 12px`.

`Back to queue` uses background `#F8FAFC`, border `#CBD5E1`, and a `2px` left-arrow shift on
hover over `140ms`.

If extracted values have unsaved changes, show a confirmation dialog before leaving:

```text
Leave without saving?

You have unsaved changes to the extracted invoice data.
```

## 5. Progress Stepper

Stages are `Read -> Validate -> Decision`.

Completed state:

- circle background `#E8F7F8`
- border and icon `#0F8B94`

Active state:

- background `#EFF6FF`
- border and text `#2563EB`
- ring `0 0 0 4px rgba(37, 99, 235, 0.10)`

When a stage completes, extend the progress line, replace the number with a check, and update
supporting text over a total of `300ms`. Never pulse the active stage continuously.

Tooltip copy:

- Read: `Invoice extracted. OCR and document parsing completed at 9:38 AM.`
- Validate: `Data validated. 12 checks completed. One blocking issue was found.`

Use observed timestamps and counts in implementation.

## 6. Invoice Preview Toolbar

Controls: previous page, page number, next page, zoom out, zoom percentage, zoom in, fullscreen,
and open in a new view.

- control height: `34px`
- icon button: `34px` square
- gap: `8px`
- radius: `8px`

Hover:

```css
background: #F1F5F9;
color: #0F172A;
transition: 120ms ease-out;
```

Press: `scale(0.96)` over `80ms`.

Zoom rules:

- minimum `50%`
- maximum `200%`
- increment `10%`
- default `100%`
- transform origin `center top`
- scale transition `160ms`
- percentage crossfade `100ms`

Above `100%`, use `grab` and `grabbing` cursors without strong momentum.

Fullscreen uses a `160ms` overlay fade and `scale(0.98 -> 1)` over `240ms`. Keep its toolbar
sticky, close on `Esc`, trap modal focus, and return focus to the fullscreen button on close.

## 7. Field-To-Document Cross-Highlighting

Hovering or focusing an extracted field highlights its matching source region:

- Invoice number
- Vendor
- Invoice date
- Due date
- Tax
- Total amount

Normal highlight:

```css
background: rgba(37, 99, 235, 0.10);
border: 1px solid rgba(37, 99, 235, 0.55);
border-radius: 4px;
opacity: 0 -> 1;
transform: scale(0.98) -> scale(1);
transition-duration: 150ms;
```

Fade out over `120ms` after pointer or keyboard focus leaves the field.

For a missing PO number, show a red dashed highlight only when the PDF or extraction result
provides a reliable expected or labelled region:

```css
background: rgba(239, 68, 68, 0.10);
border: 1px dashed rgba(239, 68, 68, 0.75);
```

Label: `PO number not detected`.

Do not fabricate coordinates. When no reliable region exists, keep the document unmarked and
show the missing-field explanation in Extracted Data and Evidence. A known highlight may pulse
once on first appearance but must never blink.

## 8. Extracted Data

Header: `Extracted data` with `92% extraction confidence` in the reference. Runtime values must
come from stored extraction results.

Confidence chip:

- background `#E8F7F8`
- text `#0F7A83`
- pill radius `999px`
- type `11px`
- height `24px`

Its tooltip may show overall extraction, OCR, field mapping, and document classification
confidence only when each value is actually available.

Field rows:

- minimum height `42px`
- label `12px`, `#475569`
- value `13px`, weight `500`
- divider `#EEF2F6`
- edit icon `16px`, default opacity `0.45`

On row hover use `#FAFCFE` and full edit-icon opacity over `120ms`.

For a missing PO number, use text `#DC2626`, icon `#EF4444`, and hover background `#FFF8F8`.
Tooltip copy:

```text
PO number not detected

The vendor policy requires a PO number.
OCR did not find a PO label or reference.
This issue blocks approval.

Confidence: 92%
```

Use the actual confidence value or omit that line.

## 9. Inline Editing

When the edit control is activated:

1. Replace the value with an input.
2. Reveal Save and Cancel controls.
3. Keep the document highlight visible when a reliable region exists.
4. Move keyboard focus into the input.

Input height: `34px`; border `#0F8B94`; radius `8px`; focus ring
`0 0 0 3px rgba(15, 139, 148, 0.12)`.

Value fades out over `70ms`; input fades in over `110ms`.

Keyboard behavior:

- `Enter`: save
- `Esc`: cancel
- `Tab`: move to the next control

After a successful save, use background `#F0FDF4` and a check for `700ms`, then return to white
over `500ms`.

When validation must rerun, show `Revalidating...` and a `14px` spinner only on the affected row.
After completion show `Validation updated`. Do not block or reload the whole page.

## 10. Evidence And Checks

The reference groups the blocker and supporting observations:

```text
Vendor policy requires PO number     Blocker
OCR did not detect PO field
Approval blocked until PO is provided
Severity                             Blocker
```

Evidence rows are `34-38px` high with `16px` icons, `12px` text, and soft-red blocker badges.
Hover background: `#FAFCFE`, `120ms`.

Clicking a row opens an accordion with rule source, expected field, observed result, and impact.
Height transitions over `220ms`, content fades over `140ms`, and the chevron rotates `180deg`.
Keep only one row open at a time.

## 11. Line Items

Line items use only row hover `#FAFCFE`, right-aligned amounts, a stronger Total row, and a
tooltip for truncated values. When reliable coordinates exist, hovering a line item may
highlight the same row in the document using soft blue.

## 12. Decision Panel

The Decision panel is visually important but must remain calm:

```css
border: 1px solid #F6CACA;
background: #FFFCFC;
```

Do not apply red to the entire panel. Red is reserved for the correction recommendation,
blockers, and destructive or blocking feedback. Do not use a gradient.

## 13. AI Recommendation

The recommendation explains its reasoning:

```text
AI recommendation
92% confidence

Recommended action
Request correction

A valid PO number is required before approval.
Vendor policy requires a PO and OCR did not detect one.
```

Evidence summary:

```text
OCR evidence       Not detected
Policy rule        Matched
Blocker severity   High
```

On hover, strengthen the border and adjust the background subtly over `140ms`; do not lift or
glow the card.

`Why this recommendation?` expands reasoning over `220ms`, fades content over `140ms`, and
rotates its arrow `90deg`. It may explain vendor identity, threshold policy, invoice total,
missing extraction, and approval impact. End with:

```text
This recommendation assists the reviewer and does not make the final decision.
```

## 14. Decision Note

The note is required for Request correction and Reject, and optional for Approve after all
blockers are resolved.

- minimum height `112px`
- radius `8px`
- padding `12px`
- border `#CBD5E1`
- type `13px`
- focus: teal border and `0 0 0 3px rgba(15, 139, 148, 0.12)`

Counter color is `#94A3B8`, orange above `850`, and red above `1000`. Prevent submission beyond
the supported limit.

For correction, offer but never insert automatically:

```text
Use suggested note

PO number is missing. Please provide a valid PO number so the invoice can proceed through
approval.
```

## 15. Decision Actions And Guardrails

Visual order:

1. Request correction
2. Approve
3. Reject

Request correction uses background `#EF4444`; hover `#DC2626`; shadow
`0 8px 20px rgba(239, 68, 68, 0.18)`. Disable it while the required note is empty and show:
`Add a decision note before requesting correction.`

Approve must remain disabled while a blocking validation issue exists. Its explanation is:

```text
Resolve the blocking PO number issue before approval.
```

Do not provide a UI-only override. A future override is allowed only if the backend introduces
an explicit authorization policy, required reason, immutable audit event, and tests for that
boundary.

Reject opens a confirmation dialog and requires a rejection reason:

```text
Reject invoice?

This permanently marks the invoice as rejected.
A rejection reason is required.
```

All buttons use `scale(1 -> 0.985)` over `90ms` when pressed.

## 16. Confirmation Modal

For Request correction:

```text
Request correction?

Invoice
INV-2025-04567

Issue
PO number missing

Decision note
"PO number is missing. Please provide..."

This action will be recorded in the audit log.
```

Modal width: `440px`; radius: `8px`; padding: `24px`; backdrop:
`rgba(15, 23, 42, 0.32)`.

Animate backdrop opacity, modal opacity, `scale(0.97 -> 1)`, and `translateY(8px -> 0)` over
`220ms`. Trap focus, close on `Esc`, and return focus to the invoking button.

## 17. Submit State

After confirmation:

- show a `16px` spinner
- use `Saving decision...`
- keep the modal open
- disable all modal actions
- prevent duplicate submission

On success, close the modal, update invoice status, and show a top-right toast:

```text
Correction requested

The invoice now requires a valid PO number before review can continue.
```

Actions: `View activity` and `Review next invoice`.

Toast position: top `84px`, right `24px`, width `340px`. Enter with opacity and
`translateX(20px -> 0)` over `220ms`.

Do not claim the request was delivered to a vendor unless an external integration confirms it.

## 18. Error State

On failure:

```text
Decision could not be saved

Your note has been preserved. Please try again.
```

Keep the note, keep the current invoice state, retain the modal, show `Try again`, and preserve
input locally for the current session.

Offline copy:

```text
You appear to be offline. Your decision has not been submitted.
```

## 19. Audit Consequence

The Audit card may list:

- reviewer identity
- timestamp
- decision note
- previous invoice state
- new invoice state
- AI recommendation version, when stored
- validation rule version, when stored

Use only a light border hover. `View audit details` may open a popover or accordion.

## 20. Keyboard Behavior

- `Tab` and `Shift + Tab`: move between controls
- `Enter`: select or save
- `Esc`: close modal, dropdown, or edit mode
- `+` and `-`: zoom while preview is focused
- `Ctrl/Cmd + Enter`: submit the currently selected decision when valid
- Arrow keys: navigate dropdowns and accordions

Visible focus ring:

```css
outline: none;
box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
```

Never remove keyboard focus styling without an equivalent replacement.

## 21. Loading State

Use stable skeletons per panel:

- Preview: toolbar, paper, and line blocks.
- Extracted Data: eight field rows, evidence, and line items.
- Decision: recommendation, textarea, and three actions.

Skeleton base: `#EEF2F6`; highlight: `#F8FAFC`; duration: `1.4s`. Keep shimmer subtle and
disable it under reduced motion.

## 22. Responsive Behavior

At `1280-1440px`, retain three columns with Preview around `36-40%`, Extracted Data around
`28-31%`, and Decision at least `320px`.

At `1024-1279px`, use two primary columns for Preview and Extracted Data. Open Decision as a
sticky right drawer from an `Open decision panel` action.

Below `1024px`, stack Preview and Extracted Data, open Decision in a full-height drawer, allow
horizontal toolbar scrolling when needed, and make line items horizontally scrollable.

## 23. Reduced Motion

Under `prefers-reduced-motion: reduce`, disable page stagger, zoom interpolation, highlight
pulse, progress animation, modal scaling, and drawer sliding. Replace them with a fade of at most
`100ms` and no translation.

## 24. Intentionally Static Elements

Keep sidebar, vendor metadata, invoice total, line-item header, audit text, breadcrumb divider,
separators, and the loaded status badge static.

Never add blinking blockers, repeated recommendation glow, rotating AI icons, continuous stepper
pulse, bouncing buttons, floating documents, or approval confetti. The final result must feel
like a calm, trustworthy enterprise verification workspace.

