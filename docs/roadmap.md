# Synarch Roadmap

Last updated: 2026-05-13

This roadmap is the operating map for Synarch. The README explains the vision, and
`docs/development-quality-gates.md` defines the verification discipline. This document answers:
where are we now, what is next, and how each of the nine layers becomes real without turning the
project into an untestable multi-agent prototype.

## Current Reality

Synarch is currently a clean executable skeleton, not yet a durable AI company runtime.

- Backend services exist as FastAPI boundaries: gateway, control-plane, state-service,
  memory-service, event-service, and agent-runtime.
- Shared Pydantic contracts exist for goals, projects, tasks, agents, memory, events, tools,
  model providers, model policies, costs, audit logs, lifecycle requests, project workspaces, and
  project split requests.
- The state-service exposes endpoints for company state, model routing state, cost records, audit
  logs, task results, and lifecycle requests through in-memory or PostgreSQL repositories.
- PostgreSQL schema coverage is implemented in `packages/state-service/migrations/0001_initial.sql`.
- A Next.js 16 / Tailwind CSS 4 dashboard exists. Projects, agents, lifecycle approvals, and
  timeline events now read backend APIs through TanStack Query and Next API proxies, with sample
  fallbacks when services are offline.
- `make PYTHON=.venv\Scripts\python.exe verify` passes locally on Windows.

The product is therefore testable through code, APIs, and the first live UI slices. It is not yet a
complete live interface because cost, health, and goal submission flows are not yet fully wired
through the dashboard.

## Status Legend

- `Done`: implemented, tested, and part of the executable baseline.
- `Partial`: a boundary or contract exists, but important behavior is missing.
- `Next`: the active engineering priority.
- `Later`: intentionally delayed until lower layers are measurable.
- `Blocked`: waiting on a prerequisite decision or layer.

## Nine-Layer Status

| Layer | Status | What Exists Now | Main Gap | Next Validation |
| --- | --- | --- | --- | --- |
| A. Interface | Partial | Next.js control surface with live projects, agents, lifecycle approvals, timeline events, review queue, connector job controls, and connector job history drilldown, plus sample metrics. | No live cost/health dashboard yet. | Dashboard follows one live operation across runs, events, audits, and payloads by trace ID. |
| B. Orchestration | Partial | Gateway accepts `GoalEnvelope`, persists goals through `/goals/submit`, runs one ready task through `/tasks/run-next`, recovers expired leases before bounded `/tasks/run-ready` batches, respects retry backoff, records scheduler ticks, skips task claim conflicts, and exposes an opt-in scheduler worker. | Routing is keyword-based only and there is no durable worker queue yet. | Submit goal -> run scheduler tick -> persisted result timeline. |
| C. Control Plane | Partial | State-backed agents, lifecycle create/update requests, active `AgentSoul`, soul replacement, services, policies, and deterministic `LocalWorldView`. | No frontend form to author lifecycle requests yet and no LLM belongs inside this layer. | Create a lifecycle request from the dashboard, approve it, then verify control-plane world view. |
| D. Domain Agents | Partial | Agent runtime supports deterministic stub mode and interim OpenRouter execution through typed `AgentTaskRequest`/`AgentResult`. | No persistent worker process, no Hermes wrapper, no tool execution, and no standalone model-gateway service. | Narrow division workflow returns typed output, event, cost, and memory candidate. |
| E. Project / Workflow | Partial | Project/task contracts, durable repositories, task dependencies, atomic task start claim, task lease heartbeat, expired lease retry recovery, retry backoff, dead-letter review metadata, task review decisions, task result recording, bounded ready-batch execution, scheduler tick event/audit records, opt-in scheduler worker, and timeline events exist. | No durable worker queue or human review UI for dead-lettered tasks yet. | Bounded scheduler loop executes only ready tasks and emits traceable batch output. |
| F. Memory & Context | Partial | PostgreSQL-backed memory items, scoped context assembly, explicit workspace bridge project isolation, bounded graph expansion through `related_memory_ids`, optional query-embedding cosine ranking, OpenRouter task query embeddings, embedded memory candidates, bounded embedding backfill, deterministic fallback ranking, 1536D embedding validation, reusable vector-ranking E2E, live OpenRouter embedding E2E, live embedding-backfill E2E, live bridge/graph E2E, token budget enforcement, proposed memory candidates, gateway approval/rejection, dashboard review controls, live approved/rejected-memory validation, deterministic compaction with structured source provenance, threshold-based compaction policy, duplicate suppression, project-wide compaction planning, Gateway planning restricted to active project workspaces, reusable active/inactive workspace compaction E2E, compaction worker path, and live compacted-memory validation exist. | No memory relation authoring workflow or hierarchical context database yet. | Add a safe relation-authoring path for proposed memory links. |
| G. Execution & Tooling | Partial | `ToolCallRequest`, `ToolResult`, gateway permission gate, `event.emit`/`web.fetch` adapters, task-scoped credential gates, service health checks, durable connector job lifecycle records, and bounded connector workers exist. | No sandbox execution and no real external connector adapters yet. | Connector job executes a real adapter only after permission, service, and credential gates pass. |
| H. Data / Knowledge | Partial | Conceptual docs plus structured Synarch layer-status facts that can be seeded into memory. | No external connectors, ingestion jobs, document provenance, or loaders. | Seed system facts into memory and verify they appear in context assembly with source metadata. |
| I. Observability & Governance | Partial | Event, audit, cost, trace fields, model-call events, and chronological event API responses exist. Docker includes OTEL/Grafana stack. | No OTEL instrumentation, no Langfuse, and no live cost dashboard. | One request has same trace ID across gateway, state, runtime, event, cost, memory, and audit. |

