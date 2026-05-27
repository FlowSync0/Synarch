CREATE TABLE IF NOT EXISTS worker_heartbeats (
  id TEXT PRIMARY KEY,
  worker_kind TEXT NOT NULL,
  status TEXT NOT NULL,
  target TEXT,
  heartbeat_count INTEGER NOT NULL DEFAULT 0,
  last_tick_result JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_error TEXT,
  started_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_kind_seen
  ON worker_heartbeats (worker_kind, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_target_seen
  ON worker_heartbeats (target, last_seen_at DESC)
  WHERE target IS NOT NULL;
