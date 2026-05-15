#!/usr/bin/env bash
set -euo pipefail

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://localhost:8010}"
MODEL_GATEWAY_URL="${MODEL_GATEWAY_URL:-http://localhost:8060}"
AGENT_RUNTIME_URL="${AGENT_RUNTIME_URL:-http://localhost:8050}"
TASK_RUNNER_MODEL_ID="${TASK_RUNNER_MODEL_ID:-deepseek/deepseek-v4-flash}"
OPENROUTER_MODEL_ID="${OPENROUTER_MODEL_ID:-$TASK_RUNNER_MODEL_ID}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_live_connector_jobs_${RUN_ID}"
TASK_ID="task_live_connector_jobs_${RUN_ID}"
OWN_JOB_ID="connector_job_live_owned_${RUN_ID}"
OTHER_JOB_ID="connector_job_live_other_${RUN_ID}"
TRACE_ID="trace_live_connector_jobs_${RUN_ID}"

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
    -H "X-Synarch-Actor-Id: live-connector-job-list-stop-e2e" \
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
  echo "OPENROUTER_API_KEY is required for the live connector job E2E." >&2
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
wait_for_health "${CONTROL_PLANE_URL}/healthz"
wait_for_health "${MODEL_GATEWAY_URL}/healthz"
wait_for_health "${AGENT_RUNTIME_URL}/healthz"

runtime_env="$(docker compose exec -T agent-runtime sh -lc 'printf "%s" "$AGENT_RUNTIME_MODE"' 2>/dev/null || true)"
model_gateway_env="$(docker compose exec -T model-gateway sh -lc 'printf "%s:%s" "$MODEL_GATEWAY_MODE" "$([ -n "$OPENROUTER_API_KEY" ] && echo present || echo missing)"' 2>/dev/null || true)"
if [ "$runtime_env" != "model_gateway" ]; then
  echo "agent-runtime is not ready for model-gateway live tests: ${runtime_env}" >&2
  exit 1
fi
if [ "$model_gateway_env" != "openrouter:present" ]; then
  echo "model-gateway is not ready for live OpenRouter tests: ${model_gateway_env}" >&2
  exit 1
fi

world_view="$(
  curl -fsS "${CONTROL_PLANE_URL}/agents/agent-ops-sourcing/world-view"
)"
printf "%s" "$world_view" | jq -e '
  (.permissions.allowed_tools | index("connector.job.list") != null) and
  (.permissions.allowed_tools | index("connector.job.stop") != null) and
  (.available_services | index("connector-supplier-web") != null) and
  (.available_service_capabilities["connector-supplier-web"] | index("connector.job.list") != null) and
  (.available_service_capabilities["connector-supplier-web"] | index("connector.job.stop") != null)
' >/dev/null

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live connector job list then stop",
      goal: "Use DeepSeek to inspect active connector jobs before stopping a completed follow-up loop.",
      owner_agent_id: "agent-direction"
    }'
)"

task_payload="$(
  jq -n \
    --arg id "$TASK_ID" \
    --arg project_id "$PROJECT_ID" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Inspect and stop completed supplier follow-up",
      description: "A supplier replied, but this task does not provide the connector job id. First request connector.job.list on connector-supplier-web with status active. Do not request connector.job.stop until tool_results contain connector.job.list. Then stop the active supplier follow-up job that belongs to you. After the stop tool result is returned, finish with status completed and no new tool calls.",
      assigned_agent_id: "agent-ops-sourcing",
      required_tools: ["connector.job.list", "connector.job.stop"],
      acceptance_criteria: [
        "The agent discovers the active owned connector job through connector.job.list.",
        "The discovered job is stopped through connector.job.stop.",
        "The final answer uses the real stop tool result and requests no further tool calls."
      ],
      sequence: 1
    }'
)"

own_job_payload="$(
  jq -n \
    --arg id "$OWN_JOB_ID" \
    --arg project_id "$PROJECT_ID" \
    '{
      id: $id,
      service_id: "connector-supplier-web",
      project_id: $project_id,
      owner_agent_id: "agent-ops-sourcing",
      kind: "cron",
      schedule: "*/30 * * * *",
      purpose: "Supplier follow-up polling loop; stop once a supplier replies.",
      created_by_type: "agent",
      created_by_id: "agent-ops-sourcing",
      metadata: {
        tool_name: "web.fetch",
        max_runs: 5
      }
    }'
)"

