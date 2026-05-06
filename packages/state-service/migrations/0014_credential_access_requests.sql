CREATE TABLE IF NOT EXISTS credential_access_requests (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  agent_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  requested_scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  candidate_service_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  reason TEXT NOT NULL,
  requested_by_type TEXT NOT NULL DEFAULT 'service',
  requested_by_id TEXT NOT NULL DEFAULT 'gateway-scheduler',
  status TEXT NOT NULL DEFAULT 'requested',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
