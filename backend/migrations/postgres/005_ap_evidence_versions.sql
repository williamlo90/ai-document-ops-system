-- Additive AP evidence/procurement history; no legacy rows are rewritten.

CREATE TABLE IF NOT EXISTS ap_scope_locks (
 workspace_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ap_versions (
 workspace_id TEXT NOT NULL, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
 version INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (workspace_id, kind, entity_id, version)
);
