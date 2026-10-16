# Dataset protocol 2.0.0

Measurement protocol is unchanged. Under contract 2.1.0, the separate operator
study is deferred and optional; its untouched inputs do not block Phase 6.

This is a planned manifest, not a populated or sealed dataset. No final holdout
documents or answers are opened in Phase 0.

Allocate **60 development families**, **40 quality-holdout families**, and a
separate **20 time-study families**. Family counts are not invoice counts.
Each family groups related invoices, PO/receipt timelines, duplicate variants and
corrections. Development includes at least three meaningful dated layout/rule
revisions. Final counts must be recorded and sealed before Phase 6, never adjusted
after seeing output. The planned cohort sizes may only change through a new contract.

Each holdout needs at least ten oracle-positive transactions for each discrepancy
category (quantity, price, duplicate, receipt), ten clean hard-negative transactions,
and ten eligible submissions. Categories can overlap. The time cohort includes
at least ten eligible submissions and ten final exception outcomes. Record exact
invoice, line, pair, layout, revision and operation counts rather than equating
them with family counts. Insufficient categories block their release claim.

## Partition and oracle rules

Assign family ID, supplier-layout family ID, and duplicate-group ID globally.
All related records stay in one split, including altered layouts from the same
family. No ID may overlap across splits. Versioned purchasing policies may be
shared; holdout transaction instances and layout families may not. Store split
membership and hashes in the manifest. A deterministic generator seed alone is
not evidence of independence; inspect shared templates and near-duplicate content.

An oracle authoring pass uses business specifications, source documents and manually
specified expected arithmetic, not matcher/adapter output. Label provenance as
developer/AI-assisted synthetic where applicable. Expected records include required
field paths, explicit nulls, source evidence, PO/receipt snapshots, allocations,
policy/mapping versions, issue categories, expected action and terminal outcome,
and ERP record/ledger expectations. Expected and actual results use separate files.
Hidden oracle IDs must not be exposed to extraction as matching hints.

Required family files: source PDFs with license/provenance; invoice labels;
procurement JSON; event timeline; expected matching; expected posting; expected
correction events. Each artifact has relative path, SHA-256, role and split.
Use [manifest.schema.json](manifest.schema.json) and the initial
[manifest.json](manifest.json). A sealed manifest must have complete actual counts,
file hashes and freeze metadata (commit, model/prompt/config/evaluator versions).
Cross-record uniqueness/count/hash checks supplement JSON Schema validation.

## Scenario coverage

Cover exact match; partial and cancelled receipt; sequential/concurrent billing;
multi-PO; price/quantity tolerance boundaries; missing/stale source; wrong
company/vendor/currency; unknown UOM; repeated/ambiguous/reordered item; tax/discount;
missing printed value; unsupported inferred value; duplicate OCR/alias variations;
legitimate similar invoice; changed supplier mapping/policy; edited ERP draft;
provider failure; timeout before/after remote effect; restart; tenant isolation.

Freeze development regression cases before corrections or prompt changes. Replay
all prior correct cases plus new failures after every revision; record introduced,
recovered and persistent errors. A viewed or tuned-on holdout becomes development
data; create a new disjoint final holdout instead of repeatedly optimizing the old one.

Time-study data stays sealed separately until the study. Counterbalance manual-first
and assisted-first order, record operator familiarity, and retain raw time intervals,
active/waiting durations, outcomes and exclusions. Both conditions use the same
terminal outcome and oracle. Report only synthetic/sandbox single-operator evidence
unless a different design has actually been executed.
