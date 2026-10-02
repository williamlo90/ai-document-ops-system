# AI Document Production-Grade Testing Documentation

Status: draft baseline and results template  
Created: 2026-10-02  
Last updated: 2026-10-02  
Repository: `ai-document-ops-system`  
Related implementation plan: local ignored `_local_docs/production-grade/production-grade-testing-todo.md`  

## 1. Purpose

This document is the consolidated engineering record for production-grade testing of AI Document
Ops. It combines:

1. reliability, security, concurrency, and release evidence that existed before the new
   production-grade testing patch; and
2. the live capacity, recovery, queue, alerting, tracing, and autoscaling evidence that will be
   produced by implementing the local production-grade testing TODO.

This is an evidence document, not a certification. A test is marked **Passed** only when an
identified revision, environment, procedure, result artifact, and acceptance threshold exist.

## 2. Status Vocabulary

| Status | Meaning |
| --- | --- |
| Passed | Executed evidence satisfies the frozen acceptance threshold. |
| Failed | Executed evidence violates one or more acceptance thresholds. |
| Partial | Some behavior is proven, but the complete target scenario was not executed. |
| Locally validated | Proven in deterministic unit, integration, emulator, or container tests only. |
| Live validated | Proven against the disposable Azure deployment. |
| Planned | Defined in the TODO but not yet implemented or executed. |
| Not applicable | Explicitly excluded with a documented reason. |

## 3. Executive Summary

### Current baseline

The system already has a strong local and release-engineering foundation:

- retry and idempotency behavior is covered by deterministic tests;
- job claim, lease, and concurrent mutation behavior is tested;
- queue poison-message, retry-limit, and dead-letter decisions are covered locally and through the
  Service Bus adapter contract;
- stale leases and worker interruption recovery logic are tested;
- health/readiness behavior under dependency failure is tested;
- structured logs, request IDs, trace IDs, basic metrics, and operation events are tested;
- the release image is built immutably, exercised in API/worker/migration modes, and vulnerability
  scanned in CI;
- a controlled Azure deployment previously validated PostgreSQL migration, API health/readiness,
  ClamAV, private Blob persistence, Service Bus delivery, worker processing, and teardown.

### Current limitation

The following evidence does not yet exist and must remain **Planned** until the new TODO is
implemented and executed:

- sustained load and soak behavior with frozen latency/resource thresholds;
- realistic end-to-end concurrent upload/approval/export evidence in Azure;
- real worker termination and lease recovery in Azure;
- live duplicate replay, poison-message DLQ, and safe replay evidence;
- timeout-after-external-success reconciliation evidence;
- real alert delivery to a human receiver;
- automated API-to-queue-to-worker trace correlation proof;
- queue-driven worker scale-out and scale-in evidence.

### Current verdict

**Foundation status:** strong production-oriented test foundation.  
**Live production-grade test status:** incomplete.  
**Permitted claim today:** production-shaped Azure deployment with controlled integration
validation.  
**Claim blocked today:** production-grade reliability, proven scalability, highly available, or
production-ready.

## 4. System and Evidence Boundary

### Included

- FastAPI API and React workflow;
- PostgreSQL persistence and migrations;
- private document storage;
- asynchronous processing queue and worker;
- review, approval, export, and integration idempotency;
- health/readiness and graceful runtime behavior;
- container and infrastructure security controls;
- Azure Container Apps, Blob Storage, Service Bus, PostgreSQL Flexible Server, Key Vault, Managed
  Identity, Log Analytics, Application Insights, Event Grid, and Azure Functions;
- synthetic workload and mock AI-provider behavior.

### Excluded unless separately stated

- real customer or production data;
- real-provider throughput, accuracy, rate limits, and cost;
- multi-region availability;
- disaster recovery;
- penetration testing;
- long-term production operation;
- contractual SLA/SLO evidence;
- full private-network or zero-trust certification.

## 5. Evidence Already Available Before the New Patch

