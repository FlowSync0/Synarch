#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
MEMORY_SERVICE_URL="${MEMORY_SERVICE_URL:-http://localhost:8030}"
PYTHON_BIN="${PYTHON:-python}"
RUN_ID="${RUN_ID:-$(date +%s)}"

ACTIVE_PROJECT_ID="project_live_active_scope_${RUN_ID}"
INACTIVE_PROJECT_ID="project_live_inactive_scope_${RUN_ID}"
TRACE_ID="trace_live_active_scope_${RUN_ID}"

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
    -H "X-Synarch-Actor-Id: live-compaction-scope-test" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload" >/dev/null
}

post_memory() {
  local payload="$1"
  curl -fsS -X POST "${MEMORY_SERVICE_URL}/memory-items" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null
}

post_gateway() {
  local path="$1"
  local payload="$2"
  curl -fsS -X POST "${GATEWAY_URL}/${path}" \
    -H "Content-Type: application/json" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}" \
    -d "$payload"
}

require_command curl
require_command jq

curl -fsS "${GATEWAY_URL}/healthz" >/dev/null
curl -fsS "${STATE_SERVICE_URL}/healthz" >/dev/null
curl -fsS "${MEMORY_SERVICE_URL}/healthz" >/dev/null

active_project_payload="$(
  jq -n \
    --arg id "$ACTIVE_PROJECT_ID" \
    '{
      id: $id,
      title: "Active compaction scope",
      goal: "Validate active workspace compaction planning.",
      owner_agent_id: "agent-ops-sourcing"
    }'
)"

inactive_project_payload="$(
  jq -n \
    --arg id "$INACTIVE_PROJECT_ID" \
    '{
      id: $id,
      title: "Inactive compaction scope",
      goal: "Validate inactive workspace exclusion.",
      owner_agent_id: "agent-ops-sourcing"
    }'
)"

active_workspace_payload="$(
  jq -n \
    --arg id "workspace_active_${RUN_ID}" \
    --arg project_id "$ACTIVE_PROJECT_ID" \
    '{
      id: $id,
      project_id: $project_id,
      name: "Active scope workspace",
      memory_scope: ("project:" + $project_id),
      allowed_agent_ids: ["agent-ops-sourcing"],
      active: true
    }'
)"

inactive_workspace_payload="$(
  jq -n \
    --arg id "workspace_inactive_${RUN_ID}" \
    --arg project_id "$INACTIVE_PROJECT_ID" \
    '{
      id: $id,
      project_id: $project_id,
      name: "Inactive scope workspace",
      memory_scope: ("project:" + $project_id),
      allowed_agent_ids: ["agent-ops-sourcing"],
      active: false
    }'
)"

post_state projects "$active_project_payload"
post_state projects "$inactive_project_payload"
post_state project-workspaces "$active_workspace_payload"
post_state project-workspaces "$inactive_workspace_payload"

for suffix in a b; do
  active_memory_payload="$(
    jq -n \
      --arg id "mem_active_${suffix}_${RUN_ID}" \
      --arg project_id "$ACTIVE_PROJECT_ID" \
      --arg content "$(printf "%080d" 0 | tr 0 A)" \
      '{
        id: $id,
        scope: ("project:" + $project_id),
        agent_id: "agent-ops-sourcing",
        project_id: $project_id,
        status: "approved",
        content: $content
      }'
  )"
  inactive_memory_payload="$(
    jq -n \
      --arg id "mem_inactive_${suffix}_${RUN_ID}" \
      --arg project_id "$INACTIVE_PROJECT_ID" \
      --arg content "$(printf "%080d" 0 | tr 0 B)" \
      '{
        id: $id,
        scope: ("project:" + $project_id),
        agent_id: "agent-ops-sourcing",
        project_id: $project_id,
        status: "approved",
        content: $content
      }'
  )"
  post_memory "$active_memory_payload"
  post_memory "$inactive_memory_payload"
