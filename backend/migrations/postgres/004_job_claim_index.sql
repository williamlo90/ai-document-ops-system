-- Supports the worker's deterministic stale-first claim order while keeping
-- terminal jobs out of the index.
CREATE INDEX IF NOT EXISTS idx_jobs_claim_order
    ON jobs ((CASE WHEN status = 'running' THEN 0 ELSE 1 END), created_at, id)
    WHERE status IN ('queued', 'retrying', 'running');
