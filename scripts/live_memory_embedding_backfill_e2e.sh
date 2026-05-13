#!/usr/bin/env bash
set -euo pipefail

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
MEMORY_SERVICE_URL="${MEMORY_SERVICE_URL:-http://localhost:8030}"
OPENROUTER_BASE_URL="${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}"
TASK_RUNNER_EMBEDDING_MODEL_ID="${TASK_RUNNER_EMBEDDING_MODEL_ID:-openai/text-embedding-3-small}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_live_memory_embedding_${RUN_ID}"
MEMORY_ID="memory_live_embedding_backfill_${RUN_ID}"
TRACE_ID="trace_live_memory_embedding_${RUN_ID}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

post_json() {
  local url="$1"
  local payload="$2"
  curl -fsS -X POST "$url" \
    -H "Content-Type: application/json" \
    -H "X-Synarch-Actor-Type: user" \
    -H "X-Synarch-Actor-Id: live-memory-embedding-backfill-e2e" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload"
}

wait_for_health() {
  local url="$1"
  for _ in $(seq 1 30); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  curl -fsS "$url" >/dev/null
}

require_command curl
require_command jq
require_command docker

if [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "OPENROUTER_API_KEY is required for the live memory embedding E2E." >&2
  exit 1
fi

export TASK_RUNNER_EMBEDDING_PROVIDER_ID=provider-openrouter
export TASK_RUNNER_EMBEDDING_MODEL_ID
export OPENROUTER_API_KEY
export OPENROUTER_BASE_URL

docker compose up -d --build gateway >/dev/null

wait_for_health "${GATEWAY_URL}/healthz"
wait_for_health "${STATE_SERVICE_URL}/healthz"
wait_for_health "${MEMORY_SERVICE_URL}/healthz"

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live memory embedding backfill",
      goal: "Backfill approved memory vectors through the Gateway.",
      owner_agent_id: "agent-direction"
    }'
)"
memory_payload="$(
  jq -n \
    --arg id "$MEMORY_ID" \
    --arg project_id "$PROJECT_ID" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      project_id: $project_id,
      agent_id: "agent-dev",
      status: "approved",
      content: "Critical supplier sourcing memory that should receive a vector embedding."
    }'
)"
backfill_payload="$(
  jq -n \
    --arg project_id "$PROJECT_ID" \
    '{
      project_id: $project_id,
      max_items: 1
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$project_payload" >/dev/null
post_json "${MEMORY_SERVICE_URL}/memory-items" "$memory_payload" >/dev/null

backfill_response="$(
  post_json "${GATEWAY_URL}/memory-items/embedding-backfill" "$backfill_payload"
)"

printf "%s" "$backfill_response" | jq -e \
  --arg memory_id "$MEMORY_ID" \
  '
    .inspected_count == 1 and
    .backfilled_count == 1 and
    .skipped_count == 0 and
    .memory_ids == [$memory_id]
  ' >/dev/null

memory_items="$(
  curl -fsS "${MEMORY_SERVICE_URL}/memory-items?project_id=${PROJECT_ID}"
)"

printf "%s" "$memory_items" | jq -e \
  --arg memory_id "$MEMORY_ID" \
  '
    any(.[];
      .id == $memory_id and
      (.embedding | type == "array") and
      (.embedding | length == 1536)
    )
  ' >/dev/null

embedding_events="$(
  curl -fsS "${GATEWAY_URL}/events?event_type=memory.embedding_backfilled&trace_id=${TRACE_ID}"
)"

printf "%s" "$embedding_events" | jq -e \
  --arg memory_id "$MEMORY_ID" \
  '
    length == 1 and
    .[0].type == "memory.embedding_backfilled" and
    .[0].payload.memory_id == $memory_id and
    .[0].payload.embedding_dimensions == 1536
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --arg memory_id "$MEMORY_ID" \
  --arg trace_id "$TRACE_ID" \
  --argjson response "$backfill_response" \
  --argjson events "$embedding_events" \
  '{
    status: "passed",
    project_id: $project_id,
    memory_id: $memory_id,
    trace_id: $trace_id,
    backfill: $response,
    event_count: ($events | length)
  }'
