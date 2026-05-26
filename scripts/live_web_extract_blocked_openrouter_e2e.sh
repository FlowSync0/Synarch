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

PROJECT_ID="project_live_web_extract_blocked_${RUN_ID}"
TASK_ID="task_live_web_extract_blocked_${RUN_ID}"
TRACE_ID="trace_live_web_extract_blocked_${RUN_ID}"
BLOCKED_URL="https://httpbin.org/status/403"

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
    -H "X-Synarch-Actor-Id: live-web-extract-blocked-e2e" \
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
  echo "OPENROUTER_API_KEY is required for the live blocked web.extract E2E." >&2
  exit 1
fi

export AGENT_RUNTIME_MODE=model_gateway
export MODEL_GATEWAY_MODE=openrouter
export OPENROUTER_MODEL_ID
export TASK_RUNNER_PROVIDER_ID=provider-openrouter
export TASK_RUNNER_MODEL_ID
export OPENROUTER_API_KEY

docker compose up -d --build --wait --wait-timeout 180 \
  state-service memory-service event-service control-plane model-gateway agent-runtime gateway \
  >/dev/null

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
  (.permissions.allowed_tools | index("web.extract") != null) and
  (.available_services | index("connector-web-browser-local") != null) and
  (.available_service_capabilities["connector-web-browser-local"] | index("web.extract") != null)
' >/dev/null

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live blocked web extraction",
      goal: "Verify a blocked browser extraction cannot be converted into a completed task.",
      owner_agent_id: "agent-direction"
    }'
)"

task_payload="$(
  jq -n \
    --arg id "$TASK_ID" \
    --arg project_id "$PROJECT_ID" \
    --arg blocked_url "$BLOCKED_URL" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Extract protected supplier evidence",
      description: (
        "First request exactly one web.extract tool call on connector-web-browser-local. " +
        "Use arguments url " + $blocked_url + ", provider local_playwright, max_bytes 2048. " +
        "Do not use web.fetch and do not request any connector job. " +
        "After the tool_result is returned, if it is blocked or requires_human_review, " +
        "do not mark the task completed. Return status blocked or needs_review, no new tool calls, " +
        "and summarize the blocked_reason."
      ),
      assigned_agent_id: "agent-ops-sourcing",
      required_tools: ["web.extract"],
      acceptance_criteria: [
        "The browser extraction is attempted through connector-web-browser-local.",
        "A blocked extraction result is preserved with review evidence.",
        "The task is not completed while the extraction is blocked."
      ],
      sequence: 1
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$project_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/tasks" "$task_payload" >/dev/null

batch_response="$(curl -fsS -X POST "${GATEWAY_URL}/tasks/run-ready?project_id=${PROJECT_ID}&max_tasks=1" -H "X-Synarch-Trace-Id: ${TRACE_ID}")"

printf "%s" "$batch_response" | jq -e \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg model_id "$TASK_RUNNER_MODEL_ID" \
  --arg blocked_url "$BLOCKED_URL" \
  '
    (.trace_id == $trace_id) and
    (.project_id == $project_id) and
    (.runs | length == 1) and
    (.runs[0].task.id == $task_id) and
    (.runs[0].task.status != "completed") and
    (.runs[0].agent_result.status != "completed") and
    (.runs[0].tool_results | length == 1) and
    (.runs[0].tool_results[0].tool_name == "web.extract") and
    (.runs[0].tool_results[0].status == "blocked") and
    (.runs[0].tool_results[0].output.provider == "local_playwright") and
    (.runs[0].tool_results[0].output.url == $blocked_url) and
    (.runs[0].tool_results[0].output.status_code == 403) and
    (.runs[0].tool_results[0].output.blocked_reason == "http_access_denied") and
    (.runs[0].tool_results[0].output.requires_human_review == true) and
    (.runs[0].tool_results[0].output.human_assistance_request_id | startswith("human_assistance_auto_" + $task_id + "_")) and
    (.runs[0].tool_results[0].output.human_assistance_request.status == "requested") and
    (.runs[0].tool_results[0].output.human_assistance_request.kind == "error_resolution") and
    (.runs[0].tool_results[0].output.human_assistance_request.task_id == $task_id) and
    (.runs[0].tool_results[0].output.recommended_action == "Answer the human assistance request, then retry or update the task.") and
    (.runs[0].tool_results[0].output.review_evidence.kind == "web_extract_block") and
    (.runs[0].tool_results[0].output.review_evidence.provider == "local_playwright") and
    (.runs[0].agent_result.model_usage.provider_id == "provider-openrouter") and
    (.runs[0].agent_result.model_usage.model_id == $model_id) and
    (.runs[0].agent_result.model_usage.input_tokens > 0) and
    (.runs[0].agent_result.model_usage.output_tokens > 0) and
    (.runs[0].cost_records[0].provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[-1].payload.provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[-1].payload.tool_result_count == 1) and
    (.runs[0].model_call_events[-1].payload.blocked_tool_result_count == 1) and
    (.runs[0].model_call_events[-1].payload.blocked_tool_names == ["web.extract"]) and
    (.runs[0].model_call_events[-1].payload.blocked_tool_errors == [{"tool_name":"web.extract","error":"http_access_denied"}]) and
    (.scheduler_event.type == "scheduler.tick") and
    (.scheduler_event.payload.blocked_tool_result_count == 1) and
    (.scheduler_event.payload.blocked_tool_names == ["web.extract"]) and
    (.scheduler_event.payload.blocked_tool_errors == [{"tool_name":"web.extract","error":"http_access_denied"}])
  ' >/dev/null

HUMAN_REQUEST_ID="$(
  printf "%s" "$batch_response" |
    jq -er '.runs[0].tool_results[0].output.human_assistance_request_id'
)"

