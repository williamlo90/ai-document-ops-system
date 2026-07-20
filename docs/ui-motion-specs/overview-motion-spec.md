# Overview Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-overview.png](../assets/ui-reference/modern-operations-overview.png)

## Purpose

Motion on Overview must help the user identify what is urgent, what changed, and what needs
action. It must not turn the operational dashboard into a marketing animation.

## Shared Motion System

### Principles

Use animation only to:

- explain hierarchy
- confirm user input
- connect state changes
- direct attention to an important action

Do not use excessive bouncing, parallax, long chart animations, high-contrast shimmer, or large
flying-card movement. Do not animate every visible element.

### Timing

| Interaction | Duration |
| --- | --- |
| Fast micro interaction | `120-160ms` |
| Standard transition | `180-240ms` |
| Panel or drawer | `260-320ms` |
| Initial section entrance | `360-500ms` |

Use these easing values:

- Enter: `cubic-bezier(0.2, 0.8, 0.2, 1)`
- Exit: `cubic-bezier(0.4, 0, 1, 1)`
- Hover: `ease-out`
- Panel: `cubic-bezier(0.16, 1, 0.3, 1)`

### Visual Tokens

- Primary teal: `#0F8B94`
- Primary teal hover: `#0C7480`
- Primary teal soft: `#E8F7F8`
- Blue: `#2563EB`; soft blue: `#EAF2FF`
- Red: `#EF4444`; soft red: `#FEECEC`
- Orange: `#F59E0B`; soft orange: `#FFF4DF`
- Green: `#10B981`; soft green: `#EAFBF4`
- Purple: `#8B5CF6`; soft purple: `#F3EDFF`
- Page: `#F8FAFC`; surface: `#FFFFFF`
- Border: `#E6EDF3`; muted border: `#EEF2F6`
- Primary text: `#0F172A`; secondary: `#475569`; tertiary: `#64748B`

Use a compact radius that matches the reference:

- input and button: `6-8px`
- card and hero surface: `8px`
- pill and badge: `999px`

Shadows:

- Default surface: `0 1px 2px rgba(15, 23, 42, 0.04)`
- Hovered surface: `0 8px 24px rgba(15, 23, 42, 0.08)`
- Dropdown or tooltip: `0 12px 32px rgba(15, 23, 42, 0.12)`

### Common Feedback

- Card hover: `translateY(-2px)`, stronger border and hover shadow, `180ms`.
- Button hover: darken background by `6-8%`; move a trailing arrow `2px`, `140ms`.
- Button press: `scale(0.98)`, `90ms`.
- Table row hover: background `#FAFCFE`, `120ms`.
- Tooltip: opacity `0 -> 1` and `translateY(4px -> 0)`, `140ms`.
- Sidebar, search, title, separators, avatars, and pagination remain visually stable and use only
  normal hover or focus feedback.

### Reduced Motion

Under `prefers-reduced-motion: reduce`, disable slide transitions, staggered entrances, count-up
numbers, line drawing, donut drawing, floating decoration, and progress-width animation. Replace
them with a `100ms` opacity transition and no movement.

## Page Structure

The reference contains:

1. Greeting and urgent-work hero
2. Four KPI cards
3. AI findings card
4. Urgent alerts
5. Decision queue
6. Throughput chart
7. Exception breakdown donut
8. Pipeline summary
9. Recent decisions

## Initial Load Sequence

Keep the complete sequence under `500ms`, excluding count and chart drawing:

1. Hero: fade and `translateY(12px -> 0)`, `320ms`, no delay.
2. KPI cards: fade and `translateY(12px -> 0)`, `260ms`, `60ms` stagger.
3. AI findings: same KPI motion, entering last at about `240ms`.
4. Urgent alerts: fade and `translateX(12px -> 0)`, `300ms`, `180ms` delay.
5. Decision queue: fade and `translateY(10px -> 0)`, `280ms`, `220ms` delay.
6. Recent decisions: subtle fade from the right, `220ms`.

Do not replay page-load motion after ordinary filtering or component rerenders.

## Hero Briefing

The decorative wave is mostly static. Sparkles may pulse from opacity `0.25 -> 0.55 -> 0.25`
over `2.8s`. The small AI tile may move vertically by only `2px` over `4.5s`, infinite,
`ease-in-out`. Stop both under reduced motion.

The `Review urgent invoices` button uses the shared teal hover, arrow shift, and press state. On
activation, navigate directly to the urgent Review Queue filter without an intermediate modal.

