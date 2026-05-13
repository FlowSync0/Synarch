#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STATE_SERVICE_URL="${STATE_SERVICE_URL:-http://localhost:8020}"
MEMORY_SERVICE_URL="${MEMORY_SERVICE_URL:-http://localhost:8030}"
RUN_ID="${RUN_ID:-$(date +%s)}"

PROJECT_ID="project_live_openrouter_${RUN_ID}"
TASK_ID="task_live_openrouter_${RUN_ID}"
FOLLOWUP_TASK_ID="task_live_openrouter_followup_${RUN_ID}"
REJECTED_MEMORY_ID="memory_live_openrouter_rejected_${RUN_ID}"
COMPACTION_PROJECT_ID="proj_compact_${RUN_ID}"
COMPACTION_TASK_ID="task_compact_${RUN_ID}"
COMPACTION_SOURCE_ID_A="mem_compact_a_${RUN_ID}"
COMPACTION_SOURCE_ID_B="mem_compact_b_${RUN_ID}"
TRACE_ID="trace_live_openrouter_${RUN_ID}"
MARKER="SYNARCH_LIVE_OK_${RUN_ID}"
REJECTED_MARKER="SYNARCH_REJECTED_MEMORY_${RUN_ID}"
COMPACTION_MARKER="SYNARCH_COMPACTED_CONTEXT_${RUN_ID}"

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

patch_json() {
  local url="$1"
  local payload="$2"
  curl -fsS -X PATCH "$url" \
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
curl -fsS "${MEMORY_SERVICE_URL}/healthz" >/dev/null

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
    --arg marker "$MARKER" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Break down supplier outreach workflow",
      description: ("Create the next small debuggable tasks for finding and contacting suppliers for a motor in China. Return status completed. Include the exact memory marker " + $marker + " in summary. Return at least two sub_tasks_created with explicit acceptance criteria. In depends_on, refer to previous child tasks by exact title only. Return at least one memory_candidates entry summarizing what should be remembered from this run."),
      assigned_agent_id: "agent-ops-sourcing",
      acceptance_criteria: [
        "The live model result is parsed into AgentResult.",
        "At least two child tasks are persisted.",
        "Every child task has acceptance criteria and a valid dependency list.",
        "The model result includes the live memory marker and at least one memory candidate."
      ],
      sequence: 1
    }'
)"

memory_payload="$(
  jq -n \
    --arg project_id "$PROJECT_ID" \
    --arg marker "$MARKER" \
    '{
      scope: ("project:" + $project_id),
      agent_id: "agent-ops-sourcing",
      project_id: $project_id,
      status: "approved",
      content: ("Live OpenRouter memory proof marker: " + $marker + ". The final summary must include this exact marker.")
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
  --arg marker "$MARKER" \
  '
    (.trace_id == $trace_id) and
    (.task.id == $task_id) and
    (.task.project_id == $project_id) and
    (.task.status == "completed") and
    (.agent_result.status == "completed") and
    (.agent_result.summary | type == "string" and contains($marker)) and
    (.agent_result.actions_taken | type == "array" and length > 0) and
    (.agent_result.sub_tasks_created | type == "array" and length >= 2) and
    (.agent_result.memory_candidates | type == "array" and length >= 1) and
    ((.memory_context.items | type) == "array") and
    (any(.memory_context.items[]; .content | contains($marker))) and
    (.memory_events | type == "array" and length >= 1) and
    (all(.memory_events[]; .type == "memory.candidate_created")) and
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
    ([.events[] | select(.trace_id == $trace_id and .type == "memory.candidate_created" and .payload.task_id == $task_id)] | length >= 1) and
    ([.audit_logs[] | select(.trace_id == $trace_id and .action == "scheduler.tick")] | length == 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .model_id == "deepseek/deepseek-v4-flash" and .input_tokens > 0 and .output_tokens > 0)] | length == 1)
  ' >/dev/null

