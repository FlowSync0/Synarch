CREATE TABLE IF NOT EXISTS human_assistance_requests (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  kind TEXT NOT NULL DEFAULT 'other',
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  urgency TEXT NOT NULL DEFAULT 'medium',
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  requested_by_type TEXT NOT NULL DEFAULT 'agent',
  requested_by_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'requested',
  response TEXT,
  resolved_by_type TEXT,
  resolved_by_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_human_assistance_project_status
  ON human_assistance_requests(project_id, status);

CREATE INDEX IF NOT EXISTS idx_human_assistance_task_status
  ON human_assistance_requests(task_id, status);
