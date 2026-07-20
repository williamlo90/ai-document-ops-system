# Exports Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-exports.png](../assets/ui-reference/modern-operations-exports.png)

## Purpose

Exports must make clear which invoices are eligible, which are already batched or exported,
which are blocked, what destination and format will be used, and whether the action can run now.

```text
Select eligible invoices
-> add them to a batch
-> verify eligibility
-> choose a configured destination and format
-> create or schedule when supported
-> inspect the recorded result
```

The page must feel controlled, transactional, and predictable. No invoice can be exported before
approval or while an unresolved blocker exists.

## 1. Shared Visual And Motion Tokens

```css
--motion-instant: 80ms;
--motion-fast: 120ms;
--motion-standard: 180ms;
--motion-expand: 220ms;
--motion-panel: 280ms;
--motion-page: 320ms;
--ease-enter: cubic-bezier(0.2, 0.8, 0.2, 1);
--ease-panel: cubic-bezier(0.16, 1, 0.3, 1);
--ease-exit: cubic-bezier(0.4, 0, 1, 1);

--primary: #0F8B94;
--primary-hover: #0C7480;
--primary-soft: #E8F7F8;
--blue: #2563EB;
--blue-soft: #EAF2FF;
--green: #10B981;
--green-soft: #ECFDF5;
--orange: #F59E0B;
--orange-soft: #FFF7E8;
--red: #EF4444;
--red-soft: #FEF2F2;
--page-bg: #F7F9FC;
--surface: #FFFFFF;
--border: #E4EAF0;
--border-muted: #EDF1F5;
--text-primary: #0F172A;
--text-secondary: #475569;
--text-muted: #64748B;
```

Use `6-8px` radii for controls and surfaces. Clickable surfaces may lift no more than `2px` over
`180ms`; informational surfaces remain still. Tooltips appear after `200-250ms`, enter with
opacity and `translateY(4px)` over `150ms`, and remain under `280px` wide.

All controls use a visible focus ring:

```css
outline: none;
box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
```

## 2. Capability And Eligibility Rules

- Destination names such as NetSuite are shown only for configured integrations.
- Unsupported destinations and formats are hidden, not displayed as inactive demo controls.
- Scheduling is shown only when the backend can persist, execute, cancel, and audit schedules.
- A successful export is recorded only after the destination or file-generation boundary
  confirms success.
- Failed exports do not mark invoices exported or discard the batch.
- Duplicate export protection must be enforced by backend idempotency, not only UI state.
- Daily export limits apply only when a configured destination policy actually requires them.

The visual reference contains a contradiction: `No previously successful export today` is shown
as passed while `Another export already created today` is also shown. Implementation must never
render both states as true. When a daily limit is active and a prior export exists, the first
check is Failed or replaced by one explicit policy check, and the primary action is disabled or
changed to a supported scheduling action.

## 3. Page Entrance

Run once on route entry:

1. Header: `0ms`
2. KPI cards: `60ms`
3. Tabs and filters: `130ms`
4. Table: `180ms`
5. Export Batch: `150ms`
6. Recent runs: `220ms`

Main sections fade and move from `translateY(8-10px)` over `260ms`. The right panel enters from
`translateX(12px)` over `280ms`. Do not replay entrance after filtering or selection changes.

## 4. KPI Cards

Cards: Ready to export, In batch, Exported today, Blocked. Hover tooltips may show counts, total
value, approval state, blockers, run results, and issue breakdown from observed data.

Clicking a KPI switches to its related tab and updates the URL. Informational cards change only
border on hover; clickable cards may use a subtle `2px` lift.

## 5. Tabs And Filters

Tabs: Ready, In batch, Exported, Blocked, Drafts. The active underline moves over `180ms`. Table
content crossfades over `150ms`; existing batch selection remains unless selected items become
invalid.

URL example:

```text
/exports?status=ready
```

Search debounce: `250ms`. Active filters use soft teal and show count, such as `Filters 2`.
The filter panel contains only supported filters: Vendor, Approval date, Currency, Country,
Amount range, Approved by. Actions: Reset and Apply filters.

## 6. Table Selection

Checkbox states:

- unchecked: border `#CBD5E1`
- checked: teal background and white check
- indeterminate: teal background and white horizontal line

Animate background and border over `120ms` and check scale from `0.8` over `100ms`.

Selected rows use background `#F4FBFC` without a large outline. On the first selection, show the
selection bar with opacity and `translateY(-6px)` over `180ms`:

```text
3 selected
Clear selection
Add to export
```

Fade it out over `140ms` when selection reaches zero.

Selection must reject invoices that are not approved, are already successfully exported, are in
another active batch, or have blockers according to backend state.

## 7. Add To Export

On activation:

1. Revalidate selected invoice IDs on the server.
2. Add only still-eligible invoices.
3. Return explicit accepted and rejected results.
4. Update the batch panel.

Loading copy: `Adding 3 invoices...`.

Success copy: `3 invoices added to export batch`.

Accepted rows move from Ready to In batch, use a soft-teal confirmation for `500ms`, then clear
their selection. Under the Ready tab, rows may fade out after `600-800ms`; do not remove them
before feedback.

