ALTER TABLE connector_connections
  ADD COLUMN IF NOT EXISTS setup_url TEXT,
  ADD COLUMN IF NOT EXISTS callback_url TEXT,
  ADD COLUMN IF NOT EXISTS external_state TEXT;

CREATE INDEX IF NOT EXISTS idx_connector_connections_external_state
  ON connector_connections (service_id, external_state)
  WHERE external_state IS NOT NULL;