## KPI Cards

The values `24`, `16`, `7`, and `12` may count up over `800ms`, once on first load only. Do not
count again after a data refresh.

Hovering a card lifts it by `2px`, strengthens its border, and slightly increases the icon
background saturation. Trend-pill tooltips may show:

- previous value
- current value
- percentage change
- last updated time

Tooltip width: `180-220px`; padding: `10px 12px`; radius: `8px`; dark background and white
text; `12px` body type.

## AI Findings

On finding-row hover:

- use background `#F8FBFD`
- scale the icon badge to `1.05`
- underline clickable text subtly
- transition over `120ms`

The PO mismatch tooltip may show `High confidence: 5`, `Medium confidence: 3`, the most recent
invoice, and `View all findings`. Tooltip width: `220-260px`.

`View all insights` shifts its trailing arrow by `2px` on hover.

## Urgent Alerts

Each alert gains background `#FCFDFE` and a `3px` left accent on hover. Use red for blocking
alerts and orange for attention. Status dots remain static; they may scale to `1.15` on hover but
must never blink.

If the panel supports collapse:

- content height: `240ms`
- content opacity: `180ms`
- chevron rotation: `180deg` over `180ms`

## Decision Queue

Invoice links deepen from `#2563EB` to `#1D4ED8` and gain a thin underline over `120ms`.
Selected or keyboard-focused rows use a teal `3px` left accent or a thin teal outline; ordinary
row hover uses `#FAFCFE`.

Risk tooltip examples:

- High: `Likely to require manual intervention`, confidence, and due risk.
- Medium: `Needs review before approval`.
- Low: `No immediate SLA risk`.

Confidence tooltip content:

- extraction confidence
- OCR confidence
- rule-match confidence
- last scored time

`Resolve` and `Review` darken by `6%` on hover. A dropdown caret rotates `180deg` when open.

## Throughput Chart

On first load only:

- draw each line over `900ms`, `ease-out`
- fade the area fill over `300ms` after a `300ms` delay
- scale points from `0 -> 1` with a `40ms` stagger

When a point is hovered, grow it from `6px` to `9px`, add a `14px` low-opacity halo, display a
vertical guide, and show a tooltip containing date, processed invoices, exceptions, approval
rate, and average handling time. Tooltip width: `200-240px`.

Hovering a legend item emphasizes its series and reduces the other series to `0.35` opacity.
Never loop chart motion or make points bounce.

## Exception Breakdown

On first load, draw the donut stroke over `700ms`, fade legend rows with `50ms` stagger, and
count the center value to `36` once.

On slice hover:

- move the slice outward by `6px`
- reduce other slices to `0.45` opacity
- replace the center label with the active count and category
- show percentage, common vendor, and average resolution time in a tooltip

Hovering a legend row highlights the related slice, uses background `#F8FBFD`, and scales the
legend dot to `1.1`.

## Pipeline Summary

Rows fade in with a `40ms` stagger. Counts may animate once over `600ms`. Row tooltips can show
the active count, oldest item age, and SLA risk count.

An optional thin progress strip may animate from zero to its target width over `700ms`. Omit it
if the panel becomes visually busy.

## Recent Decisions

On item hover, use `#FAFCFE`, scale the avatar to `1.03`, and darken the timestamp slightly over
`120ms`. `View all` shifts its arrow by `2px`.

## Loading State

Use skeletons for the hero, five top-row cards, five queue rows, chart area, and the two right-rail
panels. Skeleton base: `#F1F5F9`; shimmer: `#F8FAFC`; duration: `1.4s linear infinite`. Keep the
contrast low and disable shimmer under reduced motion.

## Responsive Behavior

- `>=1440px`: full reference layout.
- `1280-1439px`: preserve the right rail but reduce chart and table spacing.
- `1024-1279px`: stack lower analytics below the queue; keep urgent alerts visible.
- `<1024px`: collapse the sidebar, show queue rows as scan-friendly lists, and move secondary
  analytics below urgent work.
- On touch screens, convert hover-only tooltips into tap-triggered popovers or a compact bottom
  sheet.

## Priority

Required: hero entrance, KPI stagger, alert hover, queue row hover, chart tooltip, donut hover,
recent-decision hover, button feedback, skeleton loading, and reduced-motion support.

Optional: count-up values, decorative floating motion, pipeline progress animation, and detailed
AI finding tooltips.