## Build Strategy

Synarch should grow through vertical slices. Each slice must add one capability that crosses enough
layers to prove the architecture, while keeping the behavior deterministic until the base is solid.

Do not add real LLM autonomy, OpenViking, Cognee, LangGraph, or complex frontend workflows before
the state, events, permissions, and traceability path can be tested. Those tools become useful after
the product can already represent work reliably.

The guiding rule is:

```text
contract -> state -> event/audit -> deterministic behavior -> test -> only then add autonomy
```

## Milestones

### M0. Repo Baseline

Status: Partial, close to done.

Goal: make every contributor able to install, lint, test, and run the skeleton locally.

Done already:

- Monorepo layout exists.
- CI exists for backend and frontend.
- Backend `make verify` runs Ruff, mypy, and pytest when `PYTHON` points to the local venv.
- Frontend scripts exist for lint, route type generation, TypeScript checking, and production build.
- Frontend stack is on Next.js 16, React 19.2, Tailwind CSS 4, and ESLint flat config.

Remaining:

- Make Windows setup first-class in docs and Makefile.
- Add a short `docs/testing.md` or update local development docs with Windows commands.
- Document the recommended cache directories for sandboxed/local environments.

Definition of done:

- A fresh clone can run backend verification with one documented command per OS.
- Frontend install/typecheck is documented and verified.
- Frontend `npm run lint`, `npm run typecheck`, and `npm run build` pass locally.
- README points to roadmap, quality gates, and local development.

### M1. Durable Company State

Status: Next.

Goal: state-service becomes the canonical durable store for Synarch company state.

Scope:

- Build repository interfaces for divisions, agents, projects, tasks, events, services,
  model providers, model definitions, model policies, cost records, audit logs, and lifecycle
  requests.
- Keep the current in-memory repository for fast unit tests.
- Add a PostgreSQL repository behind the same interface.
- Add startup configuration for `DATABASE_URL`.
- Add seed data for default divisions and initial agents.
- Make state-changing endpoints write audit logs when the actor is known.

Progress:

- Done: state-service now depends on a `RecordRepository` protocol instead of direct module-level
  dictionaries.
- Done: `StateRepositories.in_memory()` provides isolated stores for all company-state records.
- Done: `StateRepositories.postgres(DATABASE_URL)` maps the same record types to PostgreSQL tables
  through Psycopg 3.
