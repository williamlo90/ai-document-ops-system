-- Runtime schema intentionally keeps serialized payloads and ISO timestamps as
-- TEXT so the existing domain serializers remain identical across SQLite and
-- PostgreSQL. PostgreSQL-specific indexes and locking still provide the
-- production concurrency guarantees.

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL DEFAULT 'default',
    original_filename TEXT NOT NULL, storage_key TEXT NOT NULL,
    content_type TEXT NOT NULL, submitted_by TEXT NOT NULL DEFAULT 'admin',
    size_bytes BIGINT NOT NULL DEFAULT 0, status TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error_message TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL, attempt_count INTEGER NOT NULL, started_at TEXT,
    finished_at TEXT, error_message TEXT, provider_name TEXT, provider_trace_id TEXT,
    next_attempt_at TEXT, lease_token TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL, actor TEXT NOT NULL, old_status TEXT, new_status TEXT,
    payload_summary TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_tasks (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    id TEXT NOT NULL, status TEXT NOT NULL, reviewer_notes TEXT, assigned_to TEXT,
    reviewed_by TEXT, reviewed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_identities (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    vendor_identity TEXT NOT NULL, invoice_identity TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backoffice_work_items (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, idempotency_key TEXT,
    updated_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backoffice_work_item_documents (
    work_item_id TEXT NOT NULL REFERENCES backoffice_work_items(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    updated_at TEXT NOT NULL, PRIMARY KEY (work_item_id, document_id)
);
CREATE TABLE IF NOT EXISTS backoffice_task_plans (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
    work_item_id TEXT NOT NULL REFERENCES backoffice_work_items(id) ON DELETE CASCADE,
    idempotency_key TEXT, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backoffice_action_drafts (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
    work_item_id TEXT NOT NULL REFERENCES backoffice_work_items(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backoffice_approvals (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
    work_item_id TEXT NOT NULL REFERENCES backoffice_work_items(id) ON DELETE CASCADE,
    status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backoffice_policy_decisions (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
    work_item_id TEXT NOT NULL REFERENCES backoffice_work_items(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_events (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, document_id TEXT,
    work_item_id TEXT, event_type TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agentops_evaluations (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, evaluation_type TEXT NOT NULL,
    scenario_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, source_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, read_at TEXT, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id TEXT PRIMARY KEY, dataset_name TEXT NOT NULL, provider_name TEXT NOT NULL,
    report_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_attempts (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, status TEXT NOT NULL,
    updated_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_deliveries (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, document_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL, idempotency_key TEXT NOT NULL, status TEXT NOT NULL,
    updated_at TEXT NOT NULL, payload TEXT NOT NULL,
    UNIQUE (workspace_id, adapter_name, idempotency_key)
);
CREATE TABLE IF NOT EXISTS export_batches (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, status TEXT NOT NULL,
    updated_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_runs (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, batch_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL,
    payload TEXT NOT NULL, UNIQUE (workspace_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS correction_events (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, document_id TEXT NOT NULL,
    created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_purge_events (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, document_fingerprint TEXT NOT NULL,
    actor TEXT NOT NULL, reason TEXT NOT NULL, deleted_records TEXT NOT NULL, purged_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_workspace_status_updated ON documents(workspace_id, status, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_jobs_processable ON jobs(status, next_attempt_at, updated_at, created_at, id);
CREATE INDEX IF NOT EXISTS idx_jobs_document_created ON jobs(document_id, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_audit_document_created ON audit_events(document_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_review_tasks_status_updated ON review_tasks(status, updated_at DESC, document_id);
CREATE INDEX IF NOT EXISTS idx_invoice_identity_lookup ON invoice_identities(vendor_identity, invoice_identity, document_id);
CREATE INDEX IF NOT EXISTS idx_work_item_document_latest ON backoffice_work_item_documents(workspace_id, document_id, updated_at DESC, work_item_id);
CREATE INDEX IF NOT EXISTS idx_backoffice_work_items_workspace ON backoffice_work_items(workspace_id, updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_backoffice_work_items_idempotency ON backoffice_work_items(workspace_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_backoffice_task_plans_work_item ON backoffice_task_plans(workspace_id, work_item_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_backoffice_task_plans_idempotency ON backoffice_task_plans(workspace_id, work_item_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_backoffice_action_drafts_work_item ON backoffice_action_drafts(workspace_id, work_item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_backoffice_approvals_work_item ON backoffice_approvals(workspace_id, work_item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_backoffice_approvals_pending ON backoffice_approvals(workspace_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_backoffice_policy_decisions_work_item ON backoffice_policy_decisions(workspace_id, work_item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_events_document ON workflow_events(workspace_id, document_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_events_work_item ON workflow_events(workspace_id, work_item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_workspace ON agent_runs(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agentops_evaluations_workspace ON agentops_evaluations(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_workspace ON notifications(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_evaluation_attempts_workspace ON evaluation_attempts(workspace_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_integration_deliveries_document ON integration_deliveries(workspace_id, document_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_export_batches_workspace ON export_batches(workspace_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_export_runs_workspace ON export_runs(workspace_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_correction_events_document ON correction_events(workspace_id, document_id, created_at);
