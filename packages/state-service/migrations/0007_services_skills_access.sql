ALTER TABLE services
  ADD COLUMN IF NOT EXISTS allowed_agent_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN IF NOT EXISTS allowed_divisions TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN IF NOT EXISTS audit_required BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '0.1.0',
  required_tools TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  owner_agent_id TEXT REFERENCES agents(id),
  allowed_agent_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  allowed_divisions TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