memory_items="$(
  curl -fsS "${MEMORY_SERVICE_URL}/memory-items?project_id=${PROJECT_ID}"
)"

printf "%s" "$memory_items" | jq -e \
  --arg marker "$MARKER" \
  '
    ([.[] | select(.status == "approved" and (.content | contains($marker)))] | length == 1) and
    ([.[] | select(.status == "proposed")] | length >= 1)
  ' >/dev/null

approved_candidate_memory_id="$(printf "%s" "$run_response" | jq -r '.memory_events[0].payload.memory_id')"
if [ -z "$approved_candidate_memory_id" ] || [ "$approved_candidate_memory_id" = "null" ]; then
  echo "Could not find proposed memory id in first run response" >&2
  exit 1
fi

patch_json "${GATEWAY_URL}/memory-items/${approved_candidate_memory_id}/status" \
  '{"status":"approved"}' >/dev/null

rejected_memory_payload="$(
  jq -n \
    --arg id "$REJECTED_MEMORY_ID" \
    --arg project_id "$PROJECT_ID" \
    --arg marker "$REJECTED_MARKER" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      agent_id: "agent-ops-sourcing",
      project_id: $project_id,
      status: "proposed",
      content: ("Rejected live memory marker that must stay out of future context: " + $marker)
    }'
)"

post_json "${MEMORY_SERVICE_URL}/memory-items" "$rejected_memory_payload" >/dev/null
patch_json "${GATEWAY_URL}/memory-items/${REJECTED_MEMORY_ID}/status" \
  '{"status":"rejected"}' >/dev/null

followup_task_payload="$(
  jq -n \
    --arg id "$FOLLOWUP_TASK_ID" \
    --arg project_id "$PROJECT_ID" \
    --arg memory_id "$approved_candidate_memory_id" \
    --arg rejected_memory_id "$REJECTED_MEMORY_ID" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Verify approved memory is injected",
      description: ("Return status completed after inspecting memory_context. Do not create child tasks. The approved memory id that must be present in memory_context is " + $memory_id + ". The rejected memory id must not be present in memory_context: " + $rejected_memory_id + "."),
      assigned_agent_id: "agent-ops-sourcing",
      acceptance_criteria: [
        "The approved memory candidate from the previous run is present in memory_context.",
        "The rejected memory candidate is absent from memory_context.",
        "The task completes without creating child tasks."
      ],
      sequence: 2
    }'
)"

post_json "${STATE_SERVICE_URL}/tasks" "$followup_task_payload" >/dev/null

followup_run_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/${FOLLOWUP_TASK_ID}/run" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$followup_run_response" | jq -e \
  --arg task_id "$FOLLOWUP_TASK_ID" \
  --arg memory_id "$approved_candidate_memory_id" \
  --arg rejected_memory_id "$REJECTED_MEMORY_ID" \
  '
    (.task.id == $task_id) and
    (.task.status == "completed") and
    (.agent_result.status == "completed") and
    (.memory_context.items | type == "array") and
    (any(.memory_context.items[]; .id == $memory_id)) and
    (all(.memory_context.items[]; .id != $rejected_memory_id)) and
    (.cost_records[0].provider_id == "provider-openrouter") and
    (.cost_records[0].model_id == "deepseek/deepseek-v4-flash") and
    (.cost_records[0].input_tokens > 0) and
    (.cost_records[0].output_tokens > 0)
  ' >/dev/null

timeline_after_memory_review="$(
  curl -fsS "${GATEWAY_URL}/projects/${PROJECT_ID}/timeline"
)"