If some items are rejected, preserve them in view and show their specific blocker. Do not report
the entire selection as successful.

## 8. Row Feedback

Row hover uses `#FAFCFE` over `120ms`. Invoice links deepen blue and underline. `Add` or `View`
shifts a directional icon by `2px`.

Status tooltip copy:

- Ready: approved with no unresolved export blocker.
- In batch: already included in an active batch.
- Blocked: cannot export until the displayed issue is resolved.
- Exported: included in a confirmed successful export.

Use the actual blocker or destination result.

## 9. Export Batch Panel

Keep the panel reachable:

```css
position: sticky;
top: 84px;
max-height: calc(100vh - 108px);
overflow-y: auto;
```

When selection changes, crossfade the count over `120ms` and transition the amount between old
and new values over `250ms`; do not count from zero.

`View invoices` expands a compact list of invoice ID and amount over `220ms`.

## 10. Destination And Format

`Change` opens an inline selector. Populate it from configured capabilities, not a hard-coded
marketing list. Example labels may include NetSuite, QuickBooks, SAP, Microsoft Dynamics,
Custom CSV, CSV, JSON, XML, or Native API only when supported.

After a destination or format change, display `Rechecking eligibility...` with a local `14px`
spinner. Replace check results over `180ms`. Do not reload the page.

When only one format is supported, explain that fact rather than showing unavailable options.

## 11. Eligibility Checks

Passed uses green; warning uses orange; failure uses red. Checks enter with `45ms` stagger after
real eligibility data arrives.

Checks may include:

- All invoices approved
- No unresolved blockers
- No invoice already exported successfully
- Destination is available
- Destination-specific batch policy is satisfied

Each tooltip explains the observed record or policy. Do not present a destination-specific daily
limit as a universal product rule.

When any blocking check fails, disable Create export and explain the exact next action. A warning
may allow continuation only when backend policy permits it.

## 12. Create Or Schedule

Default primary action is `Create export` when all checks pass.

If a configured destination imposes a daily window and scheduling is implemented, the primary
action may become `Schedule export for tomorrow`. Confirmation includes invoice count, total,
destination, format, exact date/time, and timezone.

On success:

```text
Export scheduled

The batch will run tomorrow at 12:05 AM Asia/Jakarta.
```

Then offer Edit schedule and Cancel schedule. If scheduling is not supported, do not render these
controls; explain the blocker and allow Save selection as draft.

## 13. Save Draft

Saving a draft preserves selected invoice IDs and current configuration without exporting.
Show local loading and then:

```text
Export draft saved

3 invoices were saved to Draft export #12.
```

Use an optional draft-name dialog only when naming is supported. Drafts must reopen from the
Drafts tab. A draft does not reserve eligibility permanently; revalidate before execution.

## 14. Recent Export Runs

Hovering a run may show status, invoice count, total value, destination, start/end time, duration,
and operator. Clicking View opens an Export Run drawer with result, filename, retries, and audit
history.

For failure:

```text
Failure reason

Connection to the configured destination timed out.
No partial export was committed.
```

Actions such as Retry export and Download error report appear only when supported and authorized.

## 15. Export Progress

During execution, show actual stage progress:

```text
Creating export

Validating invoices       Completed
Generating file           In progress
Sending to destination    Pending
Confirming result         Pending
```

For file-only export, omit the sending stage. If work continues in the background, state that
the user may leave and will be notified only when a notification mechanism exists.

Never use a fake indeterminate sequence as if it represented completed stages.

## 16. Success And Failure

On confirmed success:

```text
Export completed

19 invoices were successfully exported to the configured destination.
```

Use the actual destination name. Actions may include View run and Download file. Update the KPI
with a soft-green `500ms` flash.

On failure:

```text
Export failed

The destination did not respond before the timeout.
No invoices were marked as exported.
```

Preserve the batch and selection. Offer View details and an authorized Retry.

## 17. Loading, Empty, And Partial Errors

Use section skeletons for KPI cards, table, Export Batch, checks, and recent runs. Base
`#EEF2F6`; highlight `#F8FAFC`; duration `1.4s`; low contrast.

Empty state:

```text
No invoices are ready to export

Approved invoices without blockers will appear here.
```

CTA: View review queue.

If the recent-run panel fails, keep selection and batch controls usable. If eligibility cannot be
verified, disable export rather than assuming success.

## 18. Keyboard And Responsive Behavior

Checkboxes, tabs, filters, row actions, destination fields, and panel actions must be keyboard
operable. Preserve focus after panel updates and modal close.

- `>=1280px`: table plus sticky batch panel.
- `1024-1279px`: full-width table with batch as a `420px` right drawer.
- `<1024px`: compact invoice list and full-height batch drawer; filter controls collapse into a
  single filter action.
- Touch devices use tap popovers instead of hover-only tooltips.

## 19. Reduced Motion And Prohibited Motion

Under `prefers-reduced-motion: reduce`, disable count-up, stagger, drawer slide, amount animation,
row fade/collapse, and success flashes. Use fades no longer than `100ms`.

Never blink blocked states, bounce buttons, loop progress without real updates, use confetti,
re-enter the whole table on refresh, or slide the entire batch panel on each selection change.