other_job_payload="$(
  jq -n \
    --arg id "$OTHER_JOB_ID" \
    --arg project_id "$PROJECT_ID" \
    '{
      id: $id,
      service_id: "connector-supplier-web",
      project_id: $project_id,
      owner_agent_id: "agent-dev",
      kind: "cron",
      schedule: "*/30 * * * *",
      purpose: "Other agent supplier polling loop that must stay untouched.",
      created_by_type: "agent",
      created_by_id: "agent-dev",
      metadata: {
        tool_name: "web.fetch",
        max_runs: 5
      }
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$project_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/tasks" "$task_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/connector-jobs" "$own_job_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/connector-jobs" "$other_job_payload" >/dev/null

batch_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/run-ready?project_id=${PROJECT_ID}&max_tasks=1" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$batch_response" | jq -e \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg own_job_id "$OWN_JOB_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg model_id "$TASK_RUNNER_MODEL_ID" \
  '
    (.trace_id == $trace_id) and
    (.project_id == $project_id) and
    (.runs | length == 1) and
    (.runs[0].task.id == $task_id) and
    (.runs[0].agent_result.status == "completed") and
    (.runs[0].agent_result.tool_calls_requested == []) and
    (.runs[0].tool_results | length == 2) and
    (.runs[0].tool_results[0].tool_name == "connector.job.list") and
    (.runs[0].tool_results[0].output.connector_jobs | length == 1) and
    (.runs[0].tool_results[0].output.connector_jobs[0].id == $own_job_id) and
    (.runs[0].tool_results[1].tool_name == "connector.job.stop") and
    (.runs[0].tool_results[1].output.connector_job_id == $own_job_id) and
    (.runs[0].tool_results[1].output.status == "stopped") and
    (.runs[0].agent_result.model_usage.provider_id == "provider-openrouter") and
    (.runs[0].agent_result.model_usage.model_id == $model_id) and
    (.runs[0].agent_result.model_usage.input_tokens > 0) and
    (.runs[0].agent_result.model_usage.output_tokens > 0) and
    (.runs[0].cost_records[0].provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[0].payload.provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[1].payload.provider_id == "provider-openrouter") and
    (.scheduler_event.type == "scheduler.tick")
  ' >/dev/null

own_job="$(
  curl -fsS "${STATE_SERVICE_URL}/connector-jobs/${OWN_JOB_ID}"
)"
other_job="$(
  curl -fsS "${STATE_SERVICE_URL}/connector-jobs/${OTHER_JOB_ID}"
)"
timeline="$(
  curl -fsS "${GATEWAY_URL}/projects/${PROJECT_ID}/timeline"
)"

printf "%s" "$own_job" | jq -e '.status == "stopped"' >/dev/null
printf "%s" "$other_job" | jq -e '.status == "active"' >/dev/null
printf "%s" "$timeline" | jq -e \
  --arg trace_id "$TRACE_ID" \
  --arg own_job_id "$OWN_JOB_ID" \
  '
    ([.events[] | select(.trace_id == $trace_id and .type == "tool.called")] | length == 2) and
    ([.events[] | select(.trace_id == $trace_id and .type == "connector_job.stopped" and .payload.connector_job_id == $own_job_id)] | length == 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "tool.allowed")] | length == 2) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "connector_job.stopped" and .target_id == $own_job_id)] | length == 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .input_tokens > 0 and .output_tokens > 0)] | length == 1)
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg own_job_id "$OWN_JOB_ID" \
  --arg other_job_id "$OTHER_JOB_ID" \
  --argjson batch "$batch_response" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    trace_id: $trace_id,
    listed_job_id: $batch.runs[0].tool_results[0].output.connector_jobs[0].id,
    stopped_job_id: $own_job_id,
    untouched_job_id: $other_job_id,
    tool_results: [$batch.runs[0].tool_results[].tool_name],
    agent_status: $batch.runs[0].agent_result.status,
    model_usage: $batch.runs[0].cost_records[0]
  }'