printf "%s" "$timeline_after_memory_review" | jq -e \
  --arg trace_id "$TRACE_ID" \
  --arg memory_id "$approved_candidate_memory_id" \
  --arg rejected_memory_id "$REJECTED_MEMORY_ID" \
  --arg followup_task_id "$FOLLOWUP_TASK_ID" \
  '
    ([.events[] | select(.trace_id == $trace_id and .type == "memory.status_updated" and .payload.memory_id == $memory_id and .payload.status == "approved")] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "memory.status_updated" and .payload.memory_id == $rejected_memory_id and .payload.status == "rejected")] | length == 1) and
    ([.tasks[] | select(.id == $followup_task_id and .status == "completed")] | length == 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .model_id == "deepseek/deepseek-v4-flash" and .input_tokens > 0 and .output_tokens > 0)] | length >= 2)
  ' >/dev/null

memory_items_after_review="$(
  curl -fsS "${MEMORY_SERVICE_URL}/memory-items?project_id=${PROJECT_ID}"
)"

printf "%s" "$memory_items_after_review" | jq -e \
  --arg rejected_memory_id "$REJECTED_MEMORY_ID" \
  '
    ([.[] | select(.id == $rejected_memory_id and .status == "rejected")] | length == 1)
  ' >/dev/null

compaction_project_payload="$(
  jq -n \
    --arg id "$COMPACTION_PROJECT_ID" \
    '{
      id: $id,
      title: "Live compacted memory context",
      goal: "Verify approved compacted memory can replace oversized source facts in a live model run.",
      owner_agent_id: "agent-ops-sourcing"
    }'
)"

post_json "${STATE_SERVICE_URL}/projects" "$compaction_project_payload" >/dev/null

long_source_a="$(
  printf "Large source A: supplier qualification requires checking MOQ, export terms, certifications, and response SLA. "
  printf "%06000d" 0 | tr "0" "A"
)"
long_source_b="$(
  printf "Large source B: outreach must track platform, contact channel, follow-up date, quoted price, and human escalation reason. "
  printf "%06000d" 0 | tr "0" "B"
)"

source_memory_payload_a="$(
  jq -n \
    --arg id "$COMPACTION_SOURCE_ID_A" \
    --arg project_id "$COMPACTION_PROJECT_ID" \
    --arg content "$long_source_a" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      agent_id: "agent-ops-sourcing",
      project_id: $project_id,
      status: "approved",
      content: $content
    }'
)"
source_memory_payload_b="$(
  jq -n \
    --arg id "$COMPACTION_SOURCE_ID_B" \
    --arg project_id "$COMPACTION_PROJECT_ID" \
    --arg content "$long_source_b" \
    '{
      id: $id,
      scope: ("project:" + $project_id),
      agent_id: "agent-ops-sourcing",
      project_id: $project_id,
      status: "approved",
      content: $content
    }'
)"

curl -fsS -X POST "${MEMORY_SERVICE_URL}/memory-items" \
  -H "Content-Type: application/json" \
  -d "$source_memory_payload_a" >/dev/null
curl -fsS -X POST "${MEMORY_SERVICE_URL}/memory-items" \
  -H "Content-Type: application/json" \
  -d "$source_memory_payload_b" >/dev/null

compaction_policy_payload="$(
  jq -n \
    --arg project_id "$COMPACTION_PROJECT_ID" \
    '{
      scope: ("project:" + $project_id),
      agent_id: "agent-ops-sourcing",
      project_id: $project_id,
      status: "proposed",
      min_source_tokens: 2400,
      max_source_items: 10,
      max_summary_chars: 200
    }'
)"

compaction_response="$(post_json "${GATEWAY_URL}/memory-items/compact-if-needed" "$compaction_policy_payload")"
compacted_memory_id="$(printf "%s" "$compaction_response" | jq -r '.compaction.compacted_item.id')"
if [ -z "$compacted_memory_id" ] || [ "$compacted_memory_id" = "null" ]; then
  echo "Could not find compacted memory id in compaction response" >&2
  exit 1
fi

