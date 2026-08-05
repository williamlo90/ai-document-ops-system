SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    payload_summary TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_identities (
    workspace_id TEXT NOT NULL,
    vendor_key TEXT NOT NULL,
    invoice_key TEXT NOT NULL,
    PRIMARY KEY (workspace_id, vendor_key, invoice_key)
);
CREATE TABLE IF NOT EXISTS processing_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    lease_token TEXT,
    lease_expires_at TEXT,
    next_attempt_at TEXT NOT NULL,
    error_code TEXT
);
CREATE TABLE IF NOT EXISTS review_records (
    document_id TEXT PRIMARY KEY,
    original_json TEXT NOT NULL,
    current_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correction_events (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    before_value TEXT,
    after_value TEXT,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
