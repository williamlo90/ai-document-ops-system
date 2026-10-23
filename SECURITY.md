# Security Policy

## Supported versions

Security fixes target the latest code on `main`. Earlier phase checkpoints and archived
releases are retained for reference and are not maintained security branches.

## Report a vulnerability privately

Use GitHub's [Report a vulnerability](https://github.com/williamlo90/ai-document-ops-system/security/advisories/new)
form to send a private report to the repository maintainer. You can also find it under
**Security → Advisories → Report a vulnerability**.

Please include:

- The affected commit, component and configuration.
- Reproduction steps or a minimal proof of concept using synthetic data.
- Expected behavior, observed behavior and the potential impact.
- A suggested fix, if available.

Do not publish exploit details in public issues or pull requests before a fix is coordinated.
Never include live API keys, access tokens, real invoices or personal information in a report.
If a credential is exposed, revoke or rotate it immediately; removing it from Git is insufficient.

Reports are reviewed by the project maintainer. Follow-up, remediation and any public advisory
are coordinated through the private report; there is no guaranteed response or remediation SLA.
Ordinary bugs and feature requests can use public GitHub issues.

## Security checks

Dependabot alerts monitor vulnerable dependencies. GitHub secret scanning and push protection
check for supported credential patterns. CodeQL default setup analyzes the repository's supported
languages. CI also runs dependency audits, a full-history secret scan and container security checks.

Dependency updates are reviewed manually on `main`. Automated checks support review and do not
establish that the application is free of vulnerabilities.

## Deployment scope

The documented validation covers synthetic documents and a local ERPNext sandbox. Production
deployment and real customer data require separate security and operational validation.
The application supports approval-gated ERPNext drafts; ERP submission and payment execution
are outside this version's integration boundary.
See the [security posture](docs/security/SECURITY_POSTURE.md) and
[runbook](docs/RUNBOOK.md) for controls and deployment prerequisites.