human_requests="$(
  curl -fsS "${GATEWAY_URL}/human-assistance-requests?project_id=${PROJECT_ID}&task_id=${TASK_ID}&status=requested"
)"

printf "%s" "$human_requests" | jq -e \
  --arg request_id "$HUMAN_REQUEST_ID" \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  '
    ([.[] | select(
      .id == $request_id and
      .project_id == $project_id and
      .task_id == $task_id and
      .agent_id == "agent-ops-sourcing" and
      .kind == "error_resolution" and
      .status == "requested" and
      .evidence.source_trace_id == $trace_id and
      .evidence.tool_name == "web.extract" and
      .evidence.blocked_reason == "http_access_denied" and
      .evidence.review_evidence.kind == "web_extract_block"
    )] | length == 1)
  ' >/dev/null

resolution_payload="$(
  jq -n \
    --arg request_id "$HUMAN_REQUEST_ID" \
    '{
      request_id: $request_id,
      status: "answered",
      response: "Live test user reviewed the blocked extraction and allows the task to retry with the preserved context.",
      resolved_by_type: "user",
      resolved_by_id: "live-web-extract-blocked-e2e"
    }'
)"

resolution_response="$(
  post_json "${GATEWAY_URL}/human-assistance-requests/${HUMAN_REQUEST_ID}/resolutions" "$resolution_payload"
)"

printf "%s" "$resolution_response" | jq -e \
  --arg request_id "$HUMAN_REQUEST_ID" \
  --arg task_id "$TASK_ID" \
  '
    (.request_id == $request_id) and
    (.status == "answered") and
    (.events_emitted | length == 2) and
    ([.events_emitted[] | select(.type == "human_assistance.resolved" and .payload.human_assistance_request_id == $request_id)] | length == 1) and
    ([.events_emitted[] | select(
      .type == "task.reviewed" and
      .payload.task_id == $task_id and
      .payload.action == "human_assistance_resolved" and
      .payload.previous_status == "blocked" and
      .payload.next_status == "queued"
    )] | length == 1)
  ' >/dev/null

final_task="$(
  curl -fsS "${STATE_SERVICE_URL}/tasks/${TASK_ID}"
)"

printf "%s" "$final_task" | jq -e \
  --arg request_id "$HUMAN_REQUEST_ID" \
  '
    (.status == "queued") and
    (.result.last_human_assistance_resolution.human_assistance_request_id == $request_id) and
    (.result.last_human_assistance_resolution.status == "answered") and
    (.result.last_human_assistance_resolution.next_status == "queued")
  ' >/dev/null

timeline="$(
  curl -fsS "${GATEWAY_URL}/projects/${PROJECT_ID}/timeline"
)"

printf "%s" "$timeline" | jq -e \
  --arg trace_id "$TRACE_ID" \
  --arg request_id "$HUMAN_REQUEST_ID" \
  --arg task_id "$TASK_ID" \
  '
    ([.events[] | select(.trace_id == $trace_id and .type == "tool.called" and .payload.tool_name == "web.extract")] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "human_assistance.requested" and .payload.human_assistance_request_id == $request_id)] | length == 1) and
    ([.events[] | select(
      .trace_id == $trace_id and
      .type == "tool.failed" and
      .payload.tool_name == "web.extract" and
      .payload.tool_status == "blocked" and
      .payload.blocked_reason == "http_access_denied" and
      .payload.requires_human_review == true and
      .payload.human_assistance_request_id == $request_id and
      .payload.review_evidence.kind == "web_extract_block"
    )] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "human_assistance.resolved" and .payload.human_assistance_request_id == $request_id)] | length == 1) and
    ([.events[] | select(
      .trace_id == $trace_id and
      .type == "task.reviewed" and
      .payload.task_id == $task_id and
      .payload.action == "human_assistance_resolved" and
      .payload.next_status == "queued"
    )] | length == 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "tool.allowed" and .payload.tool_name == "web.extract")] | length == 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "tool.blocked" and .payload.tool_name == "web.extract" and .payload.blocked_reason == "http_access_denied")] | length == 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "human_assistance_request.created" and .target_id == $request_id)] | length == 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "human_assistance_request.answered" and .target_id == $request_id)] | length == 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "task.human_assistance_applied" and .target_id == $task_id)] | length == 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .input_tokens > 0 and .output_tokens > 0)] | length == 1)
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg blocked_url "$BLOCKED_URL" \
  --arg human_request_id "$HUMAN_REQUEST_ID" \
  --argjson batch "$batch_response" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    trace_id: $trace_id,
    blocked_url: $blocked_url,
    human_assistance_request_id: $human_request_id,
    task_status: $batch.runs[0].task.status,
    agent_status: $batch.runs[0].agent_result.status,
    resumed_task_status: "queued",
    tool_result: {
      tool_name: $batch.runs[0].tool_results[0].tool_name,
      status: $batch.runs[0].tool_results[0].status,
      blocked_reason: $batch.runs[0].tool_results[0].output.blocked_reason,
      status_code: $batch.runs[0].tool_results[0].output.status_code,
      review_evidence_kind: $batch.runs[0].tool_results[0].output.review_evidence.kind
    },
    model_completion_tool_metrics: {
      tool_result_count: $batch.runs[0].model_call_events[-1].payload.tool_result_count,
      blocked_tool_result_count: $batch.runs[0].model_call_events[-1].payload.blocked_tool_result_count,
      blocked_tool_names: $batch.runs[0].model_call_events[-1].payload.blocked_tool_names,
      blocked_tool_errors: $batch.runs[0].model_call_events[-1].payload.blocked_tool_errors
    },
    model_usage: $batch.runs[0].cost_records[0]
  }'
