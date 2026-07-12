# Release Notes - Project 3.5 Portfolio Release

Status: portfolio-ready local AgentOps reliability release.

Completed:

- Project 3.5 created from the Project 3 release-locked baseline.
- PRD, roadmap, architecture, evaluation plan, and dataset docs established.
- AgentOps evaluation engine added over Project 3 copilot traces.
- Reliability metrics added for tool selection, unsafe prevention, completion, escalation, confidence, tool calls, failure taxonomy, prompt versions, and regression comparison.
- AgentOps API added under `/agentops`.
- Versioned scenario dataset added at `examples/agentops/scenarios_v1.json`.
- Scenario evaluator added for run-vs-scenario comparison.
- Local AgentOps dashboard added at `/ui/agentops`.
- Portfolio story, demo script, reliability report, and Project 4 handoff notes added.

Verification:

- Black OK.
- Ruff OK.
- `docker compose config --quiet` OK.
- Full test suite: 271 tests OK.
- Real-provider tests: 2 skipped because credentials are not set.

Known limitations:

- This is local AgentOps, not hosted production monitoring.
- Current prompt version is deterministic.
- Average latency remains a placeholder.
- Token and real cost tracking require a future LLM planner.
- Regression comparison is run-window based, not persisted snapshot based.
- Scenario replay does not yet auto-provision every workflow state.
- Project 4 is still needed for broader autonomous back-office workflows.

