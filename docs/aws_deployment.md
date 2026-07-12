# AWS Production-Shaped Deployment

This is the target operating model, not evidence that the application is already
hosted or production certified.

## Recommended topology

- ECR stores one immutable API/worker image.
- ECS Fargate runs separate API and worker services in private subnets.
- An ALB terminates HTTPS and routes only to the API service.
- RDS PostgreSQL (or Supabase) holds relational state after the PostgreSQL
  repository migration is complete.
- Cloudflare R2 holds private documents through the S3-compatible adapter.
- Secrets Manager injects credentials at task startup.
- CloudWatch receives JSON stdout logs, alarms on unhealthy tasks and 5xx rates,
  and scrapes or receives metrics through an OpenTelemetry/Prometheus collector.

Do not deploy the current SQLite shared-volume topology across multiple ECS tasks.
SQLite remains suitable for one-node demos only.

## Container contract

- `GET /health` is the liveness check.
- `GET /ready` is the dependency/readiness check and returns `503` when draining
  or when database/storage checks fail.
- `GET /internal/metrics` exposes Prometheus text. Restrict it to the monitoring
  security group or collector sidecar; do not expose it through the public ALB.
- Requests receive `X-Request-ID` and `X-Trace-ID`. Incoming W3C `traceparent`
  trace IDs are preserved.
- API and worker accept `SIGTERM`; allow at least 35 seconds before forced stop.

## Deployment sequence

1. Build once, scan the image, and push an immutable SHA tag to ECR.
2. Run migrations as a one-off ECS task before updating services.
3. Update the worker service, then the API service with ECS deployment rollback enabled.
4. Wait for `/ready` and run upload/review/export smoke checks.
5. Roll back to the prior image if readiness, 5xx, queue age, or provider failure
   alarms breach their thresholds.

The production Compose override is useful for validating hardening and the
CloudWatch log driver on a VM:

```bash
DOCINTEL_IMAGE=account.dkr.ecr.region.amazonaws.com/docintel:sha \
docker compose -f docker-compose.yml -f docker-compose.production.yml config
```

ECS should normally be defined in Terraform/CDK rather than deployed from Compose.

## Minimum alarms

- ALB/API 5xx rate above 2% for 5 minutes
- no healthy API tasks
- worker has no healthy tasks
- oldest queued job exceeds 10 minutes
- dead-letter/failed jobs increase
- RDS free storage or connections cross safe thresholds
- provider failure rate and p95 latency exceed the agreed SLO

## Rollback and recovery

Keep the prior ECR image tag and migration compatibility for one release. Database
backups require encryption, separate retention, and a quarterly restore drill.
Record restore duration and integrity/smoke-check results as release evidence.
