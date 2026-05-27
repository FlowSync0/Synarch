# Synarch Development Quality Gates

This document defines how Synarch moves from skeleton to working product. The goal is not to
implement all nine conceptual layers at once. The goal is to add one executable slice at a time,
with a test proving that the new slice works before the next layer is expanded.

## Karpathy Guidelines Applied

Karpathy's recent "Software Is Changing (Again)" framing treats LLM applications as Software 3.0:
natural-language components must be engineered with the same discipline as normal code. For Synarch,
that means:

- Keep AI components on a leash: every autonomous step needs typed input, typed output, logs, and a
  deterministic fallback.
- Use generation plus verification: never accept an agent result just because it looks plausible.
- Make the next change concrete and small: one new behavior, one observable boundary, one test.
- Split every goal into debuggable tasks with acceptance criteria before execution.
- Build evals early: non-deterministic behavior needs scenario tests with expected outcomes.
- Prefer partial autonomy: agents propose and prepare; critical actions stay behind approval gates.

## Revised Build Order

The README's nine layers remain useful as an architecture map. For implementation, use these gates:

| Gate | Scope | Done When | Required Test |
| --- | --- | --- | --- |
| 0 | Repo hygiene | Install, lint, tests, CI run locally | `make verify` |
| 1 | Shared contracts | Pydantic contracts cover all cross-service payloads | contract tests |
| 2 | State and project model | Agents, projects, tasks, events persist in Postgres | repository integration tests |
| 3 | Control plane | Agent registry, permissions, and `LocalWorldView` are deterministic | control-plane tests |
| 4 | Goal to project slice | User goal becomes project, tasks, routing decision | cross-service integration test |
| 5 | Agent runtime stub | One deterministic division agent returns `AgentResult` | agent-runtime test |
| 6 | Memory baseline | Context assembly respects agent/project scope, token budget, and optional vector ranking | memory integration test |
| 7 | Event backbone | NATS publishes domain events and timeline can replay them | event integration test |
| 8 | Observability | Every request has trace ID across gateway, state, memory, runtime | trace assertion test |
| 9 | First real AI workflow | Finance invoice flow extracts JSON and flags exceptions | eval suite |
| 10 | Tool execution | Tool permission checks are enforced before execution | security integration test |

Do not add OpenViking, Cognee, LangGraph, Hermes wrappers, or a real LLM until the gate below it has
an executable test. Otherwise the project becomes hard to debug before the foundation is measurable.

## Test Taxonomy

- Contract tests: verify Pydantic schemas, enum values, serialization, and backwards compatibility.
- Unit tests: verify local deterministic code with no external service.
- Slice integration tests: verify multiple Synarch services through public APIs in one scenario.
- Infrastructure integration tests: verify Postgres, Redis, NATS, and OTEL with real dependencies.
- Evals: verify AI behavior on fixed scenarios, expected JSON, routing decisions, and refusal cases.
- Manual acceptance tests: only for UI ergonomics and human approval flows.

## Current Executable Slice

The current integration slice is:

