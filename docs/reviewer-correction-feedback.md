# Reviewer Correction Feedback

The correction loop separates a request from a factual change:

```text
Reviewer requests a correction
  -> uploader sees the reason and edits the invoice beside the PDF
  -> system stores an append-only before/after event
  -> corrected invoice returns to the reviewer
```

## What Is Preserved

Every non-empty correction event stores:

- the original AI extraction, retained across later corrections
- the values immediately before and after the change
- a field-level diff, including line-item paths
- actor, reason, reason source, timestamp, document, and workspace scope
- whether the change came from intake checking or the protected review API

Saving unchanged data does not create a correction event. Finalized invoices remain immutable under
the existing workflow rules.

## User Experience

The primary UI keeps feedback concise:

- reviewers can open a field's source detail to see whether it is AI-extracted or
  reviewer-corrected
- AI-extracted values show available confidence, exact OCR excerpt, and source page
- reviewer-corrected values show actor, reason, and the latest before/after diff without retaining
  stale AI confidence
- uploaders see `Fix invoice` only after a reviewer requests a correction
- after a changed field is submitted, ownership returns to the reviewer

Authorized reviewers can inspect full lineage through
`GET /review/{document_id}/corrections` when detailed audit evidence is required.

## Private Dataset Export

Raw correction values can contain invoice data and are never a public artifact. Export them to the
Git-ignored private directory:

```powershell
python scripts/export_private_correction_dataset.py `
  --workspace default `
  --output _private_data/reviewer-corrections.jsonl
```

An output path elsewhere inside the repository is rejected. The optional `--summary` output contains
counts only: no document IDs, actors, reasons, or invoice values.

## Reproducible Evidence

Run:

```powershell
python scripts/evaluate_correction_feedback.py
```

The committed aggregate report is
[reviewer-correction-feedback-v1.json](evidence/reviewer-correction-feedback-v1.json). It uses
deterministic synthetic data to verify lineage, sequential corrections, no-op filtering, reviewer
reason carry-forward, and public-summary privacy.

This evidence does not prove that reviewer corrections improve a model, nor does it claim real-user
adoption or real-invoice accuracy. It proves that feedback is captured in an evaluation-ready form.
