# Controlled Azure Live Validation

The production-shaped Azure profile was validated in Southeast Asia during a temporary, controlled
run on 2026-09-27/28. This was deployment and integration evidence, not permanent production
hosting or customer-traffic evidence.

## Validated profile

- Azure Container Apps hosted the FastAPI API, queue worker, and one-off migration job.
- Azure Database for PostgreSQL Flexible Server held relational workflow state.
- private Azure Blob Storage held document content through Managed Identity.
- Azure Service Bus carried asynchronous document-processing work.
- Azure Functions and Event Grid were deployed for external-drop ingestion.
- Azure Container Registry served one immutable application image.
- Key Vault references and workload Managed Identities supplied secrets and scoped data-plane access.
- Log Analytics and Application Insights received platform diagnostics.

The application image maps to Git revision
`cac929f134542b27b640265dbc51d80a691d7125` and registry manifest digest
`sha256:da4859808e048621cc986109fb8c59afceb9f8fdacc6ced5af1f4af67b9e76f2`.
The ClamAV 1.5.4 sidecar was also digest-pinned. Trivy 0.74.0 reported no fixed HIGH or CRITICAL
findings in either deployed image.

## Observed results

- the PostgreSQL migration job completed successfully;
- API liveness and readiness returned HTTP 200 on a healthy revision;
- a synthetic PDF passed ClamAV, private Blob persistence, Service Bus delivery, and mock-provider
  worker processing, progressing from `queued` to `needs_review`;
- the queue remained active with zero dead-letter messages after the successful path;
- an exact EICAR test payload sent through the same ClamAV INSTREAM protocol returned
  `Eicar-Test-Signature FOUND`;
- temporary operator access used for the test was removed before teardown;
- the validation resource group was deleted, and a subscription-level project-tag query returned
  zero remaining resources.

## Claim boundary

The run used deterministic mock OCR/extraction providers so it did not spend external AI-provider
credits or validate Azure-hosted real-provider accuracy. It did not establish sustained load,
multi-region availability, disaster recovery, customer tenancy, or continuous production operation.
Replay, forced worker interruption, intentional dead-letter, and cross-service trace demonstrations
remain separate follow-up evidence items.
