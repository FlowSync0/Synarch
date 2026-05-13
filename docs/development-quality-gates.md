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
| 6 | Memory baseline | Context assembly respects agent/project scope and token budget | memory integration test |
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
  -> Optional bounded ready-task batch through Gateway /tasks/run-ready
  -> Atomic task claim through state-service start endpoint
  -> Expired task lease recovery before each bounded ready-task batch
  -> Retry backoff prevents immediate re-execution after a lease expiry
  -> Human task review can retry, cancel, or update dead-lettered work
  -> Optional scheduler worker loop for cron/server execution
  -> Durable scheduler.tick event and audit log for every batch, including empty ticks
  -> Gateway service health checks filtered by LocalWorldView with event and audit traces
  -> Durable connector jobs can be created, run-recorded, and stopped with event/audit traces
  -> Bounded connector-job tick records explicit skipped runs until real adapters are wired
  -> Gateway connector-job execution uses the existing tool gate before recording runs
  -> Gateway connector-job batch execution records bounded runs plus empty tick traces
  -> Cron connector jobs update next_run_at after each run and are skipped until due
  -> Connector jobs can self-stop through run output or metadata.max_runs
  -> Failed connector jobs back off and can stop after metadata.max_failures
  -> Frontend connector panel reads state-service connector jobs/runs through same-origin proxies
  -> Frontend connector controls run, stop, and resume jobs through Gateway with event/audit traces
  -> Frontend connector history reads audit logs and shows job runs/events/audits by trace_id
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

This creates a real project/task, calls DeepSeek through `agent-runtime`, persists the result through
the gateway, and asserts the timeline contains child tasks, task events, a scheduler tick, scheduler
audit, no skipped task claims, no lease recoveries, and a cost record. It also seeds a project memory,
requires the model to read it, persists a proposed memory candidate, approves that candidate through
the gateway, runs a follow-up task, and verifies the approved candidate appears in the next task
context. The same run also rejects a separate proposed memory item and verifies it stays out of the
follow-up task context. It also creates oversized approved source memories, runs the gateway
`compact-if-needed` threshold policy, approves the compacted item, runs a real DeepSeek task, and
verifies the task context contains the compacted source-ID summary while excluding the oversized
source memories. It is not part of `make verify` because it depends on external provider
availability and consumes real tokens.

Deterministic memory compaction and the threshold policy are covered by the normal backend tests.
The memory-service tests assert that only approved source memories are compacted, source IDs stay
visible, and compaction is skipped below threshold; the gateway tests assert `memory.compacted` is
emitted only when a compaction is actually created.

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
The worker writes structured JSON stdout with run counts, completed/failed/skipped counts,
timestamps, duration, and transient errors.

Connector jobs can stop themselves without a separate manual request when a recorded run outputs
`stop_condition_met: true` or `stop_job: true`. A job can also declare `metadata.max_runs` to stop a
bounded follow-up loop after N recorded runs.

Failed connector runs can use `metadata.failure_cooldown_seconds` to delay the next retry. A job can
also declare `metadata.max_failures` to stop after a bounded number of failed runs.

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
