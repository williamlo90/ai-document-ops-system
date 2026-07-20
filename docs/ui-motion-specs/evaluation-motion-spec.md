# Evaluation Motion And Interaction Specification

Status: Design handoff. Implementation has not started.

Visual reference:
[modern-operations-evaluation.png](../assets/ui-reference/modern-operations-evaluation.png)

## Purpose

Evaluation must answer:

1. Did the latest run pass?
2. Did a measured regression occur?
3. How did quality change from the prior comparable run?
4. Which fields or scenarios remain weak?
5. How broadly can the results be trusted?

```text
Read verdict
-> inspect regression status
-> read the quality trend
-> inspect changed fields
-> inspect scenario coverage
-> open failure details or run a new evaluation
```

The page must feel analytical and honest. It must distinguish synthetic evidence from production
accuracy and measured values from estimates.

## 1. Shared Visual And Motion Tokens

```css
--motion-instant: 80ms;
--motion-fast: 120ms;
--motion-standard: 180ms;
--motion-expand: 220ms;
--motion-panel: 280ms;
--motion-page: 320ms;
--motion-chart: 700ms;
--ease-enter: cubic-bezier(0.2, 0.8, 0.2, 1);
--ease-panel: cubic-bezier(0.16, 1, 0.3, 1);
--ease-exit: cubic-bezier(0.4, 0, 1, 1);

--primary: #0F8B94;
--primary-hover: #0C7480;
--primary-soft: #E8F7F8;
--blue: #2563EB;
--blue-hover: #1D4ED8;
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

Use `6-8px` radii for controls and surfaces and `999px` only for pills. Informational surfaces
do not lift. Clickable surfaces may move up `2px` and gain
`0 8px 22px rgba(15, 23, 42, 0.07)` over `180ms`.

Tooltips appear after `200-250ms`, fade from zero, and move from `translateY(4px)` over `150ms`.
Maximum width: `280px`; padding: `10px 12px`; background: `#0F172A`; white text.

All interactive elements use a visible focus ring:

```css
outline: none;
box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
```

## 2. Data Integrity Rules

- The screenshot values are layout examples. Runtime values come from stored evaluation runs.
- `Run passed` must be computed from the displayed quality gates.
- Improved, Stable, and Regressed counts must add up to the displayed comparable-field
  denominator. Show excluded or newly introduced fields separately.
- A negative delta may remain Stable only when it is inside a documented regression tolerance.
  Display that tolerance in the Regression summary tooltip.
- Use percentage points (`pp`) for changes between percentages.
- Estimated cost must be labelled estimated and reconciled from recorded usage when available.
- Never present a synthetic small test set as production accuracy.

These rules resolve apparent sample-data ambiguity in the visual reference, such as a `-1.0 pp`
Tax change shown as Stable and a summary without an explicit denominator.

## 3. Page Entrance

Run once on route entry:

1. Header and Run evaluation: `0ms`
2. Verdict and KPI cards: `60ms`
3. Quality trend: `140ms`
4. Current run and Known limits: `190ms`
5. Field performance and Scenario coverage: `230ms`
6. Recent runs: `260ms`

Sections fade and move from `translateY(10px)` over `270ms`. The chart container enters before
its one-time line drawing. Do not replay the entrance when selecting another run.

## 4. Header And Synthetic Badge

The synthetic badge uses soft blue, `28px` height, `0 10px` padding, and compact radius. Its
tooltip says:

```text
Synthetic test set

Results are based on labeled test documents generated or curated for evaluation.
They do not represent production accuracy.
```

Keep the nearby limitation statement visible without requiring hover.

## 5. Run Selector

The run dropdown is about `250px` wide with `46px` rows, date, status, and Current marker. After
six items, scroll internally. Enter with opacity and `translateY(6px -> 0)` over `180ms`.

Selecting a run must not reload the page. Crossfade KPIs over `150ms`, the field table over
`180ms`, and update chart selection, Current run, Regression summary, and URL:

```text
/evaluation?run=2026-07-18
```

Browser back restores the selected run.

## 6. Run Evaluation

The primary button is `42px` high with teal background and white text. Hover darkens teal, adds
`0 8px 20px rgba(15, 139, 148, 0.18)`, and moves up no more than `1px`. Press uses
`scale(0.985)` over `90ms`.

Confirmation modal:

```text
Run evaluation?

Test set
Synthetic invoice test set v1.4

Documents
20

Estimated provider calls
20

Estimated cost
$0.08
```

Use actual version, count, call estimate, and cost estimate. Actions: Cancel and Run evaluation.

## 7. Running, Success, And Failure

Running state shows actual stages and counts:

```text
Running evaluation

Reading test documents       20 / 20
Extracting invoice fields    14 / 20
Running validation checks     8 / 20
Comparing with baseline       Pending
```

Progress height: `6px`; neutral track; teal fill; width transition `240ms`. Never animate fake
progress independent of real stage updates. The trigger becomes `Running evaluation...` with a
`16px` spinner and prevents duplicate runs.

