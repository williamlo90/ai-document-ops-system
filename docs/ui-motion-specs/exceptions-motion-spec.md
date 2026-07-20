# Exceptions Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-exceptions.png](../assets/ui-reference/modern-operations-exceptions.png)

## Purpose

Exceptions is the invoice issue triage center. Users must be able to understand the workload,
identify urgent exceptions, inspect causes and checks, assign an owner, and enter the resolution
workflow without losing context.

```text
Understand exception workload
-> identify urgent work
-> select an exception
-> inspect cause and checks
-> assign or open the invoice
-> resolve through validated workflow
-> continue to the next exception
```

This page is an operations console, not a generic error table. Motion must improve scanning,
selection, and feedback rather than decorate risk.

## 1. Layout

Use a desktop master-detail layout:

```text
Exception workspace   flexible, approximately 70-74%
Exception details     360-390px, approximately 26-30%
```

Reference viewport:

- viewport: `1536 x 1024px`
- sidebar: about `242px`
- top navigation: `68px`
- right details: `360-390px`

Main area:

```css
background: #F7F9FC;
padding: 22px 18px 24px 22px;
gap: 16px;
```

Right panel:

```css
position: sticky;
top: 68px;
height: calc(100vh - 68px);
overflow-y: auto;
background: #FFFFFF;
border-left: 1px solid #E4EAF0;
```

The details panel remains visible while the exception list scrolls.

## 2. Visual Tokens

Core colors:

```css
--primary: #0F8B94;
--primary-hover: #0C7480;
--primary-soft: #E8F7F8;
--blue: #2563EB;
--blue-soft: #EAF2FF;
--red: #EF4444;
--red-dark: #DC2626;
--red-soft: #FEF2F2;
--orange: #F59E0B;
--orange-soft: #FFF7E8;
--green: #10B981;
--green-soft: #ECFDF5;
--purple: #8B5CF6;
--purple-soft: #F3EDFF;
```

Neutral colors:

```css
--page-bg: #F7F9FC;
--card-bg: #FFFFFF;
--border: #E4EAF0;
--border-muted: #EDF1F5;
--text-primary: #0F172A;
--text-secondary: #475569;
--text-muted: #64748B;
--text-faint: #94A3B8;
```

Use `6-8px` radii for controls and surfaces and `999px` for true pills. Shadows:

- default: `0 1px 2px rgba(15, 23, 42, 0.04)`
- floating menu: `0 12px 32px rgba(15, 23, 42, 0.14)`
- interactive hover: `0 6px 20px rgba(15, 23, 42, 0.07)`

## 3. Motion Tokens

```css
--motion-fast: 120ms;
--motion-standard: 180ms;
--motion-expand: 220ms;
--motion-panel: 260ms;
--motion-page: 320ms;
--ease-enter: cubic-bezier(0.2, 0.8, 0.2, 1);
--ease-panel: cubic-bezier(0.16, 1, 0.3, 1);
--ease-exit: cubic-bezier(0.4, 0, 1, 1);
```

Use `120-150ms` for hover, `140-180ms` for tooltips, `170-200ms` for dropdowns,
`180-220ms` for detail swaps, `240-280ms` for drawers and modals, and `260-320ms` for first
page entrance.

Never use bounce, infinite exception pulse, blinking alerts, unnecessary rotating icons,
floating loops, or aggressive red motion.

## 4. Initial Entrance

Run once on initial route entry:

1. Header: `0ms`
2. Insight banner: `50ms`
3. KPI cards: `100ms`
4. Category strip: `180ms`
5. Filters: `220ms`
6. Exception table: `260ms`
7. Details panel: `200ms`

Main sections fade from zero and move from `translateY(10px)` over `260ms`. The details panel
uses `translateX(12px)` and opacity over `280ms`. Do not replay entrances after filter changes.

## 5. Header And Export

Header copy:

```text
Exceptions
Resolve issues that are blocking invoice processing.
```

Use a `30px` title, `36px` line height, weight `680-700`, and a `13px` secondary subtitle.

`Export list` is `40px` high with `14px` horizontal padding and a compact radius. On hover use
background `#F8FAFC`, border `#CBD5E1`, and at most `translateY(-1px)` over `140ms`.

Its dropdown contains:

- Export current view
- Export all open exceptions
- Export resolved exceptions

