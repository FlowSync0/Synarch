# Synarch Roadmap

Last updated: 2026-04-28

This roadmap is the operating map for Synarch. The README explains the vision, and
`docs/development-quality-gates.md` defines the verification discipline. This document answers:
where are we now, what is next, and how each of the nine layers becomes real without turning the
project into an untestable multi-agent prototype.

## Current Reality

Synarch is currently a clean executable skeleton, not yet a durable AI company runtime.

- Backend services exist as FastAPI boundaries: gateway, control-plane, state-service,
  memory-service, event-service, and agent-runtime.
- Shared Pydantic contracts exist for goals, projects, tasks, agents, memory, events, tools,
  model providers, model policies, costs, audit logs, and lifecycle requests.
- The state-service now exposes endpoints for company state, model routing state, cost records, and
  audit logs, but those endpoints still use in-memory stores.
- PostgreSQL schema coverage has started in `packages/state-service/migrations/0001_initial.sql`.
- A static Next.js 16 / Tailwind CSS 4 dashboard exists with sample data, but it is not yet
  connected to backend APIs.
- `make PYTHON=.venv\Scripts\python.exe verify` passes locally on Windows.

The product is therefore testable through code and APIs today. It is not yet visually meaningful
because the frontend reads sample data and the backend state is not persisted across restarts.

## Status Legend

- `Done`: implemented, tested, and part of the executable baseline.
- `Partial`: a boundary or contract exists, but important behavior is missing.
- `Next`: the active engineering priority.
- `Later`: intentionally delayed until lower layers are measurable.
- `Blocked`: waiting on a prerequisite decision or layer.

## Nine-Layer Status

| Layer | Status | What Exists Now | Main Gap | Next Validation |
| --- | --- | --- | --- | --- |
| A. Interface | Partial | Static Next.js control surface with sample projects, agents, metrics, timeline. | No live API reads/writes, no goal submission flow, no approval UI. | Dashboard reads real state-service data and creates a goal through gateway. |
| B. Orchestration | Partial | Gateway accepts `GoalEnvelope` and returns deterministic `RoutingDecision`. | Gateway does not yet create project/tasks/events across services. Routing is keyword-based only. | Submit goal -> persisted project/tasks -> event timeline. |
| C. Control Plane | Partial | Seeded agents, capabilities, permissions, and deterministic `LocalWorldView`. | Agents are static Python seed data; org changes and service registry are not state-backed. | Create/update agent in state -> control-plane reads it -> world view is deterministic. |
| D. Domain Agents | Partial | Agent runtime stub accepts `AgentTaskRequest` and returns typed `AgentResult`. | No persistent agent workers, no model gateway, no real execution loop, no approvals. | Finance stub handles invoice intake deterministically and emits memory/event candidates. |
| E. Project / Workflow | Next | Project/task contracts and state-service endpoints exist. | State is in memory; no dependencies engine, lifecycle transitions, or restart survival. | Postgres-backed project/task/event repositories survive restart. |
| F. Memory & Context | Partial | Memory item endpoint and basic scoped context assembly exist. | In-memory only, no token budgeting, no compaction, no vector/graph retrieval. | Context assembly filters by agent/project/scope and enforces token budget. |
| G. Execution & Tooling | Later | Tool contracts exist (`ToolCallRequest`, `ToolResult`). | No tool registry, permission enforcement, sandbox, or audit trail for tool calls. | Denied tool call fails before execution and records audit/event. |
| H. Data / Knowledge | Later | Conceptual docs only. | No connectors, ingestion jobs, document provenance, or loaders. | Upload/source stub creates traceable knowledge item with provenance. |
| I. Observability & Governance | Partial | Event, audit, cost, trace fields are modeled. Docker includes OTEL/Grafana stack. | No trace propagation, no OTEL instrumentation, no Langfuse, no cost dashboard. | One request has same trace ID across gateway, state, runtime, event, cost, and audit. |

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
- Backend `make verify` passes when `PYTHON` points to the local Windows venv.
- Frontend scripts exist for lint, route type generation, TypeScript checking, and production build.
- Frontend stack is on Next.js 16, React 19.2, Tailwind CSS 4, and ESLint flat config.

Remaining:

- Make Windows setup first-class in docs and Makefile.
- Add a short `docs/testing.md` or update local development docs with Windows commands.
- Decide whether CI should run `mypy`; config exists, but CI currently runs lint and tests only.

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
- Next: add restart-survival tests against Docker PostgreSQL and formalize migration execution.

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

Definition of done:

- Creating an agent through lifecycle approval makes it visible in `/agents`.
- A deactivated agent cannot receive new tasks.
- `LocalWorldView` contains only allowed capabilities, tools, services, and policies.

### M3. Goal To Project Slice

Status: Partial.

Goal: a user goal becomes persisted work and visible timeline data.

Scope:

- Gateway receives `GoalEnvelope`.
- Gateway asks control-plane for available agents and policies.
- Gateway creates project and tasks in state-service.
- Gateway emits `goal.received`, `routing.decided`, `project.created`, and `task.created`.
- Gateway returns a response that includes IDs, not only a draft decision.

Definition of done:

- POST `/goals` creates a persisted project and tasks.
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

### M5. Observability And Cost Ledger

Status: Partial.

Goal: every meaningful action can be traced, audited, and costed.

Scope:

- Generate or propagate `trace_id` at gateway entry.
- Propagate trace IDs through state-service, control-plane, memory-service, runtime, event-service.
- Add OpenTelemetry FastAPI instrumentation.
- Record `CostRecord` for every model call, even mocked ones.
- Add audit logs for state changes, lifecycle decisions, and tool calls.

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

Status: Later, but soon after M5.

Goal: agents never talk directly to model providers.

Scope:

- Add `packages/model-gateway`.
- Choose model from `ModelPolicy`.
- Support provider adapters in this order: fake deterministic provider, OpenAI/OpenRouter, Ollama.
- Enforce per-agent and per-project budget limits.
- Record events, cost, trace IDs, and failures.

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

Status: Later.

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
   - Add lifecycle request endpoints.

5. Make gateway create real work.
   - POST `/goals` creates project/tasks/events.
   - Return persisted IDs.
   - Add integration test for this full slice.

6. Connect frontend to read-only APIs.
   - Project list from state-service or gateway.
   - Agent list from control-plane.
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
