# Phase 1 — evaluator and quality foundation

Status: **Phase 1 gate passed**.
Contract: [2.0.0](CONTRACT.md). Evaluator report version: **2.1**.

## Learning checkpoint

The original score measured eight invoice header fields. It could remain perfect
when a line quantity was wrong. The evaluator now separates header accuracy,
line-field accuracy, exact-line precision/recall, whole-invoice exactness, and
processing/validation completion. Missing observations and provider errors stay
in scheduled denominators. Reports serialize empty denominators as null.

The historical V1 dataset and published results are unchanged. Only records with
complete header, UOM-aware line and provenance labels enter the whole-invoice
denominator; label coverage is reported. Historical reports without these labels
display N/A. Their passing header/validation gate is explicitly labeled as such.

## Design and behavior

- Line matching uses a stable line reference when supplied, otherwise normalized
  description plus UOM. Repeated identical rows are a multiset. Non-identical
  rows sharing an identity are ambiguous and fail; no numeric best-fit permutation
  can improve their score. Ambiguous groups are reported separately.
- Description/UOM text is normalized; quantity and unit price retain precision.
  Amounts use Decimal with ROUND_HALF_UP. Ambiguous locale strings are not guessed.
  Applicable tax, discount and purchasing references are scored when labeled.
- Evidence is compared to independently supplied oracle anchors. Observed,
  normalized, derived and corrected evidence have different required metadata.
  A calculated amount cannot impersonate an observed amount. Wrong/missing
  evidence fails whole-invoice and exact-line results even if values are right.
- Extraction is evaluated before review. The controlled correction replay keeps
  its original proposal immutable and evaluates the reviewed result separately.
- Runtime invoice models still lack full UOM and line provenance. Phase 2 adds
  those fields and their persistence. Phase 1 does not fabricate them in provider
  serialization or claim that the production extraction pipeline already supplies them.

## Frozen development fixtures

[Expected records](../../../examples/benchmark/datasets/invoice_quality_v2/expected.json)
contain seven synthetic document variants and fourteen lines: table, stacked,
multiple pages, decimal comma, OCR noise, missing field and repeated identical
items. These are structured evaluator fixtures with source text, not seven new
PDF/OCR runs. All variants share a transaction family and remain in development.
They must never be divided across development and final holdout.

[Correction timeline](../../../examples/benchmark/datasets/invoice_quality_v2/correction-timeline.json)
contains a deliberately wrong proposal, a correction with actor/time/reason/source,
and three explicitly simulated dated revisions. A scoped decimal-comma rule is
replayed on both the wrong proposal and all previously correct fixtures. Tests
also check that the rule does not apply to another family/layout. This proves
replay mechanics; it is not actual reviewer history or OCR quality.

Mutation/replay evidence: [phase1-evaluator-regressions.json](phase1-evaluator-regressions.json).
Hashes bind fixtures, timeline and evaluator files. The source commit identifies
the starting checkout; the dirty-worktree flag and file hashes identify the
implementation before the single phase checkpoint commit.

## Reproduction

From the repository root, with the development environment installed:

```powershell
$env:PYTHONPATH = 'backend'
.venv/Scripts/python.exe -m unittest discover -s backend/app/tests -p 'test*evaluation*.py' -q
.venv/Scripts/python.exe scripts/evaluate_phase1_regressions.py --output docs/evidence/invoice-review-v2/phase1-evaluator-regressions.json
.venv/Scripts/python.exe scripts/run_phase1_diagnostic.py
```

The last command is a zero-call preflight. `--execute` performs at most one OCR
and one extraction call on one existing synthetic PDF; no retry is automatic.
The script refuses an existing output artifact. An explicitly chosen new
`--output` is needed for a separately authorized diagnostic after resolving a
failure. Extraction input size and output tokens are bounded before network use.
The diagnostic supports `mistral_ocr`, `gemini_ocr`, and `ocr_space`. Gemini uses the fixed
Google API origin with header authentication, PDF transcription into ordered
pages, and strict rejection of empty, malformed or truncated responses. Select
it with `PARSER_PROVIDER=gemini_ocr`, `GEMINI_API_KEY`, and
`GEMINI_OCR_MODEL=gemini-3.8-flash`. The existing OpenAI extractor is unchanged.
The legacy benchmark selector remains unchanged; Gemini is available through the
configured processing/evaluation pipeline and diagnostic. Dashboard cost is N/A
for models absent from its historical pricing snapshot.
Gemini free-tier availability depends on project quota; the diagnostic records a
conservative paid-rate estimate rather than claiming a verified zero bill.
The one-page diagnostic ceiling is USD 0.128216 for Gemini plus extraction,
under the USD 1 phase budget. It makes no automatic retries.

The validated configuration uses `PARSER_PROVIDER=ocr_space` and
`OCR_SPACE_API_KEY`, with the fixed free HTTPS endpoint, engine 2, and table mode.
No local OCR model is installed. The free service limits PDFs to 1 MB and three
pages; larger documents require a different provider. Partial/failed/empty OCR
responses are rejected. The legacy benchmark selector is not extended.

[Actual diagnostic](phase1-provider-configured-diagnostic.json): one existing
synthetic PDF, OCR plus OpenAI extraction and validation completed, 8/8 header
fields correct, validation codes and blocker outcome correct. OCR took 1.61 s;
extraction took 3.05 s. Estimated extraction cost USD 0.001983; OCR uses the free
endpoint. Source evidence coverage is 3/8; whole-invoice and line accuracy are
N/A because this diagnostic has no complete line/provenance oracle. This is a
plumbing diagnostic, not final quality evidence. Raw troubleshooting remains local.

## Local validation

- Backend: 636 tests, OK, 13 environment-dependent skips.
- Frontend: 26 tests across seven files, all passed; TypeScript/Vite build passed.
- Ruff and Git diff whitespace checks: passed.
- Frontend lint: no errors; seven existing warnings outside changed components.
- Final replay rule refinement: two focused replay/budget tests passed.

## Exit gate

- Value, missing/extra/repeated/ambiguous line and provenance mutations: pass.
- Missing/failed provider and unexecuted validation cannot pass: pass.
- Legacy headers remain readable; whole-invoice N/A is distinct: pass.
- Scoped correction replay and immutable original proposal: pass.
- Bounded actual OCR plus extraction diagnostic: **pass**.
- Final sealed holdout: not opened; final quality/CV results belong to Phase 6.

Publish this phase as one `phase-1:` checkpoint; use Git history for its SHA.
