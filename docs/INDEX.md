# Documentation and Evidence

Start with the product narrative, then follow the dated reports for scope and reproducibility.

## Product and Engineering

- [Engineering case study](PORTFOLIO_CASE_STUDY.md)
- [Architecture](ARCHITECTURE.md)
- [Runbook](RUNBOOK.md)
- [Docker demo and recovery](docker_profile.md)
- [Product requirements](PRD.md)
- [Roadmap](ROADMAP.md)
- [ERPNext environment](erpnext-environment.md) and [integration boundary](erpnext-integration-design.md)

## Current Invoice-to-ERP Evidence

| Area                                                 | Record                                                                                                   |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Acceptance and measurement contract                  | [Contract](evidence/invoice-review-v2/CONTRACT.md) and [claim map](evidence/invoice-review-v2/CLAIMS.md) |
| Whole-invoice quality, matching and posting          | [Phase 6 evaluation](evidence/invoice-review-v2/PHASE-6.md)                                              |
| Frozen quality results                               | [Quality holdout](evidence/invoice-review-v2/quality-holdout/report.json)                                |
| Discrepancy checks and authorized dispositions       | [Discrepancy report](evidence/invoice-review-v2/discrepancies/report.json)                               |
| Independent ERP verification and restart replay      | [Posting report](evidence/invoice-review-v2/posting/report.json)                                         |
| Dated supplier/rule revisions                        | [Revision replay](evidence/invoice-review-v2/replay/report.json)                                         |
| Packaged runtime, response loss and storage recovery | [Phase 7 release](evidence/invoice-review-v2/PHASE-7.md)                                                 |
| Cloud scope decision                                 | [Phase 8](evidence/invoice-review-v2/PHASE-8.md)                                                         |
| Six-invoice draft timing, separate cohort            | [Paired draft benchmark](erpnext-paired-draft-timing-results.md)                                         |

## Security and Deployment

- [Security posture](security/SECURITY_POSTURE.md)
- [Provider data boundary](security/provider-data-boundary.md)
- [Supply-chain controls and lock regeneration](security/supply-chain.md)
- [Historical temporary Azure validation](azure-live-validation.md)

## Product Tour

- [Captioned demo](assets/demo/invoice-review-demo.mp4)
- [Screenshots](assets/screenshots/)
- [Demo script](demo-script.md)

Reports describe their recorded revision and test population. Historical header/draft results,
current whole-invoice evaluation, local ERP posting and temporary Azure intake are separate scopes.
