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
TASK_RUNNER_MODEL_ID="${TASK_RUNNER_MODEL_ID:-deepseek/deepseek-v4-flash}"
OPENROUTER_MODEL_ID="${OPENROUTER_MODEL_ID:-$TASK_RUNNER_MODEL_ID}"
TASK_RUNNER_EMBEDDING_MODEL_ID="${TASK_RUNNER_EMBEDDING_MODEL_ID:-openai/text-embedding-3-small}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_live_task_embedding_${RUN_ID}"
TASK_ID="task_live_task_embedding_${RUN_ID}"
MATCH_MEMORY_ID="memory_live_embedding_match_${RUN_ID}"
MISS_MEMORY_ID="memory_live_embedding_miss_${RUN_ID}"
TRACE_ID="trace_live_task_embedding_${RUN_ID}"
MARKER="SYNARCH_EMBEDDING_OK_${RUN_ID}"

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
    -H "X-Synarch-Actor-Id: live-openrouter-task-embedding-e2e" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload"
}

openrouter_embedding() {
  local text="$1"
  local response
  response="$(
    curl -fsS -X POST "${OPENROUTER_BASE_URL%/}/embeddings" \
      -H "Authorization: Bearer ${OPENROUTER_API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$(jq -n \
        --arg model "$TASK_RUNNER_EMBEDDING_MODEL_ID" \
        --arg input "$text" \
        '{model: $model, input: $input, encoding_format: "float"}')"
  )"
  printf "%s" "$response" | jq -e '.data[0].embedding | length == 1536' >/dev/null
  printf "%s" "$response" | jq -c '.data[0].embedding'
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
  echo "OPENROUTER_API_KEY is required for the live embedding E2E." >&2
  exit 1
fi

export AGENT_RUNTIME_MODE=model_gateway
export MODEL_GATEWAY_MODE=openrouter
export OPENROUTER_MODEL_ID
export TASK_RUNNER_PROVIDER_ID=provider-openrouter
export TASK_RUNNER_MODEL_ID
export TASK_RUNNER_EMBEDDING_PROVIDER_ID=provider-openrouter
export TASK_RUNNER_EMBEDDING_MODEL_ID
export OPENROUTER_API_KEY
export OPENROUTER_BASE_URL

docker compose up -d --build model-gateway agent-runtime gateway >/dev/null

wait_for_health "${GATEWAY_URL}/healthz"
wait_for_health "${STATE_SERVICE_URL}/healthz"
wait_for_health "${MEMORY_SERVICE_URL}/healthz"
wait_for_health "http://localhost:8060/healthz"
wait_for_health "http://localhost:8050/healthz"

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live OpenRouter task embedding",
      goal: "Retrieve the motor supplier sourcing memory before task execution.",
      owner_agent_id: "agent-direction"
    }'
)"
task_payload="$(
  jq -n \
    --arg id "$TASK_ID" \
    --arg project_id "$PROJECT_ID" \
    --arg marker "$MARKER" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Prepare China motor supplier RFQ",
      description: ("Use project memory to prepare a short sourcing plan for motor supplier RFQ outreach in China. Return status completed. Include marker " + $marker + " in summary. Return at least one memory_candidates entry."),
      assigned_agent_id: "agent-ops-sourcing",
      acceptance_criteria: [
        "The matching supplier memory is selected before unrelated finance memory.",
        "The model returns a completed AgentResult.",
        "At least one memory candidate is persisted with an embedding."
      ],
      sequence: 1
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$project_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/tasks" "$task_payload" >/dev/null

match_embedding="$(
  openrouter_embedding "China motor supplier RFQ sourcing outreach contacts"
)"
miss_embedding="$(
  openrouter_embedding "VAT invoice reconciliation finance exception"
)"

match_memory_payload="$(
  jq -n \
    --arg id "$MATCH_MEMORY_ID" \
    --arg project_id "$PROJECT_ID" \
    --argjson embedding "$match_embedding" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      project_id: $project_id,
      agent_id: "agent-ops-sourcing",
      status: "approved",
      content: "China motor supplier RFQ sourcing outreach contacts.",
      embedding: $embedding
    }'
)"
miss_memory_payload="$(
  jq -n \
    --arg id "$MISS_MEMORY_ID" \
    --arg project_id "$PROJECT_ID" \
    --argjson embedding "$miss_embedding" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      project_id: $project_id,
      agent_id: "agent-ops-sourcing",
      status: "approved",
      content: "VAT invoice reconciliation finance exception.",
      embedding: $embedding
    }'
)"
post_json "${MEMORY_SERVICE_URL}/memory-items" "$match_memory_payload" >/dev/null
post_json "${MEMORY_SERVICE_URL}/memory-items" "$miss_memory_payload" >/dev/null

batch_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/run-ready?project_id=${PROJECT_ID}&max_tasks=1" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$batch_response" | jq -e \
  --arg task_id "$TASK_ID" \
  --arg match_memory_id "$MATCH_MEMORY_ID" \
  --arg marker "$MARKER" \
  '
    (.runs | length == 1) and
    (.runs[0].task.id == $task_id) and
    (.runs[0].agent_result.status == "completed") and
    (.runs[0].agent_result.events_emitted[0].payload.mode == "model-gateway") and
    (.runs[0].agent_result.summary | contains($marker)) and
    (.runs[0].memory_context.query_embedding == null) and
    (all(.runs[0].memory_context.items[]; .embedding == null)) and
    (.runs[0].memory_context.summary | contains("semantic vector ranking")) and
    (.runs[0].model_call_events[0].payload.memory_query_embedding_used == true) and
    (.runs[0].model_call_events[0].payload.memory_query_embedding_dimensions == 1536) and
    (.runs[0].model_call_events[0].payload.memory_item_ids[0] == $match_memory_id) and
    ([.runs[0].memory_events[] | select(.type == "memory.candidate_created" and .payload.embedding_dimensions == 1536)] | length >= 1)
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg embedding_model_id "$TASK_RUNNER_EMBEDDING_MODEL_ID" \
  --argjson batch "$batch_response" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    trace_id: $trace_id,
    embedding_model_id: $embedding_model_id,
    selected_memory_item_ids: $batch.runs[0].model_call_events[0].payload.memory_item_ids,
    runtime_mode: $batch.runs[0].agent_result.events_emitted[0].payload.mode,
    memory_candidate_events: ($batch.runs[0].memory_events | length),
    model_usage: $batch.runs[0].cost_records[0]
  }'