printf "%s" "$compaction_response" | jq -e \
  --arg source_a "$COMPACTION_SOURCE_ID_A" \
  --arg source_b "$COMPACTION_SOURCE_ID_B" \
  '
    (.compaction_needed == true) and
    (.reason == "source_tokens_exceed_threshold") and
    (.threshold_tokens == 2400) and
    (.compaction.compacted_item.status == "proposed") and
    (.source_memory_ids == [$source_a, $source_b]) and
    (.source_count == 2) and
    (.source_tokens > 2400) and
    (.compaction.compacted_item.content | contains("Source memory ids: " + $source_a + ", " + $source_b))
  ' >/dev/null

duplicate_compaction_response="$(post_json "${GATEWAY_URL}/memory-items/compact-if-needed" "$compaction_policy_payload")"

printf "%s" "$duplicate_compaction_response" | jq -e \
  --arg compacted_memory_id "$compacted_memory_id" \
  --arg source_a "$COMPACTION_SOURCE_ID_A" \
  --arg source_b "$COMPACTION_SOURCE_ID_B" \
  '
    (.compaction_needed == false) and
    (.reason == "matching_compaction_exists") and
    (.existing_compacted_item.id == $compacted_memory_id) and
    (.source_memory_ids == [$source_a, $source_b]) and
    (.compaction == null)
  ' >/dev/null

patch_json "${GATEWAY_URL}/memory-items/${compacted_memory_id}/status" \
  '{"status":"approved"}' >/dev/null

compaction_task_payload="$(
  jq -n \
    --arg id "$COMPACTION_TASK_ID" \
    --arg project_id "$COMPACTION_PROJECT_ID" \
    --arg compacted_memory_id "$compacted_memory_id" \
    --arg source_a "$COMPACTION_SOURCE_ID_A" \
    --arg source_b "$COMPACTION_SOURCE_ID_B" \
    --arg marker "$COMPACTION_MARKER" \
    '{
      id: $id,
      project_id: $project_id,
      title: "Verify compacted memory reaches the AI employee",
      description: ("Return status completed. Inspect memory_context. Do not create child tasks. The summary must include marker " + $marker + ", compacted memory id " + $compacted_memory_id + ", and both source memory ids " + $source_a + " and " + $source_b + "."),
      assigned_agent_id: "agent-ops-sourcing",
      acceptance_criteria: [
        "The compacted memory item is present in memory_context.",
        "The oversized source memory items are absent from memory_context.",
        "The summary mentions the compacted item and both source IDs."
      ],
      sequence: 1
    }'
)"

post_json "${STATE_SERVICE_URL}/tasks" "$compaction_task_payload" >/dev/null

compaction_run_response="$(
  curl -fsS -X POST "${GATEWAY_URL}/tasks/${COMPACTION_TASK_ID}/run" \
    -H "X-Synarch-Trace-Id: ${TRACE_ID}"
)"

printf "%s" "$compaction_run_response" | jq -e \
  --arg task_id "$COMPACTION_TASK_ID" \
  --arg compacted_memory_id "$compacted_memory_id" \
  --arg source_a "$COMPACTION_SOURCE_ID_A" \
  --arg source_b "$COMPACTION_SOURCE_ID_B" \
  --arg marker "$COMPACTION_MARKER" \
  '
    (.task.id == $task_id) and
    (.task.status == "completed") and
    (.agent_result.status == "completed") and
    (.memory_context.items | type == "array") and
    (any(.memory_context.items[]; .id == $compacted_memory_id and (.content | contains("Source memory ids: " + $source_a + ", " + $source_b)))) and
    (all(.memory_context.items[]; .id != $source_a and .id != $source_b)) and
    (.agent_result.summary | contains($marker)) and
    (.agent_result.summary | contains($compacted_memory_id)) and
    (.agent_result.summary | contains($source_a)) and
    (.agent_result.summary | contains($source_b)) and
    (.cost_records[0].provider_id == "provider-openrouter") and
    (.cost_records[0].model_id == "deepseek/deepseek-v4-flash") and
    (.cost_records[0].input_tokens > 0) and
    (.cost_records[0].output_tokens > 0)
  ' >/dev/null