```text
GoalEnvelope
  -> Gateway RoutingDecision
  -> State ProjectRecord + ProjectWorkspace + AgentProjectAssignment + TaskRecord
  -> Gateway-triggered ProjectComplexityReport + optional gateway-applied ProjectSplitApplication
  -> Control Plane LocalWorldView + active AgentSoul
  -> Lifecycle approval can create an agent with active AgentSoul in one auditable trace
  -> Lifecycle approval can update an agent and replace active AgentSoul in one auditable trace
  -> Memory Context Assembly
  -> Agent Runtime AgentResult
  -> Task Runner child TaskRecord persistence when an agent proposes sub_tasks_created
  -> Task Runner approval-gated lifecycle request persistence when an agent proposes org changes
  -> Optional bounded ready-task batch through Gateway /tasks/run-ready
  -> Atomic task claim through state-service start endpoint
  -> Expired task lease recovery before each bounded ready-task batch
  -> Retry backoff prevents immediate re-execution after a lease expiry
  -> Human task review can retry, cancel, or update dead-lettered work
  -> Optional scheduler worker loop for cron/server execution
  -> Durable scheduler.tick event and audit log for every batch, including empty ticks
  -> Gateway service health checks filtered by LocalWorldView with event and audit traces
  -> Model Gateway can return deterministic typed completions through ModelCompletionResponse
  -> Agent Runtime can call Model Gateway instead of directly owning provider-specific calls
  -> Durable connector jobs can be created, run-recorded, and stopped with event/audit traces
  -> Bounded connector-job tick records completed, failed, blocked, and skipped runs
  -> Gateway connector-job execution uses the existing tool gate before recording runs
  -> Authorized agents can create durable connector jobs through `connector.job.create`
  -> Authorized agents can inspect their own connector jobs through `connector.job.list`
  -> Task Runner can execute `connector.job.create` from an agent tool loop and return the job result to the agent
  -> Task Runner can execute `connector.job.stop` for an owned connector job and return the stopped job result to the agent
  -> Task Runner can run a bounded two-round, one-tool-per-round loop so an agent can list connector jobs before stopping one
  -> Webhook connector jobs can be triggered through Gateway with the same tool gate and traceable batch output
  -> Gateway connector-job batch execution records bounded runs plus empty tick traces
  -> Cron connector jobs update next_run_at after each run and are skipped until due
  -> Connector jobs can self-stop through run output or metadata.max_runs
  -> Failed connector jobs back off and can stop after metadata.max_failures
  -> Blocked connector job runs stop the job for human review instead of retrying forever
  -> Human assistance requests persist CAPTCHA, PDF review, external error, key decision, and manual-action blockers
  -> Authorized agents can create human assistance requests through `human.assistance.request`
  -> Gateway project briefs prioritize open human assistance requests as the next project action
  -> Gateway project briefs aggregate next action, reminders, blocked connector jobs, tasks, and recent events
  -> Frontend approval queue can answer or dismiss human assistance requests through traceable Gateway routes
  -> Frontend connector panel reads state-service connector jobs/runs through same-origin proxies
  -> Frontend connector controls run, stop, and resume jobs through Gateway with event/audit traces
  -> Frontend connector history reads audit logs and shows job runs/events/audits by trace_id
  -> Frontend project detail surfaces the Gateway project brief as the operational project guide
  -> Frontend project detail surfaces project-scoped human assistance evidence and can answer/dismiss requests
  -> Frontend project detail can launch the selected project's next ready task through `/tasks/run-ready`
  -> Frontend project brief next-action control routes to run, review, connector, assistance, or planning flows
  -> Gateway `/readiness` returns actionable ready/warning/blocked items without mutating state
  -> Frontend readiness panel shows manual config and operator actions from the Gateway report
  -> Gateway `/operator-actions` aggregates task review, credential, human assistance, and blocked connector work
  -> Frontend action center can focus the selected project on the required operator action
  -> Event Service timeline
```

Run it with:

```bash
make test-integration
```

Run the paid live OpenRouter/DeepSeek slice with:

```bash
make test-live-openrouter
```

This creates a real project/task, calls DeepSeek through `agent-runtime` -> `model-gateway`, persists
the result through the gateway, and asserts the timeline contains child tasks, task events, a
scheduler tick, scheduler audit, no skipped task claims, no lease recoveries, and a cost record. It
also seeds a project memory, requires the model to read it, persists a proposed memory candidate,
approves that candidate through the gateway, runs a follow-up task, and verifies the approved
candidate appears in the next task context. The same run also rejects a separate proposed memory item
and verifies it stays out of the follow-up task context. It also creates oversized approved source
memories, runs the gateway `compact-if-needed` threshold policy, approves the compacted item, runs a
real DeepSeek task, and verifies the task context contains the compacted source-ID summary while
excluding the oversized source memories. It is not part of `make verify` because it depends on
external provider availability and consumes real tokens.

Run the paid live model-gateway/DeepSeek slice with:

```bash
make test-live-model-gateway-openrouter
```

This starts `model-gateway` in OpenRouter mode, runs a Gateway scheduler batch through
`agent-runtime` in `model_gateway` mode, and asserts the returned `AgentResult`, `ModelUsage`,
timeline events, memory candidate, and cost record all preserve the same trace.

