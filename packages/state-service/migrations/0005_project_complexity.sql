CREATE TABLE IF NOT EXISTS project_complexity_reports (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_count INTEGER NOT NULL DEFAULT 0,
  open_task_count INTEGER NOT NULL DEFAULT 0,
  blocked_task_count INTEGER NOT NULL DEFAULT 0,
  assigned_agent_count INTEGER NOT NULL DEFAULT 0,
  workspace_bridge_count INTEGER NOT NULL DEFAULT 0,
  score INTEGER NOT NULL DEFAULT 0,
  threshold INTEGER NOT NULL DEFAULT 10,
  split_recommended BOOLEAN NOT NULL DEFAULT false,
  reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_split_requests (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  complexity_report_id TEXT NOT NULL REFERENCES project_complexity_reports(id) ON DELETE CASCADE,
  requested_by TEXT NOT NULL DEFAULT 'system',
  reason TEXT NOT NULL,
  proposed_shard_titles TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  status TEXT NOT NULL DEFAULT 'requested',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
