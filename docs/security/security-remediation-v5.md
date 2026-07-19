# Security Remediation V5

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-008 from the 15 July 2026 security baseline
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-008: prompt-injection assurance not directly tested | `CLOSED_WITH_DETECTION_LIMITATION` | OCR is explicitly isolated as untrusted data, known instruction patterns create a deterministic approval blocker, critical real-provider values require matching PDF excerpts, and adversarial workflow tests prove approval is denied. Detection is not claimed to cover every possible attack. |

## Implemented Controls

- The extractor system message states that OCR is data, cannot alter rules or destinations, and must
  never be followed as an instruction.
- OCR is serialized inside a JSON value in the user message instead of being presented as a direct
  free-form instruction.
- A deterministic detector flags high-signal instruction attacks such as ignoring prior rules,
  impersonating system/developer messages, overriding invoice fields, requesting tool execution, or
  asking for the system prompt.
- A flag becomes the `potential_prompt_injection` validation error and is recorded as a sanitized
  `untrusted_content_flagged` audit event. Raw attack text is not logged.
- For the real `llm_json` provider, vendor, invoice number, invoice date, total, and currency values
  require a page-bound exact OCR excerpt that also supports the normalized value.
- Unsupported citations become `missing_field_evidence` errors. They remain visible for human review
  but cannot pass approval as AI-grounded values.
- Reviewer correction remains the explicit human override path and creates the existing before/after
  correction record.

## Executed Evidence

| Check | Result |
| --- | --- |
| Dedicated adversarial tests | 3 passed |
| Provider-boundary tests including prompt framing | 23 passed |
| Affected processing, review/export, and private-pack tests | 40 passed |
| Ruff and Black checks on affected files | Passed |
| Full backend regression | 422 passed |

The adversarial case presents a valid invoice followed by instructions to replace its number and
total, impersonate a developer message, return attacker-selected JSON, and reveal the system prompt.
The simulated compromised extractor follows those instructions and supplies high-confidence snippets.
The application still records security and evidence errors, keeps the document in review, and denies
approval.

## Residual Limitations

- Pattern detection is defense in depth, not a complete prompt-injection classifier.
- OCR providers can omit or alter hidden text before this application receives it.
- Human reviewers can intentionally replace flagged values; that is an audited business decision,
  not automatic trust in model output.
- A future model or prompt change requires rerunning the adversarial suite and realistic document
  evaluation.

## Release Decision

- Synthetic and controlled provider evaluation: `PASS_WITH_LIMITATIONS`.
- Unattended approval or export: prohibited by design.
- Real sensitive invoices: still `BLOCKED` by external scanner, provider-governance, deployment, and
  independent-review gates.
