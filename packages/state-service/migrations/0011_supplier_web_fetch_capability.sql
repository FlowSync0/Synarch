UPDATE services
SET capabilities = array_append(capabilities, 'web.fetch')
WHERE id = 'connector-supplier-web'
  AND NOT ('web.fetch' = ANY(capabilities));
