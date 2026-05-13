#!/usr/bin/env bash
set -euo pipefail

STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
MEMORY_SERVICE_URL="${MEMORY_SERVICE_URL:-http://localhost:8030}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_vector_${RUN_ID}"
OTHER_PROJECT_ID="project_vector_other_${RUN_ID}"
TRACE_ID="trace_vector_${RUN_ID}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

embedding_axis() {
  local index="$1"
  jq -n --argjson index "$index" \
    '[range(0;1536) | if . == $index then 1.0 else 0.0 end]'
}

post_project() {
  local project_id="$1"
  local title="$2"
  local payload
  payload="$(
    jq -n \
      --arg id "$project_id" \
      --arg title "$title" \
      '{
        id: $id,
        title: $title,
        goal: "Validate vector context ranking.",
        owner_agent_id: "agent-direction"
      }'
  )"
  curl -fsS -X POST "${STATE_SERVICE_URL}/projects" \
    -H "Content-Type: application/json" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload" >/dev/null
}

post_memory() {
  local item_id="$1"
  local project_id="$2"
  local content="$3"
  local embedding="$4"
  local payload
  payload="$(
    jq -n \
      --arg id "$item_id" \
      --arg project_id "$project_id" \
      --arg content "$content" \
      --argjson embedding "$embedding" \
      '{
        id: $id,
        scope: ("project:" + $project_id),
        project_id: $project_id,
        content: $content,
        embedding: $embedding,
        status: "approved"
      }'
  )"
  curl -fsS -X POST "${MEMORY_SERVICE_URL}/memory-items" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null
}

require_command curl
require_command jq

curl -fsS "${STATE_SERVICE_URL}/healthz" >/dev/null
curl -fsS "${MEMORY_SERVICE_URL}/healthz" >/dev/null

embedding_0="$(embedding_axis 0)"
embedding_1="$(embedding_axis 1)"

post_project "$PROJECT_ID" "Vector memory live test"
post_project "$OTHER_PROJECT_ID" "Other vector memory live test"

post_memory "mem_vector_miss_${RUN_ID}" \
  "$PROJECT_ID" \
  "Visible but less similar vector memory." \
  "$embedding_0"
post_memory "mem_vector_match_${RUN_ID}" \
  "$PROJECT_ID" \
  "Visible and most similar vector memory." \
  "$embedding_1"
post_memory "mem_vector_other_${RUN_ID}" \
  "$OTHER_PROJECT_ID" \
  "Matching vector but forbidden by project scope." \
  "$embedding_1"

bad_status="$(
  curl -sS -o "/tmp/synarch_bad_embedding_${RUN_ID}.json" -w "%{http_code}" \
    -X POST "${MEMORY_SERVICE_URL}/memory-items" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
      --arg id "mem_bad_${RUN_ID}" \
      '{id: $id, scope: "global", content: "bad", embedding: [1.0, 0.0]}')"
)"
if [ "$bad_status" != "400" ]; then
  echo "Expected bad embedding to return 400, got ${bad_status}" >&2
  exit 1
fi

context_payload="$(
  jq -n \
    --arg project_id "$PROJECT_ID" \
    --argjson embedding "$embedding_1" \
    '{
      agent_id: "agent-dev",
      project_id: $project_id,
      token_budget: 200,
      allowed_scopes: [("project:" + $project_id)],
      query_embedding: $embedding
    }'
)"
context="$(
  curl -fsS -X POST "${MEMORY_SERVICE_URL}/context/assemble" \
    -H "Content-Type: application/json" \
    -d "$context_payload"
)"

printf "%s" "$context" | jq -e \
  --arg match "mem_vector_match_${RUN_ID}" \
  --arg miss "mem_vector_miss_${RUN_ID}" \
  '
    (.items[0].id == $match) and
    (.items[1].id == $miss) and
    ((.items | length) == 2) and
    (.summary | contains("semantic vector ranking"))
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --argjson context "$context" \
  --arg bad_embedding_status "$bad_status" \
  '{
    passed: true,
    project_id: $project_id,
    ordered_item_ids: [$context.items[].id],
    summary: $context.summary,
    bad_embedding_status: ($bad_embedding_status | tonumber)
  }'
