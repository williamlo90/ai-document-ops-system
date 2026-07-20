# Review Queue Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-review-queue.png](../assets/ui-reference/modern-operations-review-queue.png)

## Purpose

Review Queue is a decision workstation. Motion must connect the selected table row with the
right-side invoice workspace, preserve reviewer focus, and provide clear feedback for decisions.

## Shared Motion System

### Principles And Timing

Animate only hierarchy, feedback, state transitions, and attention. Do not use bouncing,
parallax, large flying surfaces, blinking risk dots, or looping chart-like decoration.

| Interaction | Duration |
| --- | --- |
| Fast micro interaction | `120-160ms` |
| Standard transition | `180-240ms` |
| Panel or drawer | `260-320ms` |
| Initial section entrance | `360-500ms` |

Easing:

- Enter: `cubic-bezier(0.2, 0.8, 0.2, 1)`
- Exit: `cubic-bezier(0.4, 0, 1, 1)`
- Hover: `ease-out`
- Panel: `cubic-bezier(0.16, 1, 0.3, 1)`

### Visual Tokens

- Teal: `#0F8B94`; hover: `#0C7480`; soft: `#E8F7F8`
- Blue: `#2563EB`; soft: `#EAF2FF`
- Red: `#EF4444`; soft: `#FEECEC`
- Orange: `#F59E0B`; soft: `#FFF4DF`
- Green: `#10B981`; soft: `#EAFBF4`
- Page: `#F8FAFC`; surface: `#FFFFFF`
- Border: `#E6EDF3`; muted border: `#EEF2F6`
- Primary text: `#0F172A`; secondary: `#475569`; tertiary: `#64748B`
- Input, button, and card radius: `6-8px`; pill radius: `999px`

Shadows:

- Surface: `0 1px 2px rgba(15, 23, 42, 0.04)`
- Hover: `0 8px 24px rgba(15, 23, 42, 0.08)`
- Floating: `0 12px 32px rgba(15, 23, 42, 0.12)`

### Common Feedback

- Button hover: darken by `6-8%`, `140ms`; press: `scale(0.985)`, `90ms`.
- Table hover: `#FAFCFE`, `120ms`.
- Tooltip: opacity and `translateY(4px -> 0)`, `140ms`.
- Focus ring: `0 0 0 4px rgba(15, 139, 148, 0.12)`.
- Keep sidebar, page title, pagination, avatars, and top navigation stable.

### Reduced Motion

Under `prefers-reduced-motion: reduce`, replace row-to-panel movement, drawer slides, stagger,
preview refresh motion, and toast slides with a `100ms` fade and no translation.

## Page Structure

The reference contains:

1. Page header
2. KPI strip
3. Search and filters
4. Queue table
5. Right-side detail workspace
6. Extracted data and evidence
7. Invoice preview
8. AI recommendation
9. Reviewer actions

## Header And KPI Strip

Fade the title over `180ms`. KPI items enter with a `50ms` stagger and only subtle vertical
movement. Avoid dramatic count-up behavior.

KPI tooltips may explain comparison to yesterday, team baseline, peak hours, or SLA target. For
`6m Avg review time`, show team median, today's best time, and the under-eight-minute target.

## Search And Filters

Search focus changes the border from `#CBD5E1` to teal and adds the shared focus ring over
`140ms`.

Dropdowns move from `translateY(8px)` to zero while fading in over `180ms`. Active filters use
background `#E8F7F8`, text `#0C7480`, and border `#BDE7EA`. A dropdown caret rotates `180deg`
while open.

## Queue Row Selection

When a row is selected:

1. Update the radio control immediately.
2. Transition the row to background `#F4FBFC`, outline `1px solid #7ED3D9`, and a `3px` teal
   left accent.
3. Keep the right panel mounted.
4. Swap its content with a short crossfade instead of closing and reopening the panel.

Panel content swap:

- old content: opacity `1 -> 0`, `translateY(0 -> 6px)`
- new content: opacity `0 -> 1`, `translateY(6px -> 0)`
- total duration: `220ms`

An ordinary row hover uses `#FAFCFE`. A selected row only brightens slightly on hover.

## Confidence And Risk

Confidence tooltip:

- extraction confidence
- rule validation strength
- recommendation confidence

High-risk tooltip:

