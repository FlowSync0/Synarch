ALTER TABLE services
  ADD COLUMN IF NOT EXISTS credential_scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

UPDATE services
SET credential_scopes = ARRAY['github:contents:read', 'github:contents:write']
WHERE id = 'connector-github'
  AND credential_scopes = ARRAY[]::TEXT[];