- Done: repository and API tests cover the in-memory and PostgreSQL factory paths, with `16` backend tests
  passing locally.
- Done: opt-in PostgreSQL restart-survival test exists behind `SYNARCH_POSTGRES_TEST_URL`.
- Done: `make migrate-state` runs ordered state-service SQL migrations.
- Done: `make seed-state` creates default divisions and initial agents idempotently.
- Done: state-changing endpoints write audit logs when `X-Synarch-Actor-Id` is provided.
- Done: Docker Compose has a `state-migrations` one-shot service before `state-service`.
- Done: restart-survival tests run against Docker PostgreSQL for projects and task results.

Do not include yet:

- Multi-tenant organizations.
- Fine-grained RBAC UI.
- Full workflow engine.

Definition of done:

- `create agent -> create project -> assign task -> emit event -> record cost/audit` persists in
  PostgreSQL.
- Restarting the service and reading the same IDs returns the same records.
- Repository tests run against both in-memory and PostgreSQL implementations.
- API behavior remains typed with explicit 400/404/409 errors.

### M2. Control Plane From State

Status: Next after M1.

Goal: control-plane stops being static seed data and becomes the deterministic view over company
state.

Scope:

- Read agents, divisions, services, permissions, and model policies from state-service.
- Build `LocalWorldView` from structured records.
- Add lifecycle request flow: user or manager proposes agent creation/deactivation.
- Require human approval for agent-proposed org changes.
- Record `approval.requested`, `approval.decided`, and audit logs.

Progress:

- Done: control-plane can read agents from state-service when `STATE_SERVICE_URL` is configured.
- Done: seed-backed control-plane remains the local fallback for fast tests.
- Done: Docker Compose points control-plane at state-service after migrations and seeds.
- Done: `LocalWorldView` includes state-backed model policy labels and available service IDs.
- Done: `LocalWorldView` includes the active state-backed `AgentSoul` for stable agent identity.
- Done: `LocalWorldView` exposes explicit org relationships: manager, peers, and direct reports.
- Done: state-service persists service/connector access rules and skill definitions.
- Done: `LocalWorldView` exposes only skills and connectors allowed by agent tools and division.
- Done: state-service records agent lifecycle requests and emits `approval.requested` events.
- Done: approved lifecycle decisions apply agent creation/deactivation, emit `approval.decided`
  plus agent events, and write audit logs.
- Done: inactive agents are blocked from new task assignment.
- Done: control-plane exposes lifecycle request queue, creation, and decision forwarding to
  state-service.
- Done: frontend lifecycle approval queue reads control-plane through a Next API proxy and TanStack
  Query, with sample fallback when backend services are offline.
- Done: frontend agent organization panel reads control-plane through the same live/fallback path.
- Done: frontend project panel reads state-service through the same live/fallback path.
- Done: frontend timeline panel reads state-service events through the same live/fallback path.
- Done: goal submission creates a debuggable task chain with acceptance criteria instead of one broad
  execution task.
- Done: goal submission creates a project workspace and active project assignments for routed
  agents.
- Done: state-service can persist deterministic project complexity reports and request a project
  split when the current task/assignment/workspace score reaches the configured threshold.
- Done: gateway goal submission triggers the state-service complexity assessment after persisting
  the project, workspace, assignments, tasks, and initial timeline events.
- Done: project split requests can be approved or rejected through a traceable state-service
  decision endpoint.
- Done: approved project split requests can be applied into shard projects, shard workspaces,
  active assignments, and first planning tasks.
- Done: gateway exposes project split application through the same public orchestration boundary.
- Done: task runner persists `AgentResult.sub_tasks_created` as child tasks with dependency links
  and `task.created` events.
- Next: connect costs and service health to live APIs.

Definition of done:

- Creating an agent through lifecycle approval makes it visible in `/agents`.
- A deactivated agent cannot receive new tasks.
- `LocalWorldView` contains only allowed capabilities, tools, services, and policies.
- New tasks have explicit acceptance criteria.
- Agents only see active projects through explicit assignments.

