UPDATE services
SET capabilities = array_append(capabilities, 'connector.job.list')
WHERE id = 'connector-supplier-web'
  AND NOT ('connector.job.list' = ANY(capabilities));

UPDATE agents
SET
  capabilities = jsonb_set(
    COALESCE(capabilities, '{}'::jsonb),
    '{tools}',
    CASE
      WHEN COALESCE(capabilities->'tools', '[]'::jsonb) ? 'connector.job.list'
        THEN COALESCE(capabilities->'tools', '[]'::jsonb)
      ELSE COALESCE(capabilities->'tools', '[]'::jsonb) || '["connector.job.list"]'::jsonb
    END
  ),
  permissions = jsonb_set(
    COALESCE(permissions, '{}'::jsonb),
    '{allowed_tools}',
    CASE
      WHEN COALESCE(permissions->'allowed_tools', '[]'::jsonb) ? 'connector.job.list'
        THEN COALESCE(permissions->'allowed_tools', '[]'::jsonb)
      ELSE COALESCE(permissions->'allowed_tools', '[]'::jsonb) || '["connector.job.list"]'::jsonb
    END
  ),
  updated_at = now()
WHERE id = 'agent-ops-sourcing';

UPDATE skills
SET
  required_tools = array_append(required_tools, 'connector.job.list'),
  updated_at = now()
WHERE id = 'order_tracking'
  AND NOT ('connector.job.list' = ANY(required_tools));
