# System Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-system.png](../assets/ui-reference/modern-operations-system.png)

## Purpose

System must answer:

1. Is core invoice processing available?
2. Which service is degraded or unavailable?
3. What is processing, waiting, completed, or failing?
4. Where does throughput drop between stages?
5. What action can an authorized operator take?

```text
Read overall health
-> identify degradation
-> inspect processing flow
-> open service or job detail
-> investigate or retry
-> confirm observed recovery
```

The page must feel calm, operational, and trustworthy rather than like a raw engineering console.

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
--green-dark: #047857;
--green-soft: #ECFDF5;
--orange: #F59E0B;
--orange-dark: #D97706;
--orange-soft: #FFF7E8;
--red: #EF4444;
--red-dark: #DC2626;
--red-soft: #FEF2F2;
--page-bg: #F7F9FC;
--surface: #FFFFFF;
--surface-muted: #F8FAFC;
--border: #E4EAF0;
--border-muted: #EDF1F5;
--text-primary: #0F172A;
--text-secondary: #475569;
--text-muted: #64748B;
```

Use `6-8px` radii for controls and surfaces. Informational cards do not lift. Clickable rows and
controls use restrained hover over `120-180ms`.

Tooltips appear after `200-250ms`, enter with opacity and `translateY(4px)` over `150ms`, and
remain under `280px` wide. All controls use a visible focus ring:

```css
outline: none;
box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
```

## 2. Operational Data Integrity

- Show uptime only when a persisted monitor actually measures the stated period.
- Label cached or polled status with its observed timestamp. Do not call it real-time unless it
  is continuously updated within a documented freshness target.
- Processing stage counts come from a defined cohort and time window.
- If percentages represent conversion from the previous stage, compute each as
  `current_stage_count / previous_stage_count`.
- Do not mix cumulative conversion from Upload with previous-stage conversion in one column.
- Retry count increments only after a retry request is accepted.
- Recovery is announced only after an observed successful check.
- Credentials, secrets, raw prompts, and sensitive provider responses never appear in this UI.

The sample System image contains flow percentages that do not consistently match its caption.
For counts `52, 51, 48, 48, 47, 46`, previous-stage conversion is approximately
`100%, 98%, 94%, 100%, 98%, 98%`. Implementation must calculate these values rather than copying
the sample labels.

## 3. Page Entrance

Run once on route entry:

1. Header and Refresh: `0ms`
2. Status banner: `60ms`
3. KPI strip: `120ms`
4. Service status: `170ms`
5. Needs attention: `160ms`
6. Processing flow: `210ms`
7. Recent processing and connected services: `240ms`

Sections fade and move from `translateY(8px)` over `260ms`. Do not replay entrance on refresh or
tab changes.

## 4. Refresh Status

On hover, use background `#F8FAFC`; rotate the refresh icon no more than `30deg`.

On activation, rotate it once by `360deg` over `600ms`, replace the label with `Refreshing...`,
disable duplicate requests, and refresh panels without page reload.

After completion, crossfade timestamps, highlight only changed rows, and show `System status
refreshed`. If nothing changed, update only the observation time.

On failure, preserve the last observed status and show its age; do not replace it with healthy or
unknown values silently.

## 5. Overall Status Banner

The reference state is:

```text
Operational with one degraded service

Invoice uploads, reading, extraction, and storage are healthy.
Accounting export is degraded.
```

A mostly operational banner may use soft green while the degraded detail remains amber and
visible. `View status details` opens a summary drawer or modal.

When health changes to degraded, transition border from green to amber and crossfade the icon
over `300ms`; never shake or pulse. On observed recovery, use one soft-green highlight over
`600ms` and a toast naming the recovered service.

## 6. KPI Strip

Metrics: Processing now, Waiting, Completed today, Needs attention. Tooltips may show stage
breakdown, queue reason, oldest wait, average duration, observed success rate, and active alert
from measured data.

Click behavior:

- Processing now -> Processing tab with active filter
- Waiting -> Processing tab filtered to waiting
- Completed today -> Processing tab filtered to completed
- Needs attention -> focus or open the attention panel

URL state must reflect the selected tab and filter.

## 7. Tabs

Tabs: Status, Processing, Integrations, Audit. Active indicator slides over `180ms`; content
crossfades over `160ms`. Persist state:

```text
/system?tab=status
```

Do not replay page entrances on tab changes.

## 8. Core Service Status

Columns: Service, Status, Uptime (when measured), Last check, Recent activity, Action.

Row hover uses `#FAFCFE` over `120ms`. Degraded rows use solid `#FFFCF7` and a `3px` amber left
accent. Never blink.

Status tooltip semantics:

- Operational: recent checks passed within the freshness target.
- Degraded: service remains available but has elevated errors, timeouts, or latency.
- Unavailable: service cannot complete its monitored capability.
- Unknown: no sufficiently recent observation exists.

Uptime tooltip may show 24-hour, seven-day, and 30-day windows and incident count only when the
monitor stores those measurements. Clicking uptime opens status history.

## 9. Service Detail Drawer

Open from View or Investigate. Width: `440px`; enter from the right over `280ms`.

