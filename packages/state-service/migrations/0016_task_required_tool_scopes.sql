ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS required_tool_scopes JSONB NOT NULL DEFAULT '{}'::jsonb;
