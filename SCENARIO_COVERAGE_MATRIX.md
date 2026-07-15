# Scenario Coverage Matrix

This matrix translates the committed 20-invoice evaluation set into business questions a
finance-operations reviewer can understand. Every fixture expects a human review decision;
passing validation never means automatic approval.

Final provider-backed regression: **160 / 160 evaluated fields matched** and **20 / 20 expected
validation outcomes matched**. Seven fixtures expect a static validation blocker. The duplicate
copy adds one stateful cross-document blocker when the pair is processed through the application.

## Normal And Format Variation

| Scenario | Business question | Expected system behavior | Observed result |
| --- | --- | --- | --- |
| `standard_usd` | Can an ordinary USD invoice be read without a false warning? | Extract the eight evaluated fields, find no validation blocker, and wait for review. | All fields matched; no blocker; reviewer decision required. |
| `zero_tax_usd` | Is a legitimate zero-tax invoice accepted? | Preserve zero tax, keep totals consistent, and wait for review. | All fields matched; no blocker. |
| `european_number_format` | Can European dates and decimal separators be normalized? | Normalize dates and amounts without changing their meaning. | All fields matched their normalized values; no blocker. |
| `high_value_idr` | Does a large IDR amount remain visible to a human? | Preserve the amount and currency and require the normal reviewer decision. | All fields matched; no automatic approval. |
| `multiple_line_items` | Can a multi-item invoice retain consistent totals? | Read the header values and keep subtotal, tax, and total consistent. | All evaluated fields matched; no blocker. |
| `long_vendor_name` | Is a long legal vendor name truncated or replaced? | Preserve the full vendor name and invoice values. | Full expected vendor name and all fields matched. |

## Missing Data

| Scenario | Business question | Expected system behavior | Observed result |
| --- | --- | --- | --- |
| `missing_vendor` | What happens when the seller is absent? | Leave vendor empty, flag a missing critical field, and block approval. | Missing value was not invented; blocker matched. |
| `missing_invoice_number` | What happens without an invoice number? | Leave it empty, flag a missing critical field, and block approval. | Missing value was not invented; blocker matched. |
| `missing_invoice_date` | What happens without an invoice date? | Leave it empty, flag a missing critical field, and block approval. | Missing value was not invented; blocker matched. |
| `missing_due_date` | Is an absent optional due date falsely treated as fatal? | Leave it empty and allow reviewer inspection without a validation blocker. | Empty value and no blocker matched expectation. |
| `missing_tax` | Can tax be absent when the total still equals the subtotal? | Leave tax empty and avoid inventing a tax amount. | Empty value, consistent total, and no blocker matched expectation. |

## Deterministic Business-Rule Failures

| Scenario | Business question | Expected system behavior | Observed result |
| --- | --- | --- | --- |
| `total_mismatch` | Can an incorrect total pass because the PDF was read confidently? | Detect that subtotal plus tax does not equal total and block approval. | `total_mismatch` matched; approval remains unavailable. |
| `invalid_date_order` | Can a due date before the invoice date pass? | Flag the invalid date order and block approval. | `invalid_date_order` matched. |
| `unsupported_currency` | Can an unsupported currency reach approval? | Preserve the extracted currency, flag it as unsupported, and block approval. | `unsupported_currency` matched. |
| `zero_total` | Can a zero-value invoice be treated as a normal payable invoice? | Flag the invalid total and block approval. | `invalid_total` matched. |

## Cross-Document Duplicate

| Scenario | Business question | Expected system behavior | Observed result |
| --- | --- | --- | --- |
| `duplicate_original` | Is the first occurrence falsely called a duplicate? | Store the first vendor and invoice-number pair without a duplicate blocker. | First invoice remained clear and waited for review. |
| `duplicate_copy` | Is the second matching invoice stopped? | Detect the stored pair, show a duplicate reason, and block approval in UI and API. | Second invoice received `duplicate_invoice`; approval was blocked. |

The static fixture file does not assign a duplicate code to either PDF because duplicate status
cannot be determined from one document alone. The stateful application run supplies the required
cross-document evidence.

## OCR And Layout Challenge

| Scenario | Business question | Expected system behavior | Observed result |
| --- | --- | --- | --- |
| `low_contrast_scan` | Can faded source text be read without fabricated fields? | Extract the expected values or expose a failure; never infer missing content. | All evaluated fields matched; no blocker. |
| `rotated_invoice` | Can a rotated page still be processed? | Read and normalize the rotated invoice, then wait for review. | All evaluated fields matched; no blocker. |
| `multi_page_invoice` | Can invoice data be found across more than one page? | Process all pages and return one reviewable invoice record. | All evaluated fields matched; no blocker. |

## Evidence Boundary

The results above come from committed synthetic PDFs processed through a real OCR and extraction
provider configuration. They show controlled regression behavior on this dataset. They do not
establish production accuracy, business impact, or robustness across unknown customer data.

Detailed iterations, latency observations, and failure corrections are recorded in
[invoice scenario evidence](docs/invoice-scenarios-v1-evidence.md).
