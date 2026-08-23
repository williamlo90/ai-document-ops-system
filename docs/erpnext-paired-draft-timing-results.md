# ERPNext Paired Draft Timing Results

- Run date: 23 August 2026
- Protocol: [ERPNext Controlled Benchmark Protocol v1.2](erpnext-benchmark-protocol.md)
- Evidence: [machine-readable timing result](evidence/erpnext-paired-draft-timing-v2.json)

## Result

One operator reran the six draft-eligible synthetic invoices through direct ERPNext entry and the
application-assisted workflow. Both methods ended when the ERPNext Purchase Invoice Draft had been
checked against the source invoice.

| Metric              | Manual entry | Application-assisted |
| ------------------- | -----------: | -------------------: |
| Paired draft cases  |            6 |                    6 |
| Median elapsed time |  153 seconds |           49 seconds |
| Expected outcomes   |         9/10 |                10/10 |
| Outcome failures    |            1 |                    0 |

The application-assisted median was **68.0% lower** for these six paired draft cases.

## Per-case timing

| Case   | Scenario             | Manual | Application-assisted |
| ------ | -------------------- | -----: | -------------------: |
| ERP-01 | Standard USD invoice |   145s |                  48s |
| ERP-02 | No-tax USD invoice   |   150s |                  50s |
| ERP-03 | EUR invoice          |   255s |                  46s |
| ERP-07 | Original invoice     |   156s |                  45s |
| ERP-09 | Low-contrast invoice |   182s |                  51s |
| ERP-10 | Rotated invoice      |   143s |                  55s |

Sorted manual times were `143, 145, 150, 156, 182, 255`; the median was
`(150 + 156) / 2 = 153` seconds. Sorted application-assisted times were
`45, 46, 48, 50, 51, 55`; the median was `(48 + 50) / 2 = 49` seconds.

```text
median reduction = (153 - 49) / 153 = 67.9739% ~= 68.0%
```

## Retained blocker outcomes

The four blocker outcomes retain the previously recorded values. The operator reran these cases and
reported the same outcomes with timing differences of approximately zero to two seconds, but did
not record exact replacement timings. These elapsed values do not enter the paired draft median.

| Case   | Scenario                     | Manual             | Application-assisted | Manual | Application-assisted |
| ------ | ---------------------------- | ------------------ | -------------------- | -----: | -------------------: |
| ERP-04 | Supplier missing             | Safe blocker       | Safe blocker         |    75s |                  30s |
| ERP-05 | Total mismatch               | Safe blocker       | Safe blocker         |    32s |                  27s |
| ERP-06 | Due date before invoice date | Manual entry error | Safe blocker         |    68s |                  27s |
| ERP-08 | Duplicate invoice            | Safe blocker       | Safe blocker         |    76s |                  40s |

Across the combined 10-case outcome record, direct manual entry produced the expected outcome in
**9/10 cases** and the application-assisted workflow did so in **10/10 cases**. No duplicate draft
or unsafe non-draft accounting state was created.

## Measurement boundary

The manual workflow included opening the source, entering the invoice in ERPNext, checking the
entered values against the source, saving the draft, and verifying it. The source check took
approximately 10 to 15 seconds per case and was included in elapsed time, but was not measured as a
separate interval.

The timing result covers one operator, six known generated invoices, and a local ERPNext sandbox.
The 10-case outcome rate combines those six corrected reruns with four retained blocker
observations; it is not a single same-session 20-trial run. Active human time and unattended wait
were not recorded separately. The result is not evidence of production savings, multi-user
performance, or customer impact.
