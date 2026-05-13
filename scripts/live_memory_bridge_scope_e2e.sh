#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
MEMORY_SERVICE_URL="${MEMORY_SERVICE_URL:-http://localhost:8030}"
RUN_ID="${RUN_ID:-$(date +%s)}"

TARGET_PROJECT_ID="project_live_bridge_target_${RUN_ID}"
SOURCE_PROJECT_ID="project_live_bridge_source_${RUN_ID}"
OTHER_PROJECT_ID="project_live_bridge_other_${RUN_ID}"
TASK_ID="task_live_bridge_${RUN_ID}"
TRACE_ID="trace_live_memory_bridge_${RUN_ID}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

post_state() {
  local path="$1"
  local payload="$2"
  curl -fsS -X POST "${STATE_SERVICE_URL}/${path}" \
    -H "Content-Type: application/json" \
    -H "X-Synarch-Actor-Type: user" \
    -H "X-Synarch-Actor-Id: live-memory-bridge-e2e" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload" >/dev/null
}

post_memory() {
  local payload="$1"
  curl -fsS -X POST "${MEMORY_SERVICE_URL}/memory-items" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null
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

project_payload() {
  local project_id="$1"
  local title="$2"
  jq -n \
    --arg id "$project_id" \
    --arg title "$title" \
    '{
      id: $id,
      title: $title,
      goal: "Validate explicit project memory bridge isolation.",
      owner_agent_id: "agent-direction"
    }'
}

memory_payload() {
  local memory_id="$1"
  local project_id="$2"
  local content="$3"
  jq -n \
    --arg id "$memory_id" \
    --arg project_id "$project_id" \
    --arg content "$content" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      project_id: $project_id,
      status: "approved",
      content: $content
    }'
}

require_command curl
require_command jq
require_command docker

export AGENT_RUNTIME_MODE=stub
export TASK_RUNNER_PROVIDER_ID=provider-local-runtime-stub
export TASK_RUNNER_MODEL_ID=model-local-runtime-stub

docker compose up -d --build agent-runtime gateway >/dev/null

wait_for_health "${GATEWAY_URL}/healthz"
wait_for_health "${STATE_SERVICE_URL}/healthz"
wait_for_health "${MEMORY_SERVICE_URL}/healthz"

post_state projects "$(project_payload "$TARGET_PROJECT_ID" "Bridge target project")"
post_state projects "$(project_payload "$SOURCE_PROJECT_ID" "Bridge source project")"
post_state projects "$(project_payload "$OTHER_PROJECT_ID" "Bridge other project")"

target_workspace_payload="$(
  jq -n \
    --arg id "workspace_bridge_target_${RUN_ID}" \
    --arg project_id "$TARGET_PROJECT_ID" \
    --arg source_project_id "$SOURCE_PROJECT_ID" \
    '{
      id: $id,
      project_id: $project_id,
      name: "Bridge target workspace",
      memory_scope: ("project:" + $project_id),
      allowed_agent_ids: ["agent-dev"],
      bridge_project_ids: [$source_project_id],
      active: true
    }'
)"
post_state project-workspaces "$target_workspace_payload"

task_payload="$(
  jq -n \
    --arg id "$TASK_ID" \
    --arg project_id "$TARGET_PROJECT_ID" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Validate bridged memory isolation",
      description: "The runtime should receive target and explicitly bridged source memory only.",
      assigned_agent_id: "agent-dev",
      acceptance_criteria: [
        "Target project memory is visible.",
        "Source project memory is visible only because the workspace declares a bridge.",
        "Unbridged project memory is not visible."
      ],
      sequence: 1
    }'
)"
post_state tasks "$task_payload"

post_memory "$(memory_payload "memory_bridge_target_${RUN_ID}" "$TARGET_PROJECT_ID" "Target project memory.")"
post_memory "$(memory_payload "memory_bridge_source_${RUN_ID}" "$SOURCE_PROJECT_ID" "Bridged source project memory.")"
post_memory "$(memory_payload "memory_bridge_other_${RUN_ID}" "$OTHER_PROJECT_ID" "Unbridged other project memory.")"

run_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/run-ready?project_id=${TARGET_PROJECT_ID}&max_tasks=1" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$run_response" | jq -e \
  --arg task_id "$TASK_ID" \
  --arg target_project_id "$TARGET_PROJECT_ID" \
  --arg source_project_id "$SOURCE_PROJECT_ID" \
  --arg target_memory_id "memory_bridge_target_${RUN_ID}" \
  --arg source_memory_id "memory_bridge_source_${RUN_ID}" \
  --arg other_memory_id "memory_bridge_other_${RUN_ID}" \
  '
    (.runs | length == 1) and
    (.runs[0].task.id == $task_id) and
    (.runs[0].memory_context.allowed_scopes | index("project:" + $source_project_id) != null) and
    (.runs[0].memory_context.allowed_project_ids == [$target_project_id, $source_project_id]) and
    ([$target_memory_id, $source_memory_id] - [.runs[0].memory_context.items[].id] | length == 0) and
    ([.runs[0].memory_context.items[].id] | index($other_memory_id) == null) and
    (.runs[0].model_call_events[0].payload.memory_allowed_project_ids == [$target_project_id, $source_project_id])
  ' >/dev/null

jq -n \
  --arg target_project_id "$TARGET_PROJECT_ID" \
  --arg source_project_id "$SOURCE_PROJECT_ID" \
  --arg trace_id "$TRACE_ID" \
  --argjson response "$run_response" \
  '{
    status: "passed",
    target_project_id: $target_project_id,
    source_project_id: $source_project_id,
    trace_id: $trace_id,
    selected_memory_item_ids: [$response.runs[0].memory_context.items[].id]
  }'