### M3. Goal To Project Slice

Status: Done for the deterministic baseline.

Goal: a user goal becomes persisted work and visible timeline data.

Scope:

- Gateway receives `GoalEnvelope`.
- Gateway asks control-plane for available agents and policies.
- Gateway creates project and tasks in state-service through `/goals/submit`.
- Gateway records `goal.received`, `routing.decided`, `project.created`, and `task.created`.
- Gateway returns a response that includes IDs, not only a draft decision.

Definition of done:

- POST `/goals/submit` creates a persisted project and tasks.
- Replaying project state shows task list and event timeline.
- Same input routes deterministically in tests.
- Unknown or ambiguous goals remain owned by IA Direction.

### M4. Event Backbone And Timeline

Status: Partial.

Goal: events become the durable backbone, not just local lists.

Scope:

- State-service stores domain events durably.
- Event-service publishes to NATS.
- Add a timeline query by project, agent, task, event type, and trace ID.
- Decide when JetStream is required; start with NATS core unless replay/durability needs it.

Definition of done:

- Every state-changing action records or emits an event.
- Project timeline can be rebuilt from events.
- Failed event publishing is visible and retryable.

Progress:

- Done: state-service records durable domain events for goal submission, lifecycle requests,
  lifecycle decisions, and task results.
- Done: agent runtime results can be applied to a task and written into the state-service timeline
  with the same trace ID.

### M5. Observability And Cost Ledger

Status: Partial.

Goal: every meaningful action can be traced, audited, and costed.

Scope:

- Generate or propagate `trace_id` at gateway entry.
- Propagate trace IDs through state-service, control-plane, memory-service, runtime, event-service.
- Add OpenTelemetry FastAPI instrumentation.
- Record `CostRecord` for every model call, even mocked ones.
- Add audit logs for state changes, lifecycle decisions, and tool calls.

Progress:

- Done: gateway-generated trace IDs propagate into state-service events and audit logs for goal
  submission.
- Done: task result recording writes traceable event and audit records.
- Done: `/tasks/run-next` propagates the same trace ID through task start, runtime execution,
  task result recording, events, and audit logs.
- Done: every deterministic runner execution records a mock `CostRecord`, emits
  `cost.recorded`, and makes the run queryable by project, agent, model, provider, and trace ID.
- Done: runner executions now emit `model_call.started` and `model_call.completed`; runtime
  failures emit `model_call.failed` before the dependency error is returned.
- Done: every `/tasks/run-ready` bounded scheduler batch records a `scheduler.tick` event and audit
  log with run count, stop reason, task IDs, created child task count, and cost IDs.
- Done: the opt-in scheduler worker runs bounded batches in a loop, emits structured JSON logs, and
  continues after transient tick failures.
- Done: task start claims use conditional repository updates, and `/tasks/run-ready` skips task IDs
  that another scheduler already claimed instead of failing the whole tick.
- Done: running tasks now carry lease owner, lease expiry, heartbeat, attempt count, max attempts,
  retry backoff, and dead-letter review metadata; expired leases are requeued with
  `retry_after_at` or moved to `needs_review` through a traceable recovery endpoint before each
  `/tasks/run-ready` batch.
- Done: humans can list `needs_review` tasks and retry, cancel, or update them through traceable
  task review decisions.
- Done: gateway can run agent-filtered service health checks, returning a typed status report while
  recording `service_health.checked` and `services.health_checked` with the same trace ID.
- Done: state-service can create active cron/webhook connector jobs, record bounded job runs, and
  stop jobs through traceable `connector_job.*` events and audit logs.
- Done: state-service can tick active connector jobs with a bounded limit, recording explicit
  `skipped` runs and `connector_job.tick` audit/event traces until real connector adapters are wired.
- Done: gateway can execute connector jobs through the existing tool gate, preserving permission,
  service capability, credential scope, tool event, connector run, and audit boundaries.
- Done: gateway can execute active connector jobs in bounded batches and record a durable
  `connector_job.tick` event/audit even when no connector job is ready.