- `This invoice may block approval`
- critical-field count
- due status

Badge hover only increases saturation slightly over `100ms`; it must not pulse or blink.

## Right-Side Workspace

On first open, the workspace enters from `translateX(20px)` with opacity over `280ms`. It stays
mounted while the reviewer moves between rows.

When the selected invoice changes:

- header crossfade: `120ms`
- extracted field rows: `40ms` stagger
- preview refresh: opacity change over `180ms`; use a temporary blur only while the next PDF page
  is actually loading

Do not slide the entire workspace out and back in between invoices.

The status control strengthens its border on hover and rotates its chevron when open. High-risk
uses background `#FEECEC`, text `#DC2626`, and border `#F5C2C7`.

## Extracted Data

Field rows use background `#FAFCFE` on hover. A problematic value remains visibly red and gains
a slightly stronger row highlight.

For `PO number - Missing`, a tooltip may show:

- expected based on vendor policy
- no PO field found in OCR output
- confidence value

The confidence label tooltip explains that the result combines invoice reading and validation
and includes the last evaluated time. Avoid exposing raw prompts or model internals.

## AI Finding And Evidence

The AI finding enters with a `180ms` fade-up. On hover, strengthen its border and scale the issue
icon to `1.05` over `140ms`.

Evidence is a lightweight disclosure:

- summary remains visible by default
- expanded height transitions over `220ms`
- new lines fade over `120ms`
- chevron rotates `180deg`

Expanded content may show that a field was not found, the relevant vendor rule, historical PO
requirements, and confidence. Keep raw JSON and technical logs outside this page.

## Invoice Preview

Fade the preview in over `220ms`; reveal its zoom controls after an `80ms` delay. On preview
hover, strengthen the border and show a small surface shadow. Zoom controls use a soft teal hover
background and icon scale `1.05`.

Optional cross-highlighting: hovering a problematic extracted field briefly highlights the
related or expected area in the preview. Use soft red `#FEECEC`, red border `#EF4444`, and one
short opacity pulse. Do not loop the pulse.

## AI Recommendation

Fade the recommendation in over `220ms` with a small, non-looping border emphasis. On hover,
change its border from `#F4C7C3` to `#EAA49E`; avoid glow effects.

The confidence tooltip can explain the recommendation confidence and the business inputs used:
vendor policy, extracted result, and exception rules. It must not imply that AI has final
approval authority.

## Reviewer Actions

- Approve: soft-green hover with a `1px` check-icon rise.
- Request correction: red changes from `#EF4444` to `#DC2626` and gains
  `0 8px 20px rgba(239, 68, 68, 0.18)`.
- Escalate: strengthen the border and shift its arrow slightly.
- All buttons use `scale(0.985)` for `90ms` on press.

After success, show a top-right toast entering over `220ms` and dismissing after `4s`:

- Approve: `Invoice approved`, with an Undo action only if the backend can safely reverse it.
- Request correction: `Correction requested`; subtext may state the required correction. Do not
  claim it was sent externally unless an integration confirms delivery.
- Escalate: `Invoice escalated`; include the destination or owner only when known.

Disable the decision controls while the request is pending. Prevent double submission. On
failure, preserve the reviewer's note and show a retryable inline error.

## Loading State

Use skeletons for the KPI strip, queue rows, right-panel header, extracted field rows, PDF
placeholder, and recommendation area. Base: `#F1F5F9`; shimmer: `#F8FAFC`; duration:
`1.4s linear infinite`. Keep shimmer low contrast and disable it under reduced motion.

## Responsive Behavior

- `>=1440px`: retain the full queue plus inspector layout.
- `1280-1439px`: reduce table density and right-panel padding.
- `1024-1279px`: narrow the table and make the inspector a wider overlay when selected.
- `<1024px`: replace the fixed inspector with a full-height right drawer. Tables become compact
  selectable lists.
- Mobile uses tap-triggered popovers or bottom sheets instead of hover tooltips.

## Priority

Required: filter focus, dropdown transition, selected-row state, in-place panel content swap,
field hover, evidence disclosure, preview loading, decision feedback, submission lock, error
recovery, skeleton loading, and reduced-motion support.

Optional: cross-highlighting between extracted fields and PDF regions, detailed confidence
tooltips, and Undo when reversal is supported safely.