The rows below describe the baseline as of repository revision `b156e03`. “Locally validated” does
not imply live Azure validation.

| Area | Status | What is already demonstrated | Primary evidence |
| --- | --- | --- | --- |
| Retry and job idempotency | Locally validated | Retryable jobs use bounded attempts and guarded state transitions; duplicate queue delivery does not create a second logical processing effect. | `backend/app/tests/test_processing_queue.py`, worker/repository tests |
| Export idempotency | Locally validated | Repeated export commands are protected by idempotency keys and conflict rules. | export service/API and transaction-boundary tests |
| Worker claim concurrency | Locally validated | Atomic claim and lease semantics prevent two workers from owning the same processable job. | `backend/app/tests/test_postgres_persistence.py`, `test_transaction_boundaries.py` |
| Lease recovery | Locally validated | Expired/stale lease paths can be reclaimed and processing can resume. | job/repository/processing queue tests |
| Queue duplicate handling | Locally validated | A duplicate message for terminal, future-retry, or already-leased work is safely completed. | `backend/app/tests/test_processing_queue.py` |
| Poison-message handling | Locally validated | Invalid envelope and rejected processing paths choose dead-letter disposition. | `backend/app/tests/test_processing_queue.py`, `test_azure_service_bus.py` |
| Queue transport contract | Locally validated | Service Bus publish/receive, correlation ID, lock renewal, complete, abandon, and dead-letter calls are covered. | `backend/app/tests/test_azure_service_bus.py` |
| Database concurrency | Locally validated | PostgreSQL API/worker state sharing and atomic job claim contracts are exercised. | `backend/app/tests/test_postgres_persistence.py` |
| Upload and workflow concurrency smoke | Locally validated | Concurrent upload/process requests, pagination isolation, and concurrent approval responses have a runnable smoke harness. | `scripts/load_workflows.py` |
| Read concurrency smoke | Locally validated | A dependency-free concurrent read smoke reports response statuses, median, p95, and maximum latency. | `scripts/load_smoke.py` |
| Dependency readiness | Locally validated | Readiness reports failed database/storage dependencies and queue degradation separately. | runtime observability/release tests |
| Container runtime recovery | Locally validated | API, worker, and migration modes, read-only filesystems, PostgreSQL outage behavior, and graceful termination are exercised. | `scripts/container_runtime_smoke.py`, CI `container-security` job |
| Structured application logs | Locally validated | JSON logs include timestamp, level, logger, event, request ID, trace ID, path, status, and duration where relevant. | `backend/app/core/observability.py`, `test_runtime_observability.py` |
| Basic HTTP metrics | Locally validated | Per-route/status request counters and duration sums are exposed through the protected metrics endpoint. | `backend/app/core/observability.py`, `/internal/metrics` tests |
| Trace identifier propagation | Partial | API accepts/creates trace IDs and Service Bus messages carry the trace ID into worker operation logs. Automated complete-chain proof is not yet present. | observability middleware, processing message, Service Bus adapter, queue worker |
| Infrastructure as Code | Passed | Azure Bicep compiles and generated ARM is checked for expected security, identity, immutable-image, tagging, and teardown contracts. | CI `azure-infrastructure`, `scripts/validate_azure_iac.py` |
| Secret scanning | Passed | Full Git history is scanned with redaction in CI. | CI `secret-scan` |
| Dependency and code quality | Passed | Locked installs, dependency audit, formatting, lint, type checking, coverage, and complexity gates pass on final baseline. | final CI run `36339370216` |
| Container vulnerability scan | Passed | The candidate image passed the configured fixed HIGH/CRITICAL vulnerability gate. | final CI `container-security`; controlled Azure validation record |
| Azure database migration | Live validated | One-off PostgreSQL migration completed in the temporary Azure environment. | `docs/azure-live-validation.md` |
| Azure health/readiness | Live validated | Deployed API liveness and readiness returned HTTP 200 on the healthy revision. | `docs/azure-live-validation.md` |
| Azure synthetic processing path | Live validated | A synthetic PDF passed ClamAV, private Blob persistence, Service Bus delivery, mock-provider worker processing, and reached `needs_review`. | `docs/azure-live-validation.md` |
| Malware boundary | Live validated | Exact EICAR payload was detected through the deployed ClamAV INSTREAM path. | `docs/azure-live-validation.md` |
| Azure teardown | Live validated | Temporary operator access was removed, the validation resource group was deleted, and tagged active project resource count became zero. | `docs/azure-live-validation.md`, ignored teardown evidence |

