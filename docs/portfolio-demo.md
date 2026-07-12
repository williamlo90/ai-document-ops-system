# Portfolio Demo - Project 4

Project 4 demonstrates bounded autonomous back-office workflow orchestration on top of the document operations platform and local reliability evidence layer.

## Demo Narrative

1. Show the inherited document workflow.
2. Open the uploader flow and upload a sample invoice.
3. Show that processing sends the invoice to human review instead of auto-approval.
4. Switch to reviewer flow and inspect the extracted invoice data, issues, and source document.
5. Approve or reject from the reviewer decision screen.
6. Show invoice history so the business audit trail is clear.
7. Show controlled export readiness only after approval.
8. Briefly open technical evidence: reliability summary, scenario checks, and run traces.
9. Show `docs/docker_profile.md` and `docs/aws_deployment.md`.
10. Close with honest production gaps.

## Best Portfolio Claim

Use this wording:

> A production-shaped autonomous back-office AI platform with bounded planning, human approval gates, controlled execution, repeatable reliability checks, Docker deployment, CI quality gates, and an honest cloud-readiness path.

## Market Value

This project is valuable because organizations need more than an agent that can answer.

They need a way to inspect:

- whether the AI chose the expected action
- whether unsafe behavior was blocked
- whether low-confidence situations escalated
- whether failures are recurring
- whether a planning or policy change regressed behavior
- whether the system has enough trace evidence to support trust
- whether autonomous work plans stay within approval and policy boundaries

That pattern is relevant to agentic back-office workflows, document operations, finance review, support automation, compliance queues, and internal AI platform teams.

## Do Not Claim

- hosted production SaaS
- enterprise-grade monitoring
- real user traffic
- full LLM judge evaluation
- autonomous prompt optimization
- perfect confidence calibration
- production incident alerting
- production Kubernetes deployment
- complete multi-tenant billing platform