Run the paid live connector-job/DeepSeek slice with:

```bash
make test-live-connector-jobs-openrouter
```

This creates a real project, task, and two connector jobs, then requires DeepSeek to inspect state
through `connector.job.list` before stopping the owned active job through `connector.job.stop`. The
test asserts the other agent's job stays active and that the trace contains tool, stop, audit, and
cost records.

Run the paid live lifecycle/DeepSeek slice with:

```bash
make test-live-lifecycle-openrouter
```

This creates a real project and task, requires DeepSeek to return a typed `create_agent`
`lifecycle_requests_created` payload, verifies the proposed employee does not exist before human
approval, approves the request through state-service, and checks the new agent plus active
`AgentSoul` are visible through control-plane world view with trace, event, audit, and cost records.

Deterministic memory compaction and the threshold policy are covered by the normal backend tests.
The memory-service tests assert that only approved source memories are compacted, source IDs stay
visible in both content and structured metadata, compaction is skipped below threshold, and duplicate
compaction requests reuse the existing proposed or approved item without recompacting compacted
summaries as sources. The compaction-plan tests assert only overloaded non-compacted scopes are
planned. The gateway tests assert `memory.compacted` is emitted only when a compaction is actually
created.

Run one scheduler tick with:

```bash
make scheduler-tick
```

For a local server loop, use `make scheduler-loop`; it still calls bounded gateway batches, so every
loop has an explicit task limit and traceable result. For the Docker worker service, use:

```bash
make scheduler-worker
```

The worker is not started by default because it may consume provider tokens when the runtime is in
OpenRouter mode. Empty ticks are still recorded as `scheduler.tick` events and audit logs, which
makes cron/server execution debuggable without needing a task to run. Worker stdout is structured
JSON with `worker_id`, `tick`, `status`, timestamps, duration, and any tick error.
If another scheduler claims a task first, the batch skips that task ID and keeps looking for ready
work instead of failing the whole tick.
Before each batch, the gateway asks state-service to recover expired leases. Expired tasks are
requeued while attempts remain with `retry_after_at`, otherwise moved to `needs_review` with
`dead_letter_reason=lease_expired`. The scheduler ignores queued tasks whose retry backoff has not
elapsed, so a crash loop is visible instead of burning repeated model calls.
Reviewers can inspect `/tasks/review-queue` and apply `/tasks/{task_id}/review-decisions`; every
decision emits `task.reviewed` and writes an audit log.

State-service also exposes a generic durable PostgreSQL work queue for maintenance and integration
jobs that should not be modeled as project tasks yet:

```bash
curl -X POST http://localhost:8020/work-queue/claim \
  -H 'Content-Type: application/json' \
  -d '{"queue_name":"reminders","worker_id":"worker-reminders","limit":1}'
```

`/work-queue/items` persists JSON payloads, priority, run-after time, attempt count, max attempts,
lease owner, lease expiry, result, and last error. `/work-queue/claim` atomically moves ready items
to `running` with a lease through conditional state updates. `/work-queue/items/{id}/complete` clears
the lease and stores the result. `/work-queue/items/{id}/fail` requeues or dead-letters depending on
attempt count. `/work-queue/recover-expired-leases` requeues expired running items or dead-letters
exhausted ones. Every queue mutation writes an audit log.
`/work-queue/items/{id}/review-decisions` lets an operator retry a failed/dead-lettered item or
dead-letter an active queued/running/failed item; the decision writes `work_queue.reviewed`.

A safe generic worker is available for queues that only need durable claim/complete/fail behavior:

```bash
make work-queue-tick SYNARCH_WORK_QUEUE_NAME=reminders
```

`python -m synarch_state_service.work_queue_worker --loop` can run continuously, or through
`docker compose --profile worker up -d work-queue-worker`. The first supported payload actions are
`noop` and `log`; unknown actions are failed through the durable queue path and dead-lettered instead
of being executed speculatively.
The `/app` workspace includes a work-queue panel that reads these same records through the Next
state-service proxy, displays per-status counts, and can enqueue safe `log` items for operator
smoke checks. The same panel can retry dead-lettered/failed items and dead-letter queued/running
items.

