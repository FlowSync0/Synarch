UPDATE agents
SET
  capabilities = jsonb_set(
    COALESCE(capabilities, '{}'::jsonb),
    '{tools}',
    CASE
      WHEN COALESCE(capabilities->'tools', '[]'::jsonb) ? 'web.fetch'
        THEN COALESCE(capabilities->'tools', '[]'::jsonb)
      ELSE COALESCE(capabilities->'tools', '[]'::jsonb) || '["web.fetch"]'::jsonb
    END
  ),
  permissions = jsonb_set(
    COALESCE(permissions, '{}'::jsonb),
    '{allowed_tools}',
    CASE
      WHEN COALESCE(permissions->'allowed_tools', '[]'::jsonb) ? 'web.fetch'
        THEN COALESCE(permissions->'allowed_tools', '[]'::jsonb)
      ELSE COALESCE(permissions->'allowed_tools', '[]'::jsonb) || '["web.fetch"]'::jsonb
    END
  ),
  updated_at = now()
WHERE id = 'agent-ops-sourcing';
