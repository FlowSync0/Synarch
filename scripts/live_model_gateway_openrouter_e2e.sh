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
MODEL_GATEWAY_URL="${MODEL_GATEWAY_URL:-http://localhost:8060}"
AGENT_RUNTIME_URL="${AGENT_RUNTIME_URL:-http://localhost:8050}"
TASK_RUNNER_MODEL_ID="${TASK_RUNNER_MODEL_ID:-deepseek/deepseek-v4-flash}"
OPENROUTER_MODEL_ID="${OPENROUTER_MODEL_ID:-$TASK_RUNNER_MODEL_ID}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_live_model_gateway_${RUN_ID}"
TASK_ID="task_live_model_gateway_${RUN_ID}"
TRACE_ID="trace_live_model_gateway_${RUN_ID}"
MARKER="SYNARCH_MODEL_GATEWAY_OK_${RUN_ID}"

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
    -H "X-Synarch-Actor-Id: live-model-gateway-openrouter-e2e" \
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
  echo "OPENROUTER_API_KEY is required for the live model-gateway E2E." >&2
  exit 1
fi

export AGENT_RUNTIME_MODE=model_gateway
export MODEL_GATEWAY_MODE=openrouter
export OPENROUTER_MODEL_ID
export TASK_RUNNER_PROVIDER_ID=provider-openrouter
export TASK_RUNNER_MODEL_ID
export OPENROUTER_API_KEY

docker compose up -d --build model-gateway agent-runtime gateway >/dev/null

wait_for_health "${GATEWAY_URL}/healthz"
wait_for_health "${STATE_SERVICE_URL}/healthz"
wait_for_health "${MEMORY_SERVICE_URL}/healthz"
wait_for_health "${MODEL_GATEWAY_URL}/healthz"
wait_for_health "${AGENT_RUNTIME_URL}/healthz"

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live Model Gateway OpenRouter E2E",
      goal: "Validate DeepSeek task execution through the model-gateway boundary.",
      owner_agent_id: "agent-direction"
    }'
)"

memory_payload="$(
  jq -n \
    --arg project_id "$PROJECT_ID" \
    --arg marker "$MARKER" \
    '{
      scope: ("project:" + $project_id),
      agent_id: "agent-dev",
      project_id: $project_id,
      status: "approved",
      content: ("Model gateway live proof marker: " + $marker + ". The final summary must include this exact marker.")
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
      title: "Validate model gateway runtime route",
      description: ("Use the project memory and return status completed. Include exact marker " + $marker + " in summary. Return one memory_candidates entry."),
      assigned_agent_id: "agent-dev",
      acceptance_criteria: [
        "The task runs through agent-runtime in model_gateway mode.",
        "The model-gateway calls OpenRouter with DeepSeek.",
        "The returned AgentResult contains model usage and a memory candidate."
      ],
      sequence: 1
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$project_payload" >/dev/null
curl -fsS -X POST "${MEMORY_SERVICE_URL}/memory-items" \
  -H "Content-Type: application/json" \
  -d "$memory_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/tasks" "$task_payload" >/dev/null

batch_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/run-ready?project_id=${PROJECT_ID}&max_tasks=1" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$batch_response" | jq -e \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg marker "$MARKER" \
  --arg model_id "$TASK_RUNNER_MODEL_ID" \
  '
    (.trace_id == $trace_id) and
    (.project_id == $project_id) and
    (.runs | length == 1) and
    (.runs[0].task.id == $task_id) and
    (.runs[0].agent_result.status == "completed") and
    (.runs[0].agent_result.summary | contains($marker)) and
    (.runs[0].agent_result.events_emitted[0].payload.mode == "model-gateway") and
    (.runs[0].agent_result.events_emitted[0].payload.provider_id == "provider-openrouter") and
    (.runs[0].agent_result.events_emitted[0].payload.model_id == $model_id) and
    (.runs[0].agent_result.model_usage.provider_id == "provider-openrouter") and
    (.runs[0].agent_result.model_usage.model_id == $model_id) and
    (.runs[0].agent_result.model_usage.input_tokens > 0) and
    (.runs[0].agent_result.model_usage.output_tokens > 0) and
    (.runs[0].agent_result.memory_candidates | length >= 1) and
    (.runs[0].cost_records[0].provider_id == "provider-openrouter") and
    (.runs[0].cost_records[0].model_id == $model_id) and
    (.runs[0].model_call_events[0].payload.provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[1].payload.provider_id == "provider-openrouter") and
    (.scheduler_event.type == "scheduler.tick")
  ' >/dev/null

timeline="$(
  curl -fsS "${GATEWAY_URL}/projects/${PROJECT_ID}/timeline"
)"

printf "%s" "$timeline" | jq -e \
  --arg trace_id "$TRACE_ID" \
  --arg task_id "$TASK_ID" \
  --arg marker "$MARKER" \
  '
    ([.tasks[] | select(.id == $task_id and .status == "completed")] | length == 1) and
    ([.memory_items[] | select(.status == "approved" and (.content | contains($marker)))] | length == 1) and
    ([.memory_items[] | select(.status == "proposed")] | length >= 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "model_call.completed")] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "memory.candidate_created")] | length >= 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .input_tokens > 0 and .output_tokens > 0)] | length == 1)
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg model_id "$TASK_RUNNER_MODEL_ID" \
  --argjson batch "$batch_response" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    trace_id: $trace_id,
    model_id: $model_id,
    runtime_mode: $batch.runs[0].agent_result.events_emitted[0].payload.mode,
    model_usage: $batch.runs[0].agent_result.model_usage,
    memory_candidate_count: ($batch.runs[0].agent_result.memory_candidates | length)
  }'