For Accounting export, show observed status, measured uptime if available, last successful
request, latest sanitized failure category, affected and unaffected capabilities, and a compact
incident timeline.

Actions may include Retry check, View logs, and Open integration settings. Restrict logs to
authorized users and redact secrets, payloads, customer data, and provider credentials.

## 10. Needs Attention

The alert remains visible while a check or retry runs. Hover strengthens the amber border without
translation. Clicking the alert or chevron opens the service detail.

Retry check behavior:

- label changes to `Checking...`
- show a `16px` spinner
- preserve the degraded state until a healthy response is observed
- display check timestamp and retry count

Success copy: `Connection restored. Accounting export is operational.`

Failure copy: `Service is still degraded. The destination did not respond.`

Do not imply a retry is in progress unless the backend confirms it.

## 11. Processing Flow

Stages in the reference: Upload received, PDF read, Data extracted, Checks completed, Export
attempted, Export succeeded.

Every flow must define:

- cohort start and end time
- whether counts are unique invoices or attempts
- percentage denominator

For previous-stage conversion, display:

```text
current stage count / immediately previous stage count
```

Caption: `Percentages show conversion from the previous stage.`

First load may draw the connector from top to bottom over `450ms`, fade stage icons with `45ms`
stagger, and then reveal counts. Run once only.

On stage hover, scale its icon to `1.06`, use `#FAFCFE`, lower other connectors to `0.55`
opacity, and show current count, prior-stage count, conversion, incomplete breakdown, and median
stage duration.

Clicking a stage opens Processing with a URL filter such as:

```text
/system?tab=processing&stage=extraction
```

## 12. Connected Services And Integration Detail

Rows show configured services and observed connection state. Hover uses `#FAFCFE`. Badge tooltips
show the last successful check or recent failed-check count.

Clicking opens integration detail with provider name, connection state, authentication status,
last check, last successful operation, and sanitized error summary when recorded.

Actions such as Test connection, Reconnect, and View configuration appear only when implemented
and authorized. Reconnect requires confirmation because it may affect active jobs. Never expose
secret values.

## 13. Recent Processing

Columns: Invoice, Stage, Status, Started, Duration, Attempts, Action.

Live duration changes crossfade over `100ms`; do not flash rows every second. Status changes
crossfade over `180ms`. Completed uses soft-green background for `700ms`; Failed uses soft red
for `700ms` and exposes Retry when allowed.

Status tooltips describe stage, start time, attempt count, waiting reason, queue position, or
sanitized failure category from runtime data. Avoid false estimated-start promises when the queue
cannot calculate them.

View opens a Processing Trace drawer.

## 14. Processing Trace And Retry

The trace lists invoice ID and timestamped stages. A failed stage includes sanitized failure
reason, current attempt, retry limit, and whether partial work was committed.

Actions: Retry stage, Open invoice, View logs, gated by capability and authorization.

On Retry:

- lock the action while the request is pending
- increment attempts only after acceptance
- update status to Retrying
- retain failure details if retry fails

Success: `Retry completed. Invoice processing resumed.`

Failure: `Retry failed. The service remains unavailable.`

## 15. Maintenance

The compact card shows whether maintenance is scheduled. Calendar hover says `View maintenance
calendar`. A scheduled event includes service, date, time, timezone, and expected effect.

`All systems are up to date` refers to maintenance/version state, not health. Do not use it to
contradict a degraded operational service.

## 16. Audit Tab

Rows: Timestamp, Actor, Action, Target, Result. Filters: actor, action type, date, result, service.

Clicking an entry opens detail with actor, exact time, previous state, result, and request ID when
recorded. Audit data is immutable from this UI. Raw payloads and secrets remain hidden.

## 17. Loading, Empty, And Partial Errors

Use section skeletons for banner, KPIs, service rows, processing flow, attention, and recent
processing. Base `#EEF2F6`; highlight `#F8FAFC`; duration `1.4s`; low contrast.

Empty processing state:

```text
No recent processing activity

New invoice jobs will appear here once processing begins.
```

If one service panel fails, preserve other observed panels and identify the failed refresh. Never
convert missing telemetry into zero activity or Operational status.

## 18. Keyboard And Responsive Behavior

Tabs, service rows, stage rows, actions, drawers, and audit filters must be keyboard accessible.
Return focus after drawers and confirmation dialogs close.

- `>=1280px`: reference layout with right operational rail.
- `1024-1279px`: right rail moves below the primary table or opens as a drawer for details.
- `<1024px`: KPIs become `2 x 2`; tables become compact lists or horizontal scrollers; service
  and trace details use full-height drawers.
- Touch devices use tap-triggered popovers instead of hover-only content.

## 19. Reduced Motion And Prohibited Motion

Under `prefers-reduced-motion: reduce`, disable connector drawing, stagger, drawer slide, status
flash, icon rotation, and translated content changes. Use fades no longer than `100ms`.

Never blink degraded services, shake errors, pulse chart or flow points indefinitely, rotate AI
icons, float cards, bounce buttons, show fake progress, use confetti, or re-enter the whole table
after refresh.