Run one connector-job batch with:

```bash
make connector-job-tick
```

For a local connector-job loop, use `make connector-job-loop`. For the Docker worker service, use:

```bash
make connector-job-worker
```

This worker is not started by default. Each tick calls Gateway `/connector-jobs/run-ready` with an
explicit `max_jobs` limit. Gateway only selects connector jobs whose `next_run_at` is empty or due.
The worker writes structured JSON stdout with run counts, completed/failed/blocked/skipped counts,
timestamps, duration, and transient errors.

Connector jobs can stop themselves without a separate manual request when a recorded run outputs
`stop_condition_met: true` or `stop_job: true`. A job can also declare `metadata.max_runs` to stop a
bounded follow-up loop after N recorded runs.

Failed connector runs can use `metadata.failure_cooldown_seconds` to delay the next retry. A job can
also declare `metadata.max_failures` to stop after a bounded number of failed runs.

Blocked connector runs stop the job immediately with a human-review reason, so CAPTCHA, access, or
credential blocks do not loop indefinitely. The state-service connector job list can be filtered by
`last_run_status=blocked` for review surfaces and monitors.

Agents must use `human.assistance.request` when the next step depends on a human action or
judgment: CAPTCHA, login/manual account action, ambiguous provider error, PDF/document verification,
or a key business decision. The request is durable, scoped to project/task/agent, emits
`human_assistance.requested`, and writes an audit log. A human can answer or dismiss it through
Gateway; resolution emits `human_assistance.resolved`, writes an audit log, and keeps the project
brief focused on the unresolved blocker until it is handled. If the request is linked to a blocked
or reviewable task, an answered request requeues the task with enough remaining attempts to retry;
a dismissed request keeps the task in `needs_review` with `dead_letter_reason=human_assistance_dismissed`.
The retry context includes `task.result.last_human_assistance_resolution`, and the agent prompt
explicitly treats that field as fresh human input.
Gateway also creates this durable request automatically when an authorized tool returns
`requires_human_review=true`, so CAPTCHA or access blocks are not lost if the model fails to ask
explicitly.
`make test-live-web-extract-blocked-openrouter` verifies this end-to-end with a real DeepSeek run:
the blocked `web.extract` output includes the durable request ID, the request appears through
Gateway, answering it requeues the linked task, and the timeline contains the tool, human-assistance,
task-review, audit, and cost records under the same trace.

Run one memory compaction policy tick for a known scope with:

```bash
SYNARCH_MEMORY_COMPACTION_SCOPE=project:project_demo make memory-compaction-tick
```

For a local loop, use `make memory-compaction-loop`. For the Docker worker service, use:

```bash
SYNARCH_MEMORY_COMPACTION_SCOPE=project:project_demo make memory-compaction-worker
```

When a scope is provided, the worker calls Gateway `compact-if-needed` directly, so duplicate
suppression and `memory.compacted` event emission stay centralized in the gateway and
memory-service.

Omit `SYNARCH_MEMORY_COMPACTION_SCOPE` to let the worker call Gateway
`/memory-items/compaction-plan` first, then execute `compact-if-needed` for each planned scope.
Gateway fills the plan request with active project workspace scopes from state-service. Use
`SYNARCH_MEMORY_COMPACTION_PROJECT_ID` to constrain that discovery to one project.

Run the active/inactive workspace scope check with:

```bash
PYTHON=./.venv/bin/python scripts/live_memory_compaction_scope_e2e.sh
```

The memory-service also supports optional vector ranking inside the same scoped context contract:
send `query_embedding` on `/context/assemble` and only already-visible memory items are re-ranked
by cosine similarity. Without `query_embedding`, context assembly uses the deterministic scope/time
ranking.

Run the live vector-ranking check with:

```bash
scripts/live_memory_vector_context_e2e.sh
```

When `TASK_RUNNER_EMBEDDING_PROVIDER_ID=provider-openrouter` and
`TASK_RUNNER_EMBEDDING_MODEL_ID=openai/text-embedding-3-small` are set, Gateway generates a real
OpenRouter query embedding before `/context/assemble` and embeds new memory candidates before
persistence. It strips query and item embeddings before sending `memory_context` to the chat runtime
so vector retrieval does not inflate prompt tokens.

