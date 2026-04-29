CREATE TABLE IF NOT EXISTS agent_souls (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL DEFAULT 1,
  identity TEXT NOT NULL,
  mission TEXT NOT NULL,
  responsibilities TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  operating_principles TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  boundaries TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  escalation_rules TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  communication_style TEXT NOT NULL DEFAULT 'Clear, concise, and auditable.',
  created_by TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
