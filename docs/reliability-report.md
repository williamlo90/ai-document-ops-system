# Reliability Report - Project 3.5

Status: local portfolio reliability evaluation.

## What Was Measured

Project 3.5 measures copilot behavior from Project 3 agent run traces.

Measured dimensions:

- tool selection accuracy
- unevaluated runs
- unsafe action prevention rate
- successful completion rate
- human escalation rate
- average confidence
- average tool calls per task
- estimated cost per run
- failure counts
- recent failure trend
- prompt version comparison
- regression comparison
- scenario dataset version coverage

## Evidence Source

Evidence comes from:

- `AgentRun`
- `AgentToolCallTrace`
- `expected_tool`
- `selected_tool`
- `selection_reason`
- `confidence`
- `failure_type`
- `human_escalation_reason`
- `blocked_actions`
- `prompt_version`
- `token_usage`
- `examples/agentops/scenarios_v1.json`

## Implemented Reliability Surfaces

- evaluation engine: `app.agentops.service.AgentOpsEvaluationService`
- API: `/agentops/runs`, `/agentops/summary`, `/agentops/prompt-versions`, `/agentops/regression`, `/agentops/scenarios`
- UI: `/?technical=runs`
- scenario evaluator: `app.agentops.scenarios`
- dataset: `agentops_core` version `v1`

## Scenario Dataset V1

The first dataset includes nine scenarios:

- workflow summary
- review queue
- selected-document explanation
- next-action recommendation
- controlled processing
- approved export
- unsafe direct database edit
- cross-workspace attempt
- insufficient evidence

These scenarios cover read-only, recommendation, controlled execution, blocked action, workspace boundary, and human escalation cases.

## What Improved

Compared with Project 3, Project 3.5 adds:

- measurable tool choice
- trace inspection
- dashboard visibility
- scenario versioning
- regression comparison shape
- prompt version comparison shape
- safer portfolio language around reliability

Project 3 could say:

```text
The copilot can operate through tools.
```

Project 3.5 can say:

```text
The copilot leaves evidence that can be evaluated.
```

## Known Failures And Limits

- The dashboard is local, not hosted production monitoring.
- Current prompt version is deterministic `deterministic-v1`.
- Average latency remains a placeholder until run duration is recorded.
- Token and real cost fields remain placeholders until an LLM planner is added.
- Scenario replay validates run evidence against expected behavior, but does not yet provision every document state automatically.
- Regression comparison currently compares run windows, not persisted benchmark snapshots.
- LLM judge evaluation is intentionally out of scope for this slice.

## Project 4 Handoff

Project 4 can build more autonomous back-office behavior on top of this reliability foundation.

Before Project 4 increases autonomy, it should preserve:

- explicit tools
- role and workspace boundaries
- confirmation rules
- scenario datasets
- run traces
- prompt version tracking
- regression checks
- human escalation

The next question for Project 4 should be:

```text
Can the system handle a broader back-office workflow while keeping AgentOps visibility and safety gates intact?
```
