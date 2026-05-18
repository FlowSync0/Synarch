INSERT INTO services (
  id,
  name,
  kind,
  capabilities,
  credential_scopes,
  allowed_divisions,
  metadata
)
VALUES (
  'connector-browserless',
  'Browserless',
  'tool_provider',
  ARRAY['web.extract'],
  ARRAY['browserless:api_key'],
  ARRAY['ops-sourcing', 'admin-knowledge'],
  '{"connector_type":"cloud_browser","web_provider":"browserless","requires_api_key":true,"api_key_env_var":"BROWSERLESS_API_KEY","requires_human_approval":true}'::jsonb
)
ON CONFLICT (id) DO NOTHING;