- Done: the opt-in connector-job worker can run bounded gateway batches in a loop and emit
  structured JSON logs without starting by default.
- Done: cron connector jobs now store `next_run_at`, and state-service/gateway ready-job queries
  only select jobs whose cooldown has elapsed.
- Done: connector job runs can stop their own job through explicit `output.stop_condition_met` /
  `output.stop_job`, and `metadata.max_runs` stops bounded follow-up loops after N recorded runs.
- Done: failed connector job runs can use `metadata.failure_cooldown_seconds` for retry backoff,
  and `metadata.max_failures` stops jobs after a bounded number of failed runs.
- Done: frontend reads connector jobs and connector job runs through state-service proxy routes,
  showing status, next run, policies, latest run/error, and stop detail in the dashboard.
- Done: connector jobs can be resumed with a durable `connector_job.resumed` event/audit, and
  the dashboard can run, stop, or resume jobs through Gateway proxy routes.
- Done: frontend reads state-service audit logs through a same-origin proxy and shows connector job
  runs, events, audits, traces, and payloads in one history view.
- Done: lifecycle `create_agent` can carry a proposed active `AgentSoul`; approval creates the
  agent and soul in one auditable trace, and control-plane world view exposes the soul.
- Done: lifecycle `update_agent` can replace an agent's mutable definition and active `AgentSoul`;
  the previous soul is deactivated and events/audits preserve the same trace.

Definition of done:

- One request can be followed across logs/events/cost/audit with one trace ID.
- A model call produces `model_call.started`, `model_call.completed` or `model_call.failed`, and
  `cost.recorded`.
- Cost can be queried by project, agent, model, provider, and trace ID.

### M6. Memory Baseline

Status: Partial.

Goal: context assembly becomes useful without becoming expensive or magical.

Scope:

- Store memory items in PostgreSQL first.
- Add scope rules: global, division, agent, project.
- Add token budget approximation.
- Add deterministic ranking before vector search.
- Add memory candidate review flow from `AgentResult`.

Progress:

- Done: memory context requests carry explicit allowed scopes.
- Done: memory-service filters by scope, agent, and project, then ranks project, agent, division,
  and global memory deterministically.
- Done: context assembly enforces the requested token budget with a deterministic token estimate.
- Done: task runner requests memory scopes from `LocalWorldView` and project context.
- Done: memory items persist in PostgreSQL when `DATABASE_URL` is configured.
- Done: gateway persists agent `memory_candidates` as project-scoped `proposed` memory and emits
  `memory.candidate_created`; proposed/rejected memories are excluded from context assembly.
- Done: proposed memory candidates can be approved or rejected through the gateway and dashboard;
  approval emits `memory.status_updated`.
- Done: live OpenRouter E2E approves a proposed candidate and verifies it appears in the next
  task's `memory_context`.
- Done: live OpenRouter E2E rejects a proposed candidate and verifies it stays out of the next
  task's `memory_context`.
- Done: memory-service can create a deterministic proposed compaction item from approved memories,
  preserving source memory IDs in the result and content.
- Done: gateway exposes memory compaction and emits `memory.compacted` with source IDs, source
  count, and source token estimate.
- Done: memory-service and gateway expose `compact-if-needed`, a threshold-based policy that creates
  a proposed compacted memory item only when approved source tokens exceed the configured threshold.
- Done: compacted memory items persist structured provenance in `MemoryItem.metadata`, and
  `compact-if-needed` returns an existing proposed/approved compaction instead of creating
  duplicates for the same source IDs.
- Done: `memory_compaction_worker` can run `compact-if-needed` as a bounded tick or loop for a
  configured scope, with Makefile and Docker worker entrypoints.
- Done: memory-service and gateway expose a compaction plan endpoint that finds overloaded
  non-compacted memory scopes and excludes scopes with an existing proposed/approved summary.
- Done: `memory_compaction_worker` can run without a fixed scope by planning candidate scopes first,
  then executing `compact-if-needed` only for planned items.
