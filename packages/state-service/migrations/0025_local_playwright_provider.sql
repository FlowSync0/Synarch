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
  'connector-web-browser-local',
  'Local Playwright Browser',
  'tool_provider',
  ARRAY['web.extract'],
  ARRAY[]::TEXT[],
  ARRAY['ops-sourcing', 'admin-knowledge', 'dev'],
  '{"connector_type":"web_browser","web_provider":"local_playwright","requires_api_key":false,"browser":"chromium"}'::jsonb
)
ON CONFLICT (id) DO NOTHING;