Dropdown width: `220px`; item height: `38px`; padding: `6px`; enter with opacity and
`translateY(6px -> 0)` over `180ms`.

While preparing, show `Preparing export...` and a small spinner inside the selected menu item.
Never block the whole page. Exported data and available options must reflect the user's current
authorization.

## 6. Exception Insight Banner

The banner answers what requires attention now. The reference shows a high-risk count, concise
summary, top issue types, and `View all insights`.

- minimum height: `112px`
- padding: `18px 20px`
- radius: `8px`
- border: `#E4EAF0`
- background: white
- insight icon: `40px` circle, `#F4F7FF`, icon `#2563EB`

The icon enters from `scale(0.92)` and opacity over `220ms`. Issue items use a `40ms` stagger.

On issue hover, use background `#FAFCFE` and border `#DCE5ED` over `120ms`. A PO tooltip may
show open count, high-risk count, due-today count, and oldest age. Tooltip width: `230px`;
padding: `12px`; background: `#0F172A`; white text; radius: `8px`.

`View all insights` deepens blue and moves its arrow `2px`. Any expanded trend, vendor, SLA, or
operational suggestion must be derived from observed records. Do not present invented AI totals.

## 7. KPI Cards

The four cards are Open exceptions, High risk, Due today, and Resolved this week.

- four columns
- gap `14px`
- minimum height `104px`
- padding `16px 18px`
- value `30px`, weight `680`
- label `13px`
- trend `11-12px`

High risk may use solid background `#FFF9F9` and border `#FECACA`. Do not use a gradient or
strong red fill.

Cards enter with a `50ms` stagger. Count-up over `650-800ms` is optional and first-load only.
Hover uses `translateY(-2px)` and `0 8px 22px rgba(15, 23, 42, 0.07)` over `180ms`.

KPI tooltips may show additions, resolutions, net change, oldest age, due risk, blocked value,
and median resolution time only when those values exist in the dataset.

## 8. Category Strip

Categories in the reference:

```text
PO / Vendor 12
Tax / Amount 8
Duplicate 7
Receipt / Docs 5
Other 4
```

Container height: `48px`; padding `0 18px`; radius `8px`; white background; border
`#E4EAF0`. Separators are `1px` by `22px`.

Colors: blue for PO/Vendor, teal for Tax/Amount, orange for Duplicate, purple for Receipt/Docs,
and gray for Other.

Clicking a category activates the Issue type filter. Active state uses `#F4FBFC`, text
`#0F7A83`, and inset bottom line `#0F8B94` over `160ms`. Tooltips may show open count,
percentage, and average age.

## 9. Search, Tabs, Filters, And URL State

Components: Search, Open/Resolved/All, Issue type, Risk, Owner, Due date, and Sort by Priority.

Search is `190-210px` wide and `40px` high. Focus uses teal border and
`0 0 0 3px rgba(15, 139, 148, 0.12)` over `140ms`. Debounce input by `250ms`. Show an inline
spinner only when a request exceeds `300ms`. `Esc` clears a focused query.

Do not reset a selected row when it still exists in filtered results.

The status tabs use a shared active indicator moving over `180ms`. Table content crossfades over
`150ms`; do not stagger rows again.

Dropdowns enter from `translateY(6px)` with opacity over `180ms`. Active filters use soft teal
and show a compact count, such as `Risk 1`.

Persist filter and selection state in the URL:

```text
/exceptions?status=open&risk=high&owner=me&sort=priority&selected=INV-2025-04567
```

Refresh, share, and browser back must preserve the view.

## 10. Exception Table

Columns: Issue, Invoice, Vendor, Risk, Owner, Age, Due, Action.

- header height `40px`, `11-12px`, weight `600`
- row height `56-58px`, `12px`
- row divider `#EDF1F5`

Row hover uses background `#FAFCFE`; issue icons scale to `1.04`; action controls increase
opacity, all over `120ms`.

Selected row:

```css
background: #F4FBFC;
outline: 1px solid #67C6CE;
box-shadow: inset 3px 0 0 #2563EB;
```

Selection updates the details panel and URL without moving table scroll position. Keyboard row
movement updates the details panel.

## 11. Details Content Swap

Keep the panel mounted. Do not slide the entire panel between rows.

