ALTER TABLE agent_lifecycle_requests
  ADD COLUMN IF NOT EXISTS proposed_soul JSONB;