Run the live task-embedding check with:

```bash
scripts/live_openrouter_task_embedding_e2e.sh
```

Approved memories created before embeddings were configured can be indexed later through Gateway
`/memory-items/embedding-backfill`. The endpoint is bounded by `max_items`, only touches matching
memories that have no embedding, and emits `memory.embedding_backfilled` for each updated item.

Run one embedding backfill tick with:

```bash
SYNARCH_MEMORY_EMBEDDING_PROJECT_ID=project_demo make memory-embedding-backfill-tick
```

For a local loop, use `make memory-embedding-backfill-loop`. For the Docker worker service, use:

```bash
SYNARCH_MEMORY_EMBEDDING_PROJECT_ID=project_demo make memory-embedding-backfill-worker
```

Run the live OpenRouter backfill check with:

```bash
scripts/live_memory_embedding_backfill_e2e.sh
```

Project memory can cross project boundaries only through active workspace bridges. Gateway expands
active `ProjectWorkspace.bridge_project_ids` into `MemoryContext.allowed_project_ids`, and
memory-service still rejects project memory whose project ID is not explicitly allowed.
Minimal graph retrieval uses `MemoryItem.metadata.related_memory_ids`. Memory-service expands those
links after a selected memory, bounded by `MemoryContext.max_related_items`, and still applies the
same visibility and token-budget checks to every related item.
Gateway relation proposals create `proposed` memory items with `metadata.kind` set to
`memory_relation_proposal`. Applying a proposal requires it to be approved first, then Gateway merges
the approved related IDs into the source memory and emits `memory.relation_applied`. Relation
proposal memory items are excluded from runtime context assembly even after approval.

Run the bridge/graph isolation check with:

```bash
scripts/live_memory_bridge_scope_e2e.sh
```

This is intentionally not a full production workflow. It is the first contract-compatible path across
the current skeleton.

## Stack Decision Rules

- FastAPI remains the service boundary while contracts are still moving. Its `TestClient` supports
  direct app testing without binding sockets, which keeps early integration tests fast.
- LangGraph should be introduced when orchestration needs checkpoints, resume, human approval, or
  time-travel debugging. Its value is durable execution, not decorative multi-agent structure.
- NATS should become the event backbone after the state model is stable. Core pub/sub is enough first;
  JetStream is only needed when replay, durability, or work queues become required.
- OpenTelemetry should be added before real agents. Debugging AI behavior without trace IDs is not
  acceptable once model calls or tools are involved.
- OpenViking is a candidate for hierarchical context once the memory service interface is stable.
  Its filesystem-style context and L0/L1/L2 loading fit Synarch's context paging problem.
- Cognee should wait until there is a real need for graph reasoning, entity relations, and provenance
  across documents. It is likely useful, but it is heavier than a pgvector baseline.

## Definition Of Done For Any New Layer

- Public payloads are represented in `shared/models`.
- The layer exposes health and one real domain endpoint.
- The layer emits or records an event for every state-changing action.
- The layer has at least one unit or contract test.
- Any cross-layer behavior has an integration test.
- Failure behavior is explicit: status code, error payload, retry/approval policy.
- Documentation names inputs, outputs, dependencies, and limits.

## First Product Workflow To Build

The strongest first vertical workflow from the research note is Finance invoice intake:

```text
Upload invoice
  -> OCR/extraction placeholder
  -> structured invoice JSON
  -> VAT and duplicate checks
  -> proposed accounting classification
  -> human approval on exceptions
  -> event timeline and memory candidate
```

This is narrow enough to test properly, useful enough to validate the product, and representative of
the architecture: data ingestion, memory, permissions, tools, events, observability, and UI status.

## References

- Karpathy / Software 3.0 framing: https://conffab.com/elsewhere/andrej-karpathy-software-is-changing-again/
- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- NATS docs: https://docs.nats.io/
- OpenTelemetry FastAPI instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
- OpenViking repository: https://github.com/volcengine/OpenViking
- Cognee docs: https://docs.cognee.ai/