Old content fades and moves down `5px` over `90ms`. New content fades from `translateY(5px)`
over `160ms`. Keep the complete swap near `200-220ms` and avoid long per-section stagger.

## 12. Issue And Risk Semantics

Blockers use red icons, warnings orange, and informational or low-impact issues blue. Issue
tooltips explain the detected problem and whether approval is blocked.

Risk badges:

- High: `#FEF2F2`, text `#DC2626`, border `#FECACA`
- Medium: `#FFF7E8`, text `#D97706`, border `#FDE0B2`
- Low: `#EFF6FF`, text `#2563EB`, border `#D6E5FF`

Badge height: `24px`; padding `0 8px`; radius `6px`; `11px`, weight `600`.

Tooltips distinguish approval-blocking or SLA risk from non-blocking investigation. Badges never
pulse or blink.

## 13. Owner Assignment

Owner cells show a `26px` avatar and full name. Hover may show role, active exception count, and
average resolution time when available.

Click opens a `260px` assignment popover with search, team members, Unassigned, and current
workload. Recommended owner is permitted only when its basis is explainable; otherwise use a
neutral list.

After success, owner avatar and name crossfade over `160ms`, metadata updates, and a toast says
`Assigned to Alex Davis`. On failure preserve the previous assignment.

## 14. Age And SLA

Age uses `#475569`; near-SLA uses `#D97706`; breached SLA uses `#DC2626` and weight `600`.

Age tooltip may show exact detection time, remaining SLA, and priority score. `Due today` uses
`#EA580C`, weight `600`, with exact due time and remaining duration. Never blink or pulse due
text.

## 15. Row Actions

Primary labels are `Resolve` or `Investigate`, `34px` high and at least `96px` wide.

Resolve uses teal border and text. Investigate uses a neutral border. Hover uses `#F4FBFC` over
`120ms`; caret rotates `180deg` when open.

Resolve menu:

- Open invoice
- Assign owner
- View activity
- Mark as resolved, only when resolution is already validated or policy permits it

Investigate menu:

- Open invoice
- Compare possible duplicate, when supported
- Assign owner
- Snooze, when supported
- View activity

Hide unsupported actions rather than rendering dead controls.

## 16. Pagination

Footer copy: `Showing 1 to 8 of 36 results`. Buttons are `34px` square with `8px` radius. Active
uses teal and white; inactive hover uses `#F1F5F9`.

On page change, crossfade the table over `150ms`, scroll the list to its top, and preserve the
selection only if the selected item remains visible. Otherwise explicitly clear the panel or
select the first row according to the implemented product rule. Do not replay row entrances.

## 17. Details Panel Structure

Order:

1. Header
2. What happened
3. Blocking alert
4. What is required
5. Detected data
6. Related checks
7. Metadata
8. Actions

Use `28px` top padding, `24px` horizontal padding, `22px` bottom padding, `24-28px` section
spacing, and dividers `1px solid #E4EAF0`.

## 18. Detail Header And Explanation

Header content:

```text
Exception details                 High risk
INV-2025-04567
Acme Logistics - $12,450.00
```

Invoice ID becomes blue and underlined on hover with tooltip `Open invoice details`.

`What happened` uses a `16px` heading and a `13px` description with `21px` line height. Allow
three or four lines before `Show more`; do not truncate to one line.

Blocking alert:

```text
Approval is blocked until this issue is resolved.
```

Use `#FFF7F7`, border `#FECACA`, radius `8px`, padding `11px 12px`, and a red `16px` icon. It
may strengthen its border on hover but must not shake or pulse.

`What is required` provides direct actions. When multiple actions exist, use a short numbered
list rather than a paragraph.

## 19. Detected Data

Rows include PO number, invoice number, vendor, and total amount. Row height: `38-42px`; label
`12px #475569`; value `13px`, weight `500`; missing values `#DC2626`.

Hover uses `#FAFCFE` over `120ms`. The missing PO tooltip explains that no PO reference was found
and includes extraction confidence only when available.

Clicking the invoice number copies it and shows `Invoice number copied` for `1.2s`.

## 20. Related Checks

The reference shows Invoice extracted and Vendor matched as Passed, and PO number present as
Blocked.

Passed uses teal icon and text. Blocked uses red icon and soft-red badge. Hovering a row explains
the check in plain language.