## 6. New Production-Grade Test Matrix

All rows begin as **Planned**. Update them only after execution evidence exists.

| ID | Priority | Test | Current status | Mandatory acceptance summary | Result artifact |
| --- | --- | --- | --- | --- | --- |
| PG-01 | P1 | Sustained load and soak | Planned | 60-minute mixed workload; >=99.5% expected-response availability; 5xx <0.5%; latency/resource thresholds pass | TBD |
| PG-02 | P1 | End-to-end concurrency | Planned | Concurrent upload/approval/export has no lost update, duplicate effect, or inconsistent state | TBD |
| PG-03 | P1 | Live worker recovery | Planned | Claimed job survives worker termination and converges exactly once within two lease windows | TBD |
| PG-04 | P1 | Live retry and idempotency | Planned | Duplicate queue message, duplicate export call, and ambiguous external success each produce one logical effect | TBD |
| PG-05 | P1 | Live queue backlog, DLQ, and replay | Planned | Backlog drains; poison messages are classified in DLQ; corrected replay converges once | TBD |
| PG-06 | P1 | Alert delivery and trace correlation | Planned | Selected fault opens Azure alert, sends notification, and one trace ID connects API, queue, worker, and final state | TBD |
| PG-07 | P1 | Worker autoscaling | Planned | Backlog causes >=2 replicas, work remains consistent, backlog reaches zero, worker returns to zero | TBD |

## 7. Frozen Provisional Acceptance Thresholds

These are the initial portfolio validation thresholds. Freeze or explicitly revise them before the
live run; do not lower them after observing a failure.

| Signal | Threshold |
| --- | --- |
| Steady-load availability | >= 99.5% expected successful responses |
| Unexpected HTTP 5xx | < 0.5% |
| Read latency | p50 <= 500 ms; p95 <= 1.5 s; p99 <= 3 s |
| Upload acknowledgement | p50 <= 1.5 s; p95 <= 4 s; p99 <= 8 s |
| Approval/export mutation | p95 <= 2 s, excluding expected conflicts |
| Data loss | 0 |
| Duplicate processing/export/external effect | 0 |
| Queue burst drain | <= 15 minutes |
| Interrupted-work recovery | <= 2 configured lease windows |
| Worker autoscaling | reaches >=2 replicas and returns to 0 |
| CPU and memory | <85% p95; no OOM/restart loop |
| Database pool | no connection exhaustion or pool-timeout transaction failure |
| Alert | alert state observed and notification receipt confirmed |
| Trace | API, queue publish, worker, and terminal evidence share one trace ID |

## 8. Test Environment Record

Fill this section immediately before deployment.

| Field | Value |
| --- | --- |
| Validation run ID | TBD |
| Git revision | TBD |
| OCI image digest | TBD |
| Execution date/time (WIB) | TBD |
| Azure region | Southeast Asia, pending preflight confirmation |
| Runtime duration | TBD |
| API replica range | 1-1 |
| Worker replica range | 0-3 |
| PostgreSQL profile | Validation SKU; exact observed configuration TBD |
| OCR provider | Mock/deterministic |
| Extraction provider | Mock/deterministic |
| Test data | Synthetic PDFs only |
| Alert receiver | Configured locally; never record address here |
| Teardown deadline | TBD |

## 9. Workload Record

