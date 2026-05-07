CREATE TABLE IF NOT EXISTS connector_jobs (
  id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(id),
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
  owner_agent_id TEXT NOT NULL REFERENCES agents(id),
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  schedule TEXT,
  webhook_path TEXT,
  purpose TEXT NOT NULL,
  created_by_type TEXT NOT NULL,
  created_by_id TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  stopped_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS connector_job_runs (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES connector_jobs(id) ON DELETE CASCADE,
  service_id TEXT NOT NULL REFERENCES services(id),
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
  owner_agent_id TEXT NOT NULL REFERENCES agents(id),
  status TEXT NOT NULL,
  triggered_by_type TEXT NOT NULL,
  triggered_by_id TEXT NOT NULL,
  trace_id TEXT,
  output JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
