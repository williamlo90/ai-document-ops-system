# Invoices Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-invoices.png](../assets/ui-reference/modern-operations-invoices.png)

## Purpose

Invoices is the master library for browsing, filtering, and quickly inspecting uploaded
invoices. Motion should be lighter than Review Queue and should prioritize scan speed.

## Shared Motion System

### Principles And Timing

Animate only hierarchy, feedback, and state changes. Avoid bouncing, parallax, long entrances,
blinking status indicators, strong shimmer, and movement on every card.

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
- Purple: `#8B5CF6`; soft: `#F3EDFF`
- Page: `#F8FAFC`; surface: `#FFFFFF`
- Border: `#E6EDF3`; muted border: `#EEF2F6`
- Primary text: `#0F172A`; secondary: `#475569`; tertiary: `#64748B`
- Input, button, and card radius: `6-8px`; pill radius: `999px`

Shadows:

- Surface: `0 1px 2px rgba(15, 23, 42, 0.04)`
- Hover: `0 8px 24px rgba(15, 23, 42, 0.08)`
- Floating: `0 12px 32px rgba(15, 23, 42, 0.12)`

### Common Feedback

- Card hover: `translateY(-2px)`, stronger border and shadow, `180ms`.
- Button hover: darken by `6-8%`; shift a directional icon by `2px`, `140ms`.
- Button press: `scale(0.985)`, `90ms`.
- Row hover: background `#FAFCFE`, `120ms`.
- Tooltip: opacity and `translateY(4px -> 0)`, `140ms`.
- Search focus ring: `0 0 0 4px rgba(15, 139, 148, 0.12)`.

### Reduced Motion

Under `prefers-reduced-motion: reduce`, disable stagger, number count-up, decorative movement,
active-pill travel, drawer slide, and preview cross-highlighting. Use a `100ms` fade and no
translation.

## Page Structure

The reference contains:

1. Header and Upload invoice action
2. Five summary KPI cards
3. AI insights strip
4. Search, tabs, filters, and sort
5. Invoice table
6. Right-side inspection panel
7. Validation summary
8. Invoice preview
9. Open invoice action

## Initial Load

- Title: fade over `180ms`.
- Upload button: fade over `220ms`.
- KPI cards: fade and `translateY(10px -> 0)`, `240ms`, `50ms` stagger.
- AI insights strip: fade over `220ms` after the KPI row.
- Table and inspector: opacity transition only; do not stagger all eight rows.

The decorative AI wave may use the same subtle sparkle and maximum `2px` tile movement as the
Overview reference. Disable it under reduced motion.

## Upload Invoice

On hover, change teal from `#0F8B94` to `#0C7480`, add
`0 6px 18px rgba(15, 139, 148, 0.18)`, and move the upload icon up by `1px` over `140ms`.

On activation, provide an immediate pressed state. If a file picker or upload drawer takes time
to appear, retain button focus and show a short pending state rather than accepting repeated
clicks.

## KPI Cards

Cards lift by `2px`, strengthen their border and shadow, and slightly increase icon-background
saturation on hover. Tooltips may show:

- All invoices: total records, updated today, pending action.
- Waiting for review: queue count and oldest waiting time.
- Needs correction: count blocked by missing or invalid fields.
- Approved: approved count for the current reporting cycle.
- Exported: count sent to a configured destination.

Count-up is optional, first load only, and must never replay after filtering.

## AI Insights Strip

The values may count once from zero to `8`, `3`, and `2`. On cell hover, use background
`#FAFCFE`, slightly enlarge the number, and keep separators static.

The duplicate tooltip may show high- and medium-confidence counts and the most recent related
invoice. `View all insights` deepens its text color and moves its arrow `2px`.

## Search, Tabs, Filters, And Sort

Search focus uses a teal border and shared focus ring over `140ms`.

The segmented control for `All`, `Open`, and `Completed` may animate one background indicator
between tabs over `180ms`. The content table crossfades over `160ms`; do not slide the entire
table horizontally.

Dropdowns move from `translateY(6px)` to zero and fade in over `180ms`. Sort uses only standard
hover and open states.

## Invoice Table

On row hover:

- background becomes `#FAFCFE`
- `View` opacity changes from `0.78` to `1`
- overflow icon opacity changes from `0.55` to `1`

The selected row uses background `#F4FBFC`, outline `1px solid #7ED3D9`, and a teal or blue
selected radio. Sortable headers darken their text and increase arrow opacity on hover.

Status tooltip copy:

- Reading: `The invoice is currently being read.`
- Waiting for review: `Ready for human review.`
- Needs correction: `Required information is missing or invalid.`
- Approved: `Validated and approved by a reviewer.`
- Exported: `Included in a completed export.`

Keep the tooltip language aligned with actual application state. Do not claim an external system
received an invoice unless delivery is confirmed.

## Right-Side Invoice Inspector

On initial open, the panel enters from `translateX(18px)` while fading in over `280ms`. On row
selection changes, keep the panel mounted and crossfade its content over `180-220ms`.

The external-open and close icon buttons gain a visible circular hover background. Use neutral
gray for open and soft red only for the close hover if it remains visually restrained.

Do not expose reviewer decision buttons here. `Invoices` is inspection-oriented; decisions
belong to Review Queue or the dedicated review workspace.

## Validation Summary

Rows fade in with a `30ms` stagger after the selected invoice data is available. Hovering
`Warnings` may show the warning count, concise issue name, and whether approval is blocked.

Passed, Warning, and Error icons can scale to `1.05` on hover. They must remain static otherwise.
Do not blink error or warning icons.

## Invoice Preview

Fade the PDF thumbnail in over `220ms` after it has rendered. While rendering, show a stable
placeholder with the same dimensions to prevent layout shift.

On hover, strengthen the border and surface shadow slightly. The `Open invoice` action becomes
more prominent through a soft teal background.

Optional cross-highlighting: hovering invoice date, due date, or billing metadata can show a
single soft-blue overlay on the corresponding preview region. This requires reliable source
coordinates; omit it when coordinates are unavailable.

## Open Invoice

On hover, use a teal border, background `#F3FBFC`, and a `2px` directional icon shift over
`140ms`. On press, use `scale(0.985)` over `90ms`.

If it opens a full invoice modal:

- overlay fade: `160ms`
- modal scale: `0.98 -> 1`
- modal duration: `220ms`
- return focus to the button after close

If it navigates to the dedicated invoice page, use normal in-app navigation and preserve the
selected invoice in browser history.

## Loading State

Use skeletons for five KPI cards, the AI insights strip, eight table rows, and the right-side
inspector. Base: `#F1F5F9`; shimmer: `#F8FAFC`; duration: `1.4s linear infinite`. Maintain final
component dimensions and disable shimmer under reduced motion.

## Responsive Behavior

- `>=1440px`: full table and fixed right inspector.
- `1280-1439px`: reduce column spacing and inspector padding.
- `1024-1279px`: keep the table primary; the inspector can narrow or become an overlay.
- `<1024px`: table becomes a scan-friendly list and the inspector becomes a full-height drawer.
- Replace hover-only details with tap popovers or a compact bottom sheet on touch devices.

## Priority

Required: upload-button feedback, KPI hover, active tab transition, search focus, filter
dropdowns, selected row, in-place inspector update, validation tooltip, preview loading, Open
invoice feedback, skeleton loading, and reduced-motion support.

Optional: KPI count-up, AI insight count-up, decorative AI movement, and metadata-to-preview
cross-highlighting.

