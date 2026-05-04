#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_live_openrouter_${RUN_ID}"
TASK_ID="task_live_openrouter_${RUN_ID}"
TRACE_ID="trace_live_openrouter_${RUN_ID}"

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
    -H "X-Synarch-Actor-Id: live-openrouter-e2e" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload"
}

require_command curl
require_command jq

curl -fsS "${GATEWAY_URL}/healthz" >/dev/null
curl -fsS "${STATE_SERVICE_URL}/healthz" >/dev/null

if command -v docker >/dev/null 2>&1; then
  runtime_env="$(docker compose exec -T agent-runtime sh -lc 'printf "%s:%s" "$AGENT_RUNTIME_MODE" "$([ -n "$OPENROUTER_API_KEY" ] && echo present || echo missing)"' 2>/dev/null || true)"
  if [ -n "$runtime_env" ] && [ "$runtime_env" != "openrouter:present" ]; then
    echo "agent-runtime is not ready for live OpenRouter tests: ${runtime_env}" >&2
    exit 1
  fi
fi

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live OpenRouter gateway E2E",
      goal: "Use DeepSeek through Synarch to split supplier outreach into persisted child tasks.",
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
      title: "Break down supplier outreach workflow",
      description: "Create the next small debuggable tasks for finding and contacting suppliers for a motor in China. Return at least two sub_tasks_created with explicit acceptance criteria. In depends_on, refer to previous child tasks by exact title only.",
      assigned_agent_id: "agent-ops-sourcing",
      acceptance_criteria: [
        "The live model result is parsed into AgentResult.",
        "At least two child tasks are persisted.",
        "Every child task has acceptance criteria and a valid dependency list."
      ],
      sequence: 1
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$project_payload" >/dev/null
post_json "${STATE_SERVICE_URL}/tasks" "$task_payload" >/dev/null

batch_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/run-ready?project_id=${PROJECT_ID}&max_tasks=1" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$batch_response" | jq -e \
  --arg project_id "$PROJECT_ID" \
  --arg trace_id "$TRACE_ID" \
  '
    (.trace_id == $trace_id) and
    (.project_id == $project_id) and
    (.max_tasks == 1) and
    (.stop_reason == "max_tasks_reached") and
    (.runs | length == 1) and
    (.skipped_task_ids | length == 0) and
    (.lease_recovery.recovered_task_ids | length == 0) and
    (.lease_recovery.failed_task_ids | length == 0) and
    (.scheduler_event.type == "scheduler.tick") and
    (.scheduler_event.payload.run_count == 1) and
    (.scheduler_event.payload.skipped_task_count == 0) and
    (.scheduler_event.payload.lease_recovered_task_ids | length == 0) and
    (.scheduler_event.payload.lease_failed_task_ids | length == 0) and
    (.scheduler_audit_log.action == "scheduler.tick")
  ' >/dev/null

run_response="$(printf "%s" "$batch_response" | jq -c '.runs[0]')"

printf "%s" "$run_response" | jq -e \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  '
    (.trace_id == $trace_id) and
    (.task.id == $task_id) and
    (.task.project_id == $project_id) and
    (.agent_result.summary | type == "string" and length > 0) and
    (.agent_result.actions_taken | type == "array" and length > 0) and
    (.agent_result.sub_tasks_created | type == "array" and length >= 2) and
    (.created_sub_tasks | type == "array" and length >= 2) and
    (all(.created_sub_tasks[]; (.parent_task_id == $task_id) and (.acceptance_criteria | length > 0) and (.depends_on | index($task_id) != null))) and
    ((.sub_task_events | length) == (.created_sub_tasks | length)) and
    (.cost_records[0].provider_id == "provider-openrouter") and
    (.cost_records[0].model_id == "deepseek/deepseek-v4-flash") and
    (.cost_records[0].input_tokens > 0) and
    (.cost_records[0].output_tokens > 0)
  ' >/dev/null

timeline="$(
  curl -fsS "${GATEWAY_URL}/projects/${PROJECT_ID}/timeline"
)"

printf "%s" "$timeline" | jq -e \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  '
    (.project_id == $project_id) and
    ([.tasks[] | select(.id == $task_id and .status == "completed")] | length == 1) and
    ([.tasks[] | select(.parent_task_id == $task_id)] | length >= 2) and
    (all([.tasks[] | select(.parent_task_id == $task_id)][]; (.acceptance_criteria | length > 0) and (.depends_on | index($task_id) != null))) and
    ([.events[] | select(.trace_id == $trace_id and .type == "scheduler.tick" and .payload.run_count == 1)] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "task.created" and .payload.parent_task_id == $task_id)] | length >= 2) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "scheduler.tick")] | length == 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .model_id == "deepseek/deepseek-v4-flash" and .input_tokens > 0 and .output_tokens > 0)] | length == 1)
  ' >/dev/null

printf "%s" "$run_response" | jq \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg stop_reason "$(printf "%s" "$batch_response" | jq -r '.stop_reason')" \
  --arg scheduler_event_id "$(printf "%s" "$batch_response" | jq -r '.scheduler_event.id')" \
  --arg scheduler_audit_id "$(printf "%s" "$batch_response" | jq -r '.scheduler_audit_log.id')" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    trace_id: $trace_id,
    batch_stop_reason: $stop_reason,
    scheduler_event_id: $scheduler_event_id,
    scheduler_audit_id: $scheduler_audit_id,
    task_status: .task.status,
    agent_status: .agent_result.status,
    created_sub_tasks: [.created_sub_tasks[] | {id, title, depends_on, acceptance_criteria_count: (.acceptance_criteria | length)}],
    model_usage: .cost_records[0]
  }'