The blocked check may open an accordion containing rule, policy version, observed value, and
severity. Animate height over `220ms`. Display version identifiers only when the system records
them; never invent policy provenance.

## 21. Detail Metadata And Actions

Metadata: `Detected 18 minutes ago - Owner James Smith`, `11px #64748B`. Timestamp hover shows
the exact date and time.

The action area may remain sticky:

```css
position: sticky;
bottom: 0;
background: rgba(255, 255, 255, 0.96);
border-top: 1px solid #E4EAF0;
padding: 16px 0 0;
```

Actions:

1. Open invoice
2. Assign
3. More

`Open invoice` is `44px` high, teal, with white text and an `8px` radius. Hover darkens teal,
adds `0 8px 20px rgba(15, 139, 148, 0.18)`, and moves up at most `1px`.

Navigation to Invoice Review Workspace may fade over `140ms`. Preserve exception context in URL
or route state.

The More menu can include Change priority, Copy exception link, View activity, and supported
Snooze or resolution actions. Separate sensitive actions with a divider.

## 22. Resolution Guardrail And Success

Opening an invoice does not resolve an exception. The valid flow is:

```text
Open invoice
-> correct or verify data
-> save or submit the decision
-> rerun validation
-> mark the exception resolved only after the blocker clears
```

On validated success, show:

```text
Exception resolved

PO number was added and validation passed.
```

Use background `#F0FDF4`, border `#BBF7D0`, and a one-time check entrance from scale `0.85` over
`220ms`. After `800ms`, offer `View invoice` and `Next exception`.

Do not remove the row before feedback. Under the Open filter, it may fade and collapse over
`240ms` after the user continues.

A note alone must not clear a deterministic blocker. Manual resolution is allowed only for a
non-blocking exception, after validation already passes, or through a backend-enforced,
authorized override with a required reason and immutable audit event.

## 23. Empty And Loading States

Filtered empty state:

```text
No exceptions found

There are no exceptions matching the current filters.
```

Actions: Clear filters and View all exceptions.

No open exceptions:

```text
All clear

There are no open exceptions blocking invoice processing.
```

Use a small green check without confetti.

Skeletons:

- insight icon, lines, and issue items
- four KPI cards
- table header and eight rows
- details header, paragraphs, data rows, checks, and actions

Base `#EEF2F6`; highlight `#F8FAFC`; duration `1.4s`. Never use a large central spinner.

## 24. Error States

Table failure:

```text
Exceptions could not be loaded

Check your connection and try again.
```

Keep a Retry action.

If details fail but the list is available, preserve the list and show:

```text
Exception details unavailable

The exception list is still available.
```

Assignment failure:

```text
Owner could not be updated

The previous assignment has been preserved.
```

Do not block the whole page for a local panel failure.

## 25. Keyboard Behavior

- Up/Down: move between rows
- Enter: open the selected exception
- Space: select a row
- Tab: enter row and panel controls
- Esc: close dropdown or popover
- `Ctrl/Cmd + K`: focus global search when that shortcut is supported globally

Keyboard selection uses the teal left accent plus
`0 0 0 2px rgba(37, 99, 235, 0.16)`. Restore focus after assignment and modal close.

## 26. Responsive Behavior

- `1280-1439px`: details `340px`; compact table columns; shorten owner display if necessary.
- `1024-1279px`: table uses full width; details become a `420px` right drawer entering over
  `280ms` with panel easing.
- `<1024px`: KPI becomes `2 x 2`; insight banner stacks; category strip scrolls horizontally;
  list becomes a compact table or exception cards; details use a full-screen drawer.
- Touch interfaces replace hover-only tooltips with tap popovers or a compact bottom sheet.

## 27. Reduced Motion And Static Elements

Under `prefers-reduced-motion: reduce`, disable count-up, page stagger, drawer slide, row collapse,
check scaling, and translated content swaps. Use fades no longer than `100ms`.

Keep sidebar, category separators, table dividers, vendor names, amounts, section titles, metadata,
help card, and pagination label static.

Never blink high-risk badges, pulse due dates, shake alerts, rotate KPI icons, loop AI glow,
over-lift rows, or slide the whole details panel for every selection. The final page must feel
like a calm, trustworthy exception operations console.