compaction_timeline="$(
  curl -fsS "${GATEWAY_URL}/projects/${COMPACTION_PROJECT_ID}/timeline"
)"

printf "%s" "$compaction_timeline" | jq -e \
  --arg trace_id "$TRACE_ID" \
  --arg compacted_memory_id "$compacted_memory_id" \
  --arg task_id "$COMPACTION_TASK_ID" \
  '
    ([.events[] | select(.trace_id == $trace_id and .type == "memory.compacted" and .payload.memory_id == $compacted_memory_id)] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "memory.status_updated" and .payload.memory_id == $compacted_memory_id and .payload.status == "approved")] | length == 1) and
    ([.events[] | select(.trace_id == $trace_id and .type == "model_call.started" and .payload.task_id == $task_id and (.payload.memory_item_ids | index($compacted_memory_id) != null))] | length == 1) and
    ([.tasks[] | select(.id == $task_id and .status == "completed")] | length == 1) and
    ([.cost_records[] | select(.trace_id == $trace_id and .provider_id == "provider-openrouter" and .model_id == "deepseek/deepseek-v4-flash" and .input_tokens > 0 and .output_tokens > 0)] | length == 1)
  ' >/dev/null

printf "%s" "$run_response" | jq \
  --arg project_id "$PROJECT_ID" \
  --arg task_id "$TASK_ID" \
  --arg followup_task_id "$FOLLOWUP_TASK_ID" \
  --arg compaction_project_id "$COMPACTION_PROJECT_ID" \
  --arg compaction_task_id "$COMPACTION_TASK_ID" \
  --arg trace_id "$TRACE_ID" \
  --arg marker "$MARKER" \
  --arg approved_memory_id "$approved_candidate_memory_id" \
  --arg rejected_memory_id "$REJECTED_MEMORY_ID" \
  --arg compacted_memory_id "$compacted_memory_id" \
  --arg source_a "$COMPACTION_SOURCE_ID_A" \
  --arg source_b "$COMPACTION_SOURCE_ID_B" \
  --argjson followup_run "$followup_run_response" \
  --argjson compaction_run "$compaction_run_response" \
  --arg stop_reason "$(printf "%s" "$batch_response" | jq -r '.stop_reason')" \
  --arg scheduler_event_id "$(printf "%s" "$batch_response" | jq -r '.scheduler_event.id')" \
  --arg scheduler_audit_id "$(printf "%s" "$batch_response" | jq -r '.scheduler_audit_log.id')" \
  '{
    passed: true,
    project_id: $project_id,
    task_id: $task_id,
    followup_task_id: $followup_task_id,
    compaction_project_id: $compaction_project_id,
    compaction_task_id: $compaction_task_id,
    trace_id: $trace_id,
    marker: $marker,
    approved_memory_id: $approved_memory_id,
    rejected_memory_id: $rejected_memory_id,
    compacted_memory_id: $compacted_memory_id,
    compacted_source_memory_ids: [$source_a, $source_b],
    batch_stop_reason: $stop_reason,
    scheduler_event_id: $scheduler_event_id,
    scheduler_audit_id: $scheduler_audit_id,
    task_status: .task.status,
    agent_status: .agent_result.status,
    followup_task_status: $followup_run.task.status,
    followup_agent_status: $followup_run.agent_result.status,
    compaction_task_status: $compaction_run.task.status,
    compaction_agent_status: $compaction_run.agent_result.status,
    followup_memory_context_items: ($followup_run.memory_context.items | length),
    compaction_memory_context_items: ($compaction_run.memory_context.items | length),
    memory_context_items: (.memory_context.items | length),
    memory_candidates: (.agent_result.memory_candidates | length),
    memory_events: (.memory_events | length),
    created_sub_tasks: [.created_sub_tasks[] | {id, title, depends_on, acceptance_criteria_count: (.acceptance_criteria | length)}],
    model_usage: .cost_records[0]
  }'
