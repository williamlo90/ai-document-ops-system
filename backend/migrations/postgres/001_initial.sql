CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS application_records (
    record_type TEXT NOT NULL,
    id UUID NOT NULL,
    workspace_id TEXT NOT NULL,
    parent_id UUID,
    status TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (record_type, id)
);

CREATE INDEX IF NOT EXISTS idx_application_records_workspace
    ON application_records (workspace_id, record_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_application_records_parent
    ON application_records (record_type, parent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_application_records_status
    ON application_records (workspace_id, record_type, status, created_at);

CREATE TABLE IF NOT EXISTS processing_job_claims (
    job_id UUID PRIMARY KEY,
    worker_id TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    workspace_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    response_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, operation, idempotency_key)
);
