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

PROJECT_ID="project_live_lifecycle_${RUN_ID}"
TASK_ID="task_live_lifecycle_${RUN_ID}"
REQUEST_ID="lifecycle-live-create-sourcing-researcher-${RUN_ID}"
NEW_AGENT_ID="agent-live-sourcing-researcher-${RUN_ID}"
NEW_SOUL_ID="soul-agent-live-sourcing-researcher-${RUN_ID}-v1"
TRACE_ID="trace_live_lifecycle_${RUN_ID}"

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
    -H "X-Synarch-Actor-Id: live-lifecycle-openrouter-e2e" \
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
  echo "OPENROUTER_API_KEY is required for the live lifecycle E2E." >&2
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

project_payload="$(
  jq -n \
    --arg id "$PROJECT_ID" \
    '{
      id: $id,
      title: "Live lifecycle proposal OpenRouter E2E",
      goal: "Verify a manager AI can propose a new employee through an approval-gated lifecycle request.",
      owner_agent_id: "agent-direction"
    }'
)"

task_payload="$(
  jq -n \
    --arg id "$TASK_ID" \
    --arg project_id "$PROJECT_ID" \
    --arg request_id "$REQUEST_ID" \
    --arg new_agent_id "$NEW_AGENT_ID" \
    --arg new_soul_id "$NEW_SOUL_ID" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Propose a supplier researcher employee",
      description: (
        "Create exactly one lifecycle_requests_created item and no tool calls. " +
        "The lifecycle request id must be " + $request_id + ". " +
        "Use action create_agent and reason: Supplier sourcing volume requires a bounded researcher worker. " +
        "The proposed_agent must use id " + $new_agent_id + ", name IA Supplier Researcher Live, role Supplier research worker, division ops-sourcing, manager_id agent-ops-sourcing, model_policy_id policy-worker-default. " +
        "The proposed_agent capabilities must be an object with skills [supplier_search], tools [web.fetch,event.emit], models [worker-ops]. " +
        "The proposed_agent permissions must be an object with can_read_scopes [division:ops-sourcing,project:*], can_write_scopes [division:ops-sourcing,event:*], allowed_tools [web.fetch,event.emit], denied_tools []. " +
        "The proposed_soul must use id " + $new_soul_id + ", agent_id " + $new_agent_id + ", identity IA Supplier Researcher verifies supplier evidence, mission Find and summarize supplier evidence for the ops sourcing manager, responsibilities [Find supplier source evidence, Summarize risks, Escalate unclear claims], operating_principles [Keep sources auditable], boundaries [Do not contact suppliers without approval], escalation_rules [Escalate purchase commitments to IA Ops Sourcing]. " +
        "After returning the lifecycle request, finish with status completed, no sub_tasks_created, no memory_candidates, and no tool_calls_requested."
      ),
      assigned_agent_id: "agent-ops-sourcing",
      acceptance_criteria: [
        "A create_agent lifecycle request is returned as typed JSON.",
        "The proposed employee stays approval-gated before human approval.",
        "No connector or web tool is requested for this organizational change."
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
  --arg task_id "$TASK_ID" \
  --arg request_id "$REQUEST_ID" \
  --arg new_agent_id "$NEW_AGENT_ID" \
  --arg new_soul_id "$NEW_SOUL_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg model_id "$TASK_RUNNER_MODEL_ID" \
  '
    (.trace_id == $trace_id) and
    (.project_id == $project_id) and
    (.runs | length == 1) and
    (.runs[0].task.id == $task_id) and
    ((.runs[0].agent_result.status == "completed") or (.runs[0].agent_result.status == "needs_review")) and
    (.runs[0].agent_result.tool_calls_requested == []) and
    (.runs[0].tool_results == []) and
    (.runs[0].lifecycle_requests_created | length == 1) and
    (.runs[0].lifecycle_requests_created[0].id == $request_id) and
    (.runs[0].lifecycle_requests_created[0].action == "create_agent") and
    (.runs[0].lifecycle_requests_created[0].requested_by_type == "agent") and
    (.runs[0].lifecycle_requests_created[0].requested_by_id == "agent-ops-sourcing") and
    (.runs[0].lifecycle_requests_created[0].status == "requested") and
    (.runs[0].lifecycle_requests_created[0].requires_human_approval == true) and
    (.runs[0].lifecycle_requests_created[0].proposed_agent.id == $new_agent_id) and
    (.runs[0].lifecycle_requests_created[0].proposed_agent.manager_id == "agent-ops-sourcing") and
    (.runs[0].lifecycle_requests_created[0].proposed_agent.division == "ops-sourcing") and
    (.runs[0].lifecycle_requests_created[0].proposed_soul.id == $new_soul_id) and
    (.runs[0].lifecycle_requests_created[0].proposed_soul.agent_id == $new_agent_id) and
    (.runs[0].agent_result.model_usage.provider_id == "provider-openrouter") and
    (.runs[0].agent_result.model_usage.model_id == $model_id) and
    (.runs[0].agent_result.model_usage.input_tokens > 0) and
    (.runs[0].agent_result.model_usage.output_tokens > 0) and
    (.runs[0].cost_records[0].provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[1].payload.provider_id == "provider-openrouter") and
    (.runs[0].model_call_events[1].payload.tool_result_count == 0) and
    (.runs[0].model_call_events[1].payload.failed_tool_result_count == 0) and
    (.runs[0].model_call_events[1].payload.failed_tool_names == []) and
    (.runs[0].model_call_events[1].payload.failed_tool_errors == [])
  ' >/dev/null

pre_approval_agent_status="$(
  curl -sS -o /dev/null -w "%{http_code}" "${STATE_SERVICE_URL}/agents/${NEW_AGENT_ID}"
)"
if [ "$pre_approval_agent_status" != "404" ]; then
  echo "Expected proposed agent to be absent before approval, got HTTP ${pre_approval_agent_status}" >&2
  exit 1