done

active_plan_payload="$(
  jq -n \
    --arg project_id "$ACTIVE_PROJECT_ID" \
    '{project_id: $project_id, min_source_tokens: 10, max_source_items: 10, max_scopes: 5}'
)"
inactive_plan_payload="$(
  jq -n \
    --arg project_id "$INACTIVE_PROJECT_ID" \
    '{project_id: $project_id, min_source_tokens: 10, max_source_items: 10, max_scopes: 5}'
)"

active_plan="$(post_gateway memory-items/compaction-plan "$active_plan_payload")"
printf "%s" "$active_plan" | jq -e \
  --arg project_id "$ACTIVE_PROJECT_ID" \
  '
    (.planned_scope_count == 1) and
    (.items[0].project_id == $project_id) and
    (.items[0].scope == ("project:" + $project_id))
  ' >/dev/null

inactive_plan="$(post_gateway memory-items/compaction-plan "$inactive_plan_payload")"
printf "%s" "$inactive_plan" | jq -e \
  '(.planned_scope_count == 0) and (.items == [])' >/dev/null

active_tick="$(
  "$PYTHON_BIN" scripts/memory_compaction_tick.py \
    --gateway-url "$GATEWAY_URL" \
    --project-id "$ACTIVE_PROJECT_ID" \
    --min-source-tokens 10 \
    --max-source-items 10 \
    --max-scopes 5 \
    --trace-id "${TRACE_ID}_tick" \
    --timeout-seconds 30
)"
printf "%s" "$active_tick" | jq -e \
  '
    (.memory_compaction.planned_scope_count == 1) and
    (.memory_compaction.executed_scope_count == 1) and
    (.memory_compaction.compacted_scope_count == 1)
  ' >/dev/null

inactive_tick="$(
  "$PYTHON_BIN" scripts/memory_compaction_tick.py \
    --gateway-url "$GATEWAY_URL" \
    --project-id "$INACTIVE_PROJECT_ID" \
    --min-source-tokens 10 \
    --max-source-items 10 \
    --max-scopes 5 \
    --trace-id "${TRACE_ID}_inactive_tick" \
    --timeout-seconds 30
)"
printf "%s" "$inactive_tick" | jq -e \
  '
    (.memory_compaction.planned_scope_count == 0) and
    (.memory_compaction.executed_scope_count == 0)
  ' >/dev/null

duplicate_tick="$(
  "$PYTHON_BIN" scripts/memory_compaction_tick.py \
    --gateway-url "$GATEWAY_URL" \
    --project-id "$ACTIVE_PROJECT_ID" \
    --min-source-tokens 10 \
    --max-source-items 10 \
    --max-scopes 5 \
    --trace-id "${TRACE_ID}_duplicate_tick" \
    --timeout-seconds 30
)"
printf "%s" "$duplicate_tick" | jq -e \
  '
    (.memory_compaction.planned_scope_count == 0) and
    (.memory_compaction.executed_scope_count == 0)
  ' >/dev/null

inactive_memories="$(curl -fsS "${MEMORY_SERVICE_URL}/memory-items?project_id=${INACTIVE_PROJECT_ID}")"
printf "%s" "$inactive_memories" | jq -e \
  '([.[] | select(.metadata.kind == "compaction")] | length) == 0' >/dev/null

jq -n \
  --arg active_project_id "$ACTIVE_PROJECT_ID" \
  --arg inactive_project_id "$INACTIVE_PROJECT_ID" \
  --argjson active_tick "$active_tick" \
  --argjson inactive_tick "$inactive_tick" \
  --argjson duplicate_tick "$duplicate_tick" \
  '{
    passed: true,
    active_project_id: $active_project_id,
    inactive_project_id: $inactive_project_id,
    active_tick: $active_tick.memory_compaction,
    inactive_tick: $inactive_tick.memory_compaction,
    duplicate_tick: $duplicate_tick.memory_compaction
  }'