- Done: live OpenRouter E2E runs `compact-if-needed`, approves the compacted memory item, and
  verifies a real DeepSeek task gets the compacted summary with source IDs while oversized source
  memories stay out of context.
- Done: gateway exposes bounded embedding backfill for approved memories without vectors, emits
  `memory.embedding_backfilled`, and `memory_embedding_worker` can run it as a tick or loop.
- Done: `scripts/live_memory_embedding_backfill_e2e.sh` verifies real OpenRouter embedding backfill,
  1536D storage, and event traceability.
- Done: task runs derive bridged project memory from active workspace `bridge_project_ids`, pass
  explicit `allowed_project_ids` to memory-service, and keep unbridged project memory isolated.
- Done: memory-service expands bounded `metadata.related_memory_ids` after selected memories, but
  only for related memories already visible through the same scopes and project bridges.
- Done: `scripts/live_memory_bridge_scope_e2e.sh` verifies target memory and explicitly bridged
  graph-related source memory are visible while another project remains hidden.
- Done: system layer-status facts can be seeded into global memory for self-inspection tests.

Do not include yet:

- OpenViking.
- Cognee.
- Multi-hop graph reasoning.

Definition of done:

- Context assembly returns only memory allowed by agent permissions.
- Token budget is enforced.
- Agent/project scoped memories are preferred over unrelated global memories.
- Memory candidates are not automatically promoted without policy.

### M7. Model Gateway

Status: Partial.

Goal: agents never talk directly to model providers.

Scope:

- Add `packages/model-gateway`.
- Choose model from `ModelPolicy`.
- Support provider adapters in this order: fake deterministic provider, OpenAI/OpenRouter, Ollama.
- Enforce per-agent and per-project budget limits.
- Record events, cost, trace IDs, and failures.

Progress:

- Done: agent-runtime has an interim OpenRouter adapter for `deepseek/deepseek-v4-flash`.
- Done: OpenRouter API keys are read only from `OPENROUTER_API_KEY`.
- Done: runtime responses can include `ModelUsage`; gateway turns that into durable `CostRecord`.
- Next: extract provider routing into a real `packages/model-gateway` service and enforce
  `ModelPolicy`.

Definition of done:

- A deterministic fake provider can power tests.
- A real provider call requires configured API key and policy permission.
- Budget limit violations fail before provider call and produce audit/event records.

### M8. First Product Workflow: Finance Invoice Intake

Status: Later, first real product slice.

Goal: prove Synarch solves a concrete business workflow.

Workflow:

```text
Upload invoice
  -> store source metadata
  -> extraction placeholder or OCR adapter
  -> structured invoice JSON
  -> VAT and duplicate checks
  -> proposed accounting classification
  -> exception detection
  -> human approval when required
  -> event timeline
  -> memory candidate
  -> cost/audit trace
```

Definition of done:

- The workflow can run end to end with a fake extractor.
- Invalid invoices produce explicit `needs_review` or `blocked` status.
- Payment execution is denied by default.
- The UI shows project status, task status, exception reason, cost, and timeline.

### M9. Live Interface

Status: Partial.

Goal: frontend becomes the human control surface for the AI company.

Scope:

- Replace sample data with TanStack Query calls.
- Add goal submission.
- Show projects, tasks, agent org chart, timeline, costs, and blocked items.
- Add approval queue for lifecycle requests and finance exceptions.
- Add service health view.

Definition of done:

- User submits a goal and sees a project appear without refreshing manually.
- User can inspect which agent owns each task.
- User can approve/reject an exception.
- UI never becomes the source of truth; it only reads and writes through APIs.

### M10. Tool Execution And Data Connectors

Status: Partial.

Goal: agents can safely act outside Synarch.

Scope:

- Tool registry in state.
- Permission checks before execution.
- Sandboxed execution adapter.
- Connectors for GitHub, files/documents, email/storage later.
- Tool event and audit records.

Definition of done:

- Allowed tool call executes and records result.
- Denied tool call is blocked and audited.
- Tool failures are visible in timeline and do not corrupt task state.

