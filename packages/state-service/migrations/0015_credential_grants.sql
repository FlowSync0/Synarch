CREATE TABLE IF NOT EXISTS credential_grants (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES credential_access_requests(id),
  service_id TEXT NOT NULL REFERENCES services(id),
  agent_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  granted_by_type TEXT NOT NULL,
  granted_by_id TEXT NOT NULL,
  rationale TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_credential_grants_request_id
  ON credential_grants(request_id);

CREATE INDEX IF NOT EXISTS idx_credential_grants_service_agent
  ON credential_grants(service_id, agent_id)
  WHERE active = TRUE;