fi

requested_lifecycle="$(
  curl -fsS "${STATE_SERVICE_URL}/agent-lifecycle-requests?requested_by_id=agent-ops-sourcing&status=requested"
)"
printf "%s" "$requested_lifecycle" | jq -e \
  --arg request_id "$REQUEST_ID" \
  --arg new_agent_id "$NEW_AGENT_ID" \
  '
    ([.[] | select(.id == $request_id and .proposed_agent.id == $new_agent_id)] | length == 1)
  ' >/dev/null

decision_payload="$(
  jq -n \
    --arg request_id "$REQUEST_ID" \
    '{
      request_id: $request_id,
      status: "approved",
      decided_by_type: "user",
      decided_by_id: "live-lifecycle-reviewer",
      rationale: "Live E2E approval: scoped worker, bounded tools, manager assigned."
    }'
)"

decision_response="$(
  post_json "${STATE_SERVICE_URL}/agent-lifecycle-requests/${REQUEST_ID}/decisions" "$decision_payload"
)"
printf "%s" "$decision_response" | jq -e '
  (.status == "applied") and
  ([.events_emitted[].type] == ["approval.decided", "agent.created", "agent_soul.created"])
' >/dev/null

created_agent="$(
  curl -fsS "${STATE_SERVICE_URL}/agents/${NEW_AGENT_ID}"
)"
printf "%s" "$created_agent" | jq -e \
  --arg new_agent_id "$NEW_AGENT_ID" \
  '
    (.id == $new_agent_id) and
    (.status == "active") and
    (.manager_id == "agent-ops-sourcing") and
    (.model_policy_id == "policy-worker-default")
  ' >/dev/null

world_view="$(
  curl -fsS "${CONTROL_PLANE_URL}/agents/${NEW_AGENT_ID}/world-view"
)"
printf "%s" "$world_view" | jq -e \
  --arg new_agent_id "$NEW_AGENT_ID" \
  --arg new_soul_id "$NEW_SOUL_ID" \
  '
    (.agent_id == $new_agent_id) and
    (.manager_agent_id == "agent-ops-sourcing") and
    (.soul.id == $new_soul_id) and
    (.soul.agent_id == $new_agent_id)
  ' >/dev/null

events="$(
  curl -fsS "${STATE_SERVICE_URL}/events?trace_id=${TRACE_ID}"
)"
audits="$(
  curl -fsS "${STATE_SERVICE_URL}/audit-logs?trace_id=${TRACE_ID}"
)"
timeline="$(
  curl -fsS "${GATEWAY_URL}/projects/${PROJECT_ID}/timeline"
)"

printf "%s" "$events" | jq -e \
  --arg request_id "$REQUEST_ID" \
  --arg new_agent_id "$NEW_AGENT_ID" \
  '
    ([.[] | select(.type == "approval.requested" and .target == $request_id)] | length == 1) and
    ([.[] | select(.type == "approval.decided" and .target == $request_id)] | length == 1) and
    ([.[] | select(.type == "agent.created" and .target == $new_agent_id)] | length == 1) and
    ([.[] | select(.type == "agent_soul.created" and .target == $new_agent_id)] | length == 1)
  ' >/dev/null

printf "%s" "$audits" | jq -e \
  --arg request_id "$REQUEST_ID" \
  --arg new_agent_id "$NEW_AGENT_ID" \
  --arg new_soul_id "$NEW_SOUL_ID" \
  '
    ([.[] | select(.action == "agent_lifecycle_request.created" and .target_id == $request_id)] | length == 1) and
    ([.[] | select(.action == "agent_lifecycle_request.applied" and .target_id == $request_id)] | length == 1) and
    ([.[] | select(.action == "agent.created" and .target_id == $new_agent_id)] | length == 1) and
    ([.[] | select(.action == "agent_soul.created" and .target_id == $new_soul_id)] | length == 1)
  ' >/dev/null

printf "%s" "$timeline" | jq -e \
  --arg trace_id "$TRACE_ID" \
  '
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .input_tokens > 0 and .output_tokens > 0)] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "model_call.completed")] | length == 1)
  ' >/dev/null

jq -n \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg request_id "$REQUEST_ID" \
  --arg new_agent_id "$NEW_AGENT_ID" \
  --arg new_soul_id "$NEW_SOUL_ID" \
  --argjson batch "$batch_response" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    trace_id: $trace_id,
    lifecycle_request_id: $request_id,
    created_agent_id: $new_agent_id,
    created_soul_id: $new_soul_id,
    pre_approval_agent_absent: true,
    final_agent_status: "active",
    agent_status: $batch.runs[0].agent_result.status,
    model_usage: $batch.runs[0].cost_records[0]
  }'
