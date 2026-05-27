UPDATE services
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{
  "manual_connection_url": "https://github.com/settings/personal-access-tokens/new",
  "connection_setup_label": "Créer un token GitHub",
  "connection_setup_instructions": "Créer un token finement limité au dépôt nécessaire, puis coller le token ici."
}'::jsonb
WHERE id = 'connector-github';

UPDATE services
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{
  "manual_connection_url": "https://www.firecrawl.dev",
  "connection_setup_label": "Ouvrir Firecrawl",
  "connection_setup_instructions": "Créer ou copier une clé API Firecrawl depuis le dashboard, puis la coller ici."
}'::jsonb
WHERE id = 'connector-firecrawl';

UPDATE services
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{
  "manual_connection_url": "https://account.browserless.io",
  "connection_setup_label": "Ouvrir Browserless",
  "connection_setup_instructions": "Créer ou copier le token Browserless depuis le dashboard, puis le coller ici."
}'::jsonb
WHERE id = 'connector-browserless';
