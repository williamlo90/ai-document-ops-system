# Project 4 Handoff

Project 4 should start from Project 3.5, not from Project 3 alone.

## Why

Project 3 added the copilot.

Project 3.5 added the reliability loop around the copilot.

Project 4 should preserve both.

## What Project 4 Can Add

Possible Project 4 direction:

```text
Autonomous Backoffice AI
```

The system can expand from document operations into a broader workflow:

- intake documents
- classify work type
- extract and validate data
- recommend next action
- draft outbound messages or records
- execute selected tools with confirmation
- route low-confidence cases to human review
- record traces and AgentOps metrics

## Guardrails To Keep

- Project 2 workflow enforcement
- Project 3 tool contracts
- Project 3 controlled execution
- Project 3.5 evaluation engine
- Project 3.5 scenario dataset versioning
- Project 3.5 prompt version comparison
- Project 3.5 regression comparison
- Project 3.5 AgentOps dashboard

## What Not To Do

- do not jump to unrestricted autonomy
- do not remove confirmation for risky tools
- do not hide failures
- do not invent business metrics without traces
- do not claim production SaaS before deployment, auth, billing, tenancy, monitoring, backups, and real users exist

## First Project 4 Question

```text
What broader back-office workflow can create business value while still being measurable by Project 3.5 AgentOps?
```

