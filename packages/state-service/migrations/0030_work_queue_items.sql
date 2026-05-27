CREATE TABLE IF NOT EXISTS work_queue_items (
  id TEXT PRIMARY KEY,
  queue_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  priority INTEGER NOT NULL DEFAULT 100,
  run_after_at TIMESTAMPTZ,
  lease_owner_id TEXT,
  lease_expires_at TIMESTAMPTZ,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  result JSONB,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_work_queue_items_ready
  ON work_queue_items (queue_name, status, priority, created_at)
  WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_work_queue_items_running_lease
  ON work_queue_items (status, lease_expires_at)
  WHERE status = 'running';
