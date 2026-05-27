ALTER TABLE credential_grants
  ADD COLUMN IF NOT EXISTS secret_ref TEXT;

CREATE TABLE IF NOT EXISTS connector_connections (
  id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(id),
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  credential_scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  secret_ref TEXT,
  secret_fingerprint TEXT,
  connected_by_type TEXT NOT NULL,
  connected_by_id TEXT NOT NULL,
  project_id TEXT,
  agent_id TEXT,
  rationale TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_connector_connections_service_id
  ON connector_connections(service_id);

CREATE INDEX IF NOT EXISTS idx_connector_connections_active_service
  ON connector_connections(service_id)
  WHERE status = 'active';