## Immediate Backlog

Work these in order unless a blocking bug appears.

1. Make local development smoother on Windows.
   - Update Makefile default Python handling.
   - Document `make PYTHON=.venv\Scripts\python.exe verify`.
   - Add a frontend verification command to docs.

2. Add state repositories.
   - Extract repository protocol/interface.
   - Move current dictionaries behind in-memory repositories.
   - Add PostgreSQL repository implementation.
   - Add repository tests.

3. Persist the current state-service scenario.
   - Run Postgres via Docker compose.
   - Apply `0001_initial.sql`.
   - Prove restart survival.

4. Make control-plane state-backed.
   - Replace static seed reads with state-service client.
   - Keep deterministic fallback seed for tests only.
   - Connect more frontend panels to control-plane/state-service.

5. Make gateway create real work.
   - POST `/goals` creates project/tasks/events.
   - Return persisted IDs.
   - Add integration test for this full slice.

6. Connect frontend to read-only APIs.
   - Lifecycle request queue from control-plane.
   - Agent list from control-plane.
   - Project list from state-service or gateway.
   - Timeline from event/state service.

## Risk Register

| Risk | Why It Matters | Mitigation |
| --- | --- | --- |
| Building real LLM autonomy too early | Failures become non-deterministic before the foundation is observable. | Use fake/deterministic providers until trace, cost, audit, and approval gates work. |
| Treating chat history as project state | Long projects become impossible to resume or inspect. | Store projects/tasks/events as structured records. Use memory only for context. |
| Letting agents bypass model gateway | Cost, provider keys, and policy enforcement become scattered. | Agents call model-gateway only. No provider-specific code in agent runtime. |
| Adding vector/graph memory too early | Retrieval bugs become hard to isolate. | Start with scoped Postgres memory and deterministic ranking. |
| Frontend becoming source of truth | UI state will diverge from backend state. | UI reads/writes through APIs only. No hidden business logic in React. |
| Tool execution without permissions | Security risk and impossible audit trail. | Tool registry plus pre-execution permission checks. |

## Testing Map

Use this map to know which test proves which layer.

| Test Type | Proves | Command |
| --- | --- | --- |
| Contract tests | Shared Pydantic payloads serialize and reject invalid shapes. | `make PYTHON=.venv\Scripts\python.exe test-unit` |
| State-service tests | Company state endpoints behave consistently. | `make PYTHON=.venv\Scripts\python.exe test-unit` |
| Cross-service integration | Current goal -> world view -> memory -> runtime -> event slice works. | `make PYTHON=.venv\Scripts\python.exe test-integration` |
| Full backend verification | Lint and all backend tests pass. | `make PYTHON=.venv\Scripts\python.exe verify` |
| Frontend lint | Dashboard code follows the Next.js ESLint flat config. | `cd packages/frontend && npm run lint` |
| Frontend typecheck | Dashboard TypeScript and generated route types remain valid. | `cd packages/frontend && npm run typecheck` |
| Frontend build | Next.js production build succeeds with Turbopack. | `cd packages/frontend && npm run build` |

## Decision Log To Keep Updated

When a major choice is made, add an ADR under `docs/adr`.

Open decisions:

- Repository library: SQLAlchemy Core/ORM vs SQLModel.
- Migration tool: keep raw SQL early or introduce Alembic now.
- Service-to-service client style: direct HTTP clients, generated client, or shared lightweight
  client package.
- Model gateway provider order: OpenRouter first, OpenAI first, or fake provider first.
- Frontend API boundary: frontend talks only to gateway, or reads some internal services in local
  development.

Recommended defaults:

- Use SQLAlchemy 2.x first. Add SQLModel only if Pydantic/ORM duplication becomes painful.
- Keep raw SQL migration for M1, introduce Alembic when schema starts changing often.
- Use fake provider first for tests, then OpenRouter/OpenAI.
- Frontend should talk to gateway for product flows. It may call service docs directly only during
  local development/debugging.
