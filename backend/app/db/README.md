# Persistence Strategy

Status: Step 3 foundation

Project 2 targets PostgreSQL for production-shaped deployments while preserving SQLite and in-memory repositories for local development and tests.

## Runtime Modes

- `memory`: fast unit-test mode; no durable state.
- `sqlite`: local/simple durable mode; current default for Docker-style local demos.
- `postgres`: production target; `DATABASE_URL` is configured now, adapter implementation comes after the schema/repository foundation is stable.

The current application still selects repository implementations through `STORAGE_BACKEND`. This name is inherited from the MVP baseline and currently means persistence backend, not document object storage backend.

Document object storage is selected separately through `DOCUMENT_STORAGE_BACKEND`.

## Repository Boundary

Services must continue to depend on repository protocols, not concrete database clients:

- `DocumentRepository`
- `JobRepository`
- `AuditRepository`
- `ExtractionRepository`
- `ReviewTaskRepository`
- `BenchmarkHistoryRepository`

This keeps the service layer testable while allowing SQLite and PostgreSQL adapters to coexist.

## Postgres-Ready Schema Concerns

The first Postgres schema should account for:

- documents, including future `workspace_id`
- processing jobs, including retry and `dead_letter` states
- audit events, including actor and workspace context
- extraction snapshots
- review tasks
- benchmark/provider run history
- provider latency and estimated cost evidence

Step 3 should avoid rewriting business services. The goal is to prepare durable persistence, not to change workflow behavior.

## Migration Strategy

Selected strategy:

```text
repository SQL first
-> explicit schema files/migrations when Postgres adapter starts
-> Alembic only when schema churn or deployment workflow makes it worthwhile
```

Reason:

- the current repository layer is small and already protocol-driven
- raw SQL keeps the first productionization slice easy to inspect
- a large ORM rewrite would add risk before the queue, storage, and tenant boundaries are proven

## Deferrals

- full SQLAlchemy model rewrite
- Alembic migration chain
- connection pooling
- backup and restore procedure
- production index tuning
- cloud database deployment
