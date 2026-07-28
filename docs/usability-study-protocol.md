# Invoice Review Usability Study Protocol

Status: `PLANNED_NOT_RUN`.

This protocol exists to prevent an informal demo from being reported as user research. Do not add
results until sessions have actually been observed and the raw notes are retained privately.

## Research Question

Can a finance or accounts-payable user complete the core invoice workflow without product
explanation, understand why approval is blocked, and avoid an unsafe decision?

## Participants

- 3–5 people familiar with accounting, accounts payable, bookkeeping, or invoice administration.
- Do not use the builder as a participant.
- Record role and experience band, not employer, customer, or unnecessary personal information.
- Use synthetic invoices only.

## Tasks

1. Find an invoice waiting for review.
2. Compare one extracted value with its PDF source.
3. Explain why a mismatched invoice cannot be approved.
4. Correct a supported field and identify what evidence will be saved.
5. Request a correction for an unresolved blocker.
6. Approve a clean invoice.
7. Prepare an approved invoice export.

The facilitator must not explain navigation or terminology during the first attempt. Assistance can
be given after the participant is visibly blocked, but it must be recorded.

## Measures

| Measure                 | Recording rule                                                              |
| ----------------------- | --------------------------------------------------------------------------- |
| Task completion         | Complete, complete with help, or incomplete.                                |
| Unsafe approval attempt | Count every attempt to approve while a blocker remains.                     |
| Time on task            | Start at task prompt; stop at the visible outcome.                          |
| Assistance              | Record the exact hint and when it was needed.                               |
| Blocker comprehension   | Participant explains the issue and required next action in their own words. |
| Correction error        | Participant changes a field that the PDF does not support.                  |
| Navigation error        | Participant opens an unrelated primary page before finding the task.        |
| Confidence              | One 1–5 rating after the full journey, reported as individual observations. |

## Session Record

Keep raw notes outside Git. The public report should use an aggregate table with no names:

| Participant | Experience | Completed without help | Unsafe attempts | Median task time | Main confusion |
| ----------- | ---------- | ---------------------: | --------------: | ---------------: | -------------- |
| P1          | Pending    |                Pending |         Pending |          Pending | Pending        |

## Decision Rules

- Any unsafe approval that the backend permits is a release-blocking defect.
- Two participants failing the same task without help creates a usability issue.
- A label misunderstood by two participants must be rewritten before adding more UI.
- Do not claim a percentage improvement with fewer than a meaningful comparative sample.
- Do not convert observed task time into labor or cost savings without a measured manual baseline.

## Reporting

Publish:

- participant profile bands;
- task outcomes and assistance;
- observed errors and quotes paraphrased without identity;
- changes made because of the study;
- unresolved findings and sample-size limits.

Do not publish:

- names, employers, customer invoices, recordings, or raw notes;
- “users loved it” summaries without task evidence;
- production-readiness or business-impact claims derived from this small study.