| Stage | Planned workload | Actual workload | Status |
| --- | --- | --- | --- |
| Warm-up | 5 minutes | TBD | Planned |
| Read baseline | 10 concurrent users, 10 minutes | TBD | Planned |
| Workflow steady state | 2 uploads/minute, 10 users, 60 minutes | TBD | Planned |
| Mutation burst | 20 concurrent approval/export attempts | TBD | Planned |
| Queue burst | 60 documents in <=3 minutes | TBD | Planned |
| Recovery | 10-20 queued documents | TBD | Planned |
| Cool-down | backlog zero and worker zero | TBD | Planned |

## 10. Detailed Result Template

Copy this subsection once for every `PG-xx` scenario.

### PG-XX — Test name

**Status:** Planned  
**Started:** TBD  
**Completed:** TBD  
**Source revision/image:** TBD  
**Scenario trace/run ID:** TBD

#### Objective

TBD.

#### Preconditions

- TBD.

#### Procedure

1. TBD.

#### Frozen acceptance criteria

- TBD.

#### Observed result

- Request/operation count: TBD
- Success/error distribution: TBD
- Latency p50/p90/p95/p99: TBD
- Throughput: TBD
- CPU/RAM/restarts: TBD
- PostgreSQL connections/CPU: TBD
- Queue active/DLQ counts: TBD
- Replica timeline: TBD
- Invariant result: TBD

#### Evidence

- Sanitized JSON: TBD
- Sanitized Markdown summary: TBD
- Log query/result: TBD
- Azure metric export: TBD
- CI/run URL: TBD

#### Verdict

TBD. State the failed threshold directly if the result is not Passed.

#### Follow-up

TBD. Distinguish required remediation from optional optimization.

## 11. Reliability Result Summary

Complete after all scenarios.

| Reliability property | Evidence | Verdict |
| --- | --- | --- |
| Capacity under target load | PG-01 | Planned |
| Concurrent workflow consistency | PG-02 | Planned |
| Worker interruption recovery | PG-03 | Planned |
| Duplicate/retry convergence | PG-04 | Planned |
| Poison-message isolation | PG-05 | Planned |
| DLQ replay safety | PG-05 | Planned |
| Alert detection and notification | PG-06 | Planned |
| Cross-service traceability | PG-06 | Planned |
| Queue-driven scale-out/scale-in | PG-07 | Planned |

## 12. Security Result Summary

### Existing controls

- managed identities and scoped RBAC;
- Key Vault references rather than committed secret values;
- private Blob containers;
- Storage shared-key access disabled;
- Service Bus local authentication disabled;
- ACR admin account disabled;
- TLS/HTTPS controls;
- fail-closed ClamAV scanning;
- immutable image digest;
- Git secret scan and container vulnerability scan;
- synthetic-only validation data;
- guarded resource-group teardown.

### Known limits

- several Azure services still use public network endpoints;
- PostgreSQL validation profile uses password authentication;
- full VNet/private endpoint isolation is not validated;
- Key Vault purge protection and enterprise retention posture are not claimed;
- no penetration test or customer-data security assessment is included;
- production user identity lifecycle is outside this validation.

## 13. Observability and Alert Evidence

Fill after PG-06.

| Evidence | Result |
| --- | --- |
| API request ID visible | TBD |
| API trace ID visible | TBD |
| Queue publish event with same trace ID | TBD |
| Service Bus correlation ID | TBD |
| Worker event with same trace ID | TBD |
| Terminal state/audit evidence | TBD |
| Azure alert opened | TBD |
| Human notification received | TBD |
| Alert resolved after recovery | TBD |

Do not describe correlated log events as distributed tracing spans unless actual span telemetry is
implemented.

## 14. Data Integrity and Duplicate-Effect Evidence

