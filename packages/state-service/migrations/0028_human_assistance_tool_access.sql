UPDATE services
SET capabilities = CASE
  WHEN 'human.assistance.request' = ANY(capabilities) THEN capabilities
  ELSE array_append(capabilities, 'human.assistance.request')
END
WHERE id = 'service-event-log';

UPDATE agents
SET
  capabilities = jsonb_set(
    COALESCE(capabilities, '{}'::jsonb),
    '{tools}',
    CASE
      WHEN COALESCE(capabilities->'tools', '[]'::jsonb) ? 'human.assistance.request'
        THEN COALESCE(capabilities->'tools', '[]'::jsonb)
      ELSE COALESCE(capabilities->'tools', '[]'::jsonb) || '["human.assistance.request"]'::jsonb
    END
  ),
  permissions = jsonb_set(
    COALESCE(permissions, '{}'::jsonb),
    '{allowed_tools}',
    CASE
      WHEN COALESCE(permissions->'allowed_tools', '[]'::jsonb) ? 'human.assistance.request'
        THEN COALESCE(permissions->'allowed_tools', '[]'::jsonb)
      ELSE COALESCE(permissions->'allowed_tools', '[]'::jsonb) || '["human.assistance.request"]'::jsonb
    END
  ),
  updated_at = now()
WHERE id IN (
  'agent-direction',
  'agent-finance',
  'agent-ops-sourcing',
  'agent-dev',
  'agent-admin-knowledge'
);
