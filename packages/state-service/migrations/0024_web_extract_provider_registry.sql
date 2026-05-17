INSERT INTO services (
  id,
  name,
  kind,
  capabilities,
  credential_scopes,
  allowed_divisions,
  metadata
)
VALUES
  (
    'connector-web-local',
    'Local Web Extractor',
    'tool_provider',
    ARRAY['web.fetch', 'web.extract'],
    ARRAY[]::TEXT[],
    ARRAY['ops-sourcing', 'admin-knowledge', 'dev'],
    '{"connector_type":"web_extraction","web_provider":"local_fetch","requires_api_key":false}'::jsonb
  ),
  (
    'connector-firecrawl',
    'Firecrawl',
    'tool_provider',
    ARRAY['web.extract'],
    ARRAY['firecrawl:api_key'],
    ARRAY['ops-sourcing', 'admin-knowledge'],
    '{"connector_type":"web_extraction","web_provider":"firecrawl","requires_api_key":true,"api_key_env_var":"FIRECRAWL_API_KEY"}'::jsonb
  )
ON CONFLICT (id) DO NOTHING;

UPDATE services
SET
  capabilities = CASE
    WHEN 'web.extract' = ANY(capabilities) THEN capabilities
    ELSE array_append(capabilities, 'web.extract')
  END,
  metadata = COALESCE(metadata, '{}'::jsonb) || '{"web_provider":"local_fetch"}'::jsonb
WHERE id = 'connector-supplier-web';

UPDATE agents
SET
  capabilities = jsonb_set(
    COALESCE(capabilities, '{}'::jsonb),
    '{tools}',
    CASE
      WHEN COALESCE(capabilities->'tools', '[]'::jsonb) ? 'web.extract'
        THEN COALESCE(capabilities->'tools', '[]'::jsonb)
      ELSE COALESCE(capabilities->'tools', '[]'::jsonb) || '["web.extract"]'::jsonb
    END
  ),
  permissions = jsonb_set(
    COALESCE(permissions, '{}'::jsonb),
    '{allowed_tools}',
    CASE
      WHEN COALESCE(permissions->'allowed_tools', '[]'::jsonb) ? 'web.extract'
        THEN COALESCE(permissions->'allowed_tools', '[]'::jsonb)
      ELSE COALESCE(permissions->'allowed_tools', '[]'::jsonb) || '["web.extract"]'::jsonb
    END
  ),
  updated_at = now()
WHERE id = 'agent-ops-sourcing';

UPDATE skills
SET
  required_tools = CASE
    WHEN 'web.extract' = ANY(required_tools) THEN required_tools
    ELSE array_append(required_tools, 'web.extract')
  END,
  updated_at = now()
WHERE id = 'supplier_search';
