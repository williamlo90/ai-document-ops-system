# Recruiter Demo Script - 3 to 5 Minutes

Recorded artifact: [3:37 captioned MP4](assets/demo/ai-document-ops-demo.mp4).

The committed recording uses synthetic benchmark PDFs and deterministic route-level API responses
to keep the UI walkthrough reproducible. Treat the reliability report and provider verification as
the backend and real-provider evidence; the video itself is a product-flow demonstration.

## Demo Goal

Show one business problem, one normal decision, one blocked exception, and the engineering evidence
behind both. Do not begin with architecture or technical dashboards.

## Preparation

- start the app with the real-provider profile when network access is reliable
- keep the mock profile available as a deterministic fallback
- prepare one clean synthetic invoice and the committed duplicate pair
- confirm the PDF renders before recording
- reset local demo data so the queue is easy to understand
- use a 1440 x 900 or similar desktop viewport

## 0:00 - 0:30: Problem and Claim

Say:

> Finance reviewers need to compare the source invoice with extracted data, catch exceptions, and
> record a decision. This system uses AI to read the invoice, deterministic rules to block unsafe
> states, and a human for the final decision.

Show the uploader navigation. Keep the explanation in business terms.

## 0:30 - 1:20: Upload and Read

1. Upload a clean synthetic invoice.
2. Show the explicit reading state.
3. Open the invoice when processing finishes.
4. Point out the PDF and extracted fields on the same screen.

Say:

> The model does not approve the invoice. It only proposes structured evidence. Even a clean result
> stops for reviewer approval.

## 1:20 - 2:10: Reviewer Decision

1. Switch to the reviewer view.
2. Open the clean invoice from Approvals.
3. Compare vendor, invoice number, dates, and total with the PDF.
4. Approve it explicitly.
5. Show the recorded actor, timestamp, audit-event count, and controlled-export eligibility.
6. Return to the list and show the updated status.

Point out that approve, reject, and correction are separate actions and that a completed decision
leaves visible evidence instead of only changing a status label.

## 2:10 - 3:10: Exception and Blocked Action

1. Process `duplicate_original.pdf` and `duplicate_copy.pdf` from the synthetic scenario set.
2. Open the duplicate copy in the reviewer queue.
3. Show the plain-language duplicate reason beside the source PDF.
4. Show that approval is disabled while correction and rejection remain available.

Say:

> This is the central safety boundary. The interface explains the blocker, but the backend also
> refuses approval independently. A hidden or modified button cannot bypass the rule.

## 3:10 - 4:00: Technical Evidence

Show the scenario evidence document or technical evidence view briefly.

Explain:

- 20 deterministic synthetic PDFs cover normal and difficult cases
- the initial real-provider run exposed three false fills in intentionally missing fields
- prompt null rules and a deterministic grounding guard corrected those failures
- the final controlled regression matched 160 of 160 evaluated fields and 20 of 20 validation outcomes
- this is a small synthetic golden set, not production accuracy

Then show the automated verification summary: backend tests, frontend tests, lint, and build.

## 4:00 - 4:30: Close

Say:

> The engineering claim is deliberately bounded: evidence-bound invoice extraction, deterministic
> validation, approval-gated execution, and an auditable review trail. The next proof needed is a
> permissioned real-world dataset and observed finance-reviewer usability, not another feature.

## Recording Checklist

- PDF is visible and readable
- no API keys, local paths, browser extensions, or private documents appear
- no console or network error appears
- clean invoice requires explicit approval
- exception reason is visible
- blocked approval is demonstrated
- technical evidence is shown after the business flow
- limitations are stated aloud
- final video is 3 to 5 minutes