| Invariant | Expected | Observed | Verdict |
| --- | ---: | ---: | --- |
| Uploaded synthetic documents accounted for | TBD | TBD | Planned |
| Durable jobs accounted for | TBD | TBD | Planned |
| One logical processing result per job | 100% | TBD | Planned |
| Duplicate processing effects | 0 | TBD | Planned |
| Duplicate export effects | 0 | TBD | Planned |
| Duplicate external drafts | 0 | TBD | Planned |
| Lost approval decisions | 0 | TBD | Planned |
| Documents in conflicting active batches | 0 | TBD | Planned |
| Unexpected DLQ items | 0 | TBD | Planned |
| Expected poison-message DLQ items | scenario-defined | TBD | Planned |

## 15. Failure and Recovery Timeline

| Timestamp (WIB) | Event | Expected behavior | Observed behavior | Evidence |
| --- | --- | --- | --- | --- |
| TBD | Worker claim-and-exit | Lease remains until stale, then safe reclaim | TBD | TBD |
| TBD | Worker restart during backlog | Message/job converges once | TBD | TBD |
| TBD | Duplicate queue replay | Safe completion, no duplicate effect | TBD | TBD |
| TBD | Poison envelope | DLQ with expected reason | TBD | TBD |
| TBD | Safe DLQ replay | One corrected result | TBD | TBD |
| TBD | External success/client timeout | Outcome unknown, then one reconciled result | TBD | TBD |
| TBD | Alert-triggering fault | Alert and notification | TBD | TBD |

## 16. Cost and Teardown Record

| Field | Result |
| --- | --- |
| Deployment start | TBD |
| Test completion | TBD |
| Teardown start | TBD |
| Resource group deletion confirmed | TBD |
| Tagged active project resources after teardown | TBD |
| Matching resource locks after teardown | TBD |
| Expected soft-deleted records | TBD |
| Posted Azure cost | Review later after Cost Management posts usage |

Budget alerts are notifications, not automatic spending stops. The authoritative cleanup evidence is
resource-group absence plus a subscription-level tagged-resource inventory.

## 17. Final Claim Template

Use only if every mandatory scenario passes:

> The production-shaped Azure profile passed a controlled production-readiness validation using
> synthetic data and deterministic AI providers. The validation covered sustained load, concurrent
> workflow mutations, worker interruption recovery, retry/idempotency, Service Bus backlog and
> dead-letter handling, Azure Monitor alert delivery, cross-service trace correlation, and
> queue-driven worker autoscaling. The result does not represent customer production traffic,
> real-provider capacity, multi-region availability, or disaster-recovery certification.

If one or more mandatory scenarios fail, replace “passed” with an exact partial statement and list
the blocked claim.

## 18. Final Verdict Template

**Overall status:** TBD  
**Passed scenarios:** TBD  
**Failed scenarios:** TBD  
**Blocked scenarios:** TBD  
**Residual risks:** TBD  
**Required remediation:** TBD  
**Optional improvements:** TBD  
**Permitted portfolio claim:** TBD  
**Claims still prohibited:** TBD

## 19. Evidence Inventory

Public/tracked evidence:

- `docs/azure-live-validation.md`
- final sanitized production-readiness note: TBD
- CI run: TBD

Local/ignored evidence:

- `_local_docs/production-grade/production-grade-testing-todo.md`
- `_local_docs/production-grade/production-grade-documentation-ai-document.md`
- `_local_docs/azure/production-validation/<run-id>/manifest.json`: TBD
- `_local_docs/azure/production-validation/<run-id>/results.json`: TBD
- `_local_docs/azure/production-validation/<run-id>/summary.md`: TBD
- sanitized metric/log exports: TBD
- teardown evidence: TBD

Never store secret values, access tokens, subscription/tenant identifiers, personal email addresses,
payment details, real invoice contents, or customer identifiers in these artifacts.

## 20. Change Log

| Date | Change |
| --- | --- |
| 2026-10-02 | Created baseline documentation from existing local, CI, container, and controlled Azure evidence; added templates for PG-01 through PG-07. |