On success, show a one-time check entrance from `scale(0.82)` over `220ms`, then:

```text
Evaluation completed

Run passed
No regressions detected
20 documents evaluated in 24 seconds
```

Update the page without full reload and show a concise completion toast.

If the run does not complete validly:

```text
Evaluation could not be completed

14 of 20 documents were processed.
No partial results were added to comparison history.
```

Store the attempt separately. Do not replace the last valid current run. Actions: View technical
details and Retry evaluation.

## 8. KPI Cards

Cards: Run passed, Test documents, Regressions, Duration, Estimated cost. Enter with `45ms`
stagger. Optional first-load count-up lasts `650ms` for numeric values only.

Tooltips may show:

- Verdict: configured gates and their observed values.
- Documents: synthetic/production counts, languages, and templates.
- Regressions: improved, stable, regressed, new, excluded, and regression tolerance.
- Duration: observed stage durations.
- Cost: estimated total, calls, per-document estimate, and prior-run change.

Do not animate static informational cards on hover beyond a border change.

## 9. Quality Trend Chart

Series: Field match in teal, Validation match in blue, and the configured quality gate as a
dashed neutral line. Label only the latest points by default.

First-load sequence:

1. axes and grid fade `180ms`
2. quality gate fades `200ms`
3. Field match draws `650ms`
4. Validation match draws `650ms` after `80ms`
5. point markers scale in `120ms`

On point hover, grow radius from `4px` to `7px`, show a `13px` halo and vertical crosshair, and
highlight both series at that run. Tooltip includes date, both match values, gate, changes in pp,
document count, provider errors, and estimated cost.

Legend hover emphasizes one series and lowers the other to `0.25` opacity. Restore all series
over `160ms` on exit.

Clicking a point selects the run, updates dependent panels, adds a selected vertical line, and
updates the URL. It does not open a modal.

Range options: Last 5, Last 10, Last 20, All runs. Range changes crossfade or morph over `220ms`
without replaying full line drawing.

If the Y axis is zoomed to `90-100%`, show `Zoomed scale: 90-100%` and an explanation tooltip.

## 10. Regression Summary

Rows for Improved, Stable, Regressed, and New failures show count and prior-run comparison.
Hover reveals the exact comparison run, largest change, tolerance, and denominator.

Clicking a row filters Field performance and reveals a chip such as `Status: Improved`. Table
content crossfades over `160ms`.

## 11. Field Performance

Columns: Field, Current, Previous, Delta, Status. Row hover uses `#FAFCFE` over `120ms`.

The Tax tooltip may show current and prior values, delta in pp, matched cases, failures, and View
failed case. A field is Regressed only when it crosses the configured regression rule; otherwise
label it Stable and explain the tolerance.

Status treatments:

- Improved: green text and soft green
- Stable: muted text and neutral background
- Regressed: red text and soft red, optional `3px` left accent

Clicking a row opens a `420px` drawer with current/prior matched counts, failed cases, expected and
predicted values, and a cautiously worded possible cause. Actions such as Open test case and View
extraction trace are shown only when those artifacts exist. Drawer enters over `280ms`.

## 12. Scenario Coverage

Coverage bars represent current cases divided by target cases, not accuracy. Label both counts.
On first load, widths animate to target over `650ms` with `50ms` stagger.

Row tooltip includes current cases, target, coverage, remaining gap, and examples. Clicking a row
opens a drawer listing test cases, pass/fail, document category, included run, and coverage gap.

## 13. Current Run, Limits, And Recent Runs

Current run rows use only `#FAFCFE` hover. Tooltips may show exact completion time, average
duration, call retries/errors, and cost comparison when recorded.

Known limits remain visible. `Learn more` opens a plain modal covering synthetic documents, small
sample size, language coverage, and absence of customer validation. Avoid dramatic motion.

Recent run rows show status, field match, validation match, duration, cost, and regressions on
hover. Clicking selects the run. `View all` opens the run-history view or drawer.

## 14. Loading, Empty, And Error States

Use section skeletons for KPIs, chart, Regression summary, tables, coverage, and Current run.
Skeleton base `#EEF2F6`; highlight `#F8FAFC`; duration `1.4s`; low contrast.

Empty state:

```text
No evaluation runs yet

Run the synthetic test set to establish the first quality baseline.
```

CTA: Run first evaluation.

Panel-level errors must preserve unaffected data. A failed chart request does not hide Known
limits or recent run selection.

## 15. Reduced Motion And Prohibited Motion

Under `prefers-reduced-motion: reduce`, disable chart drawing, count-up, stagger, bar-width
animation, drawer slide, and success scaling. Use opacity transitions no longer than `100ms`.

Never blink failure status, pulse chart points indefinitely, rotate AI icons, float cards, bounce
buttons, show fake progress, use confetti, or replay the whole page on selection changes.

