# Backend Core Priorities

The frontend is intentionally secondary until the backend proves Synarch can represent and operate an
AI company as durable state.

## Priority 1: Durable Company State

Build PostgreSQL persistence for:

- divisions
- agents
- projects
- tasks
- events
- services
- model providers
- model definitions
- model policies
- cost records
- audit logs
- agent lifecycle requests

Success criteria:

```text
create agent -> create project -> assign task -> emit event -> record cost/audit
restart service -> read the same state back
```

## Priority 2: Model Gateway

The Model Gateway is the only place that talks to model providers.

Responsibilities:

- choose provider/model from `ModelPolicy`
- call OpenRouter, OpenAI, Ollama, vLLM, or custom providers
- enforce per-agent and per-project budget limits
- record `CostRecord`
- emit `model_call.*` and `cost.recorded` events
- attach trace IDs to every call

Agents should not hold provider API keys or know provider-specific request formats.

Current interim slice:

- agent-runtime can run in `AGENT_RUNTIME_MODE=openrouter`
- OpenRouter calls use `OPENROUTER_API_KEY` from the environment, never committed config
- default test model is `deepseek/deepseek-v4-flash`
- runtime returns `ModelUsage`; gateway converts it into durable `CostRecord`

Local OpenRouter smoke tests should be opt-in:

```bash
export OPENROUTER_API_KEY="..."
export AGENT_RUNTIME_MODE=openrouter
export TASK_RUNNER_PROVIDER_ID=provider-openrouter
export TASK_RUNNER_MODEL_ID=deepseek/deepseek-v4-flash
```

## Priority 3: Org Lifecycle

AI employees are mutable runtime entities, not static files.

Allowed flows:

- user creates/deactivates an agent
- manager agent proposes creating a worker
- manager agent proposes deactivating or replacing a worker
- control plane validates the request
- human approval applies the change
- event log and audit log record the change

Default rule:

```text
agent-proposed org changes require human approval
```

This can later be relaxed for low-risk sandbox organizations.

## Priority 4: Service Registry and Permissions

Each service/tool/provider must be visible as structured state:

- internal service: gateway, state, memory, events, runtime, model-gateway
- external provider: OpenRouter, OpenAI, Ollama endpoint, GitHub, email, storage
- allowed agent/division access
- health status
- audit policy

This is how an agent knows which company service it may communicate with. It is not prompt text; it is
runtime state exposed through `LocalWorldView`.

Implemented baseline:

- `ServiceDefinition`: capabilities, connector kind, allowed agents/divisions, audit flag, metadata
- `SkillDefinition`: required tools, allowed agents/divisions, owner, version, metadata
- `LocalWorldView.available_services`: only services whose capability requirements fit the agent
- `LocalWorldView.available_connector_ids`: allowed external/tool-provider connectors
- `LocalWorldView.available_skill_ids`: registered skills matching the agent's capabilities and tools

## Priority 5: Agent Identity

Each agent needs a bounded durable identity record:

- `AgentSoul`: identity, mission, responsibilities, operating principles, boundaries, escalation rules
- `AgentDefinition`: org position, manager, model policy, capabilities, permissions
- `MemoryContext`: scoped facts retrieved for the current task
- events and audit logs: historical record of what happened

The soul is injected through `LocalWorldView`; it is not a replacement for memory, task history, or
the skill system.

## Priority 6: Logs and Cost Tracking

Minimum required records:

- `EventRecord`: domain timeline
- `AuditLogRecord`: who did what to which target
- `CostRecord`: model/token/provider cost
- trace ID: connects HTTP request, event, model call, tool call, and cost

Every state-changing endpoint should write an audit record. Every model call should write a cost record.

Implemented baseline:

- Gateway `/tools/call` checks `LocalWorldView.permissions` and `available_services` before any tool execution.
- Allowed tool calls emit `tool.called` and write `tool.allowed` audit logs.
- Denied tool calls emit `tool.failed`, write `tool.denied` audit logs, and return HTTP 403.

## Priority 7: Task Breakdown

Objectives must become small ordered tasks before execution:

- each task has acceptance criteria
- dependencies are explicit
- the runner executes only the next ready task
- blocked tasks leave a precise debug boundary

Large projects should produce split requests when the task graph, context volume, cost, or external
coordination load exceeds configured thresholds.

Implemented baseline:

- `ProjectComplexityReport`: deterministic score from open tasks, blocked tasks, active project
  assignments, and workspace bridges
- `ProjectSplitRequest`: approval-ready request when the score reaches the split threshold
- `ProjectSplitDecision`: approved/rejected decision with `approval.decided`, audit log, and stored
  request status update
- `ProjectSplitApplication`: approved split requests create shard projects, shard workspaces,
  active assignments, first planning tasks, `project_split.applied`, and audit log

## Priority 8: Project Workspaces

Each project needs an isolated workspace before agents execute tasks:

- `ProjectWorkspace`: project memory scope, allowed agents, explicit bridge project IDs
- `AgentProjectAssignment`: which employee AI is currently attached to which project
- `LocalWorldView.active_projects`: derived from active assignments, not prompt text

Cross-project knowledge sharing must be explicit through bridges. The default is isolation.

## Recommended Next Implementation

Implement PostgreSQL repositories in `state-service` for:

1. `agents`
2. `projects`
3. `tasks`
4. `events`
5. `model_providers`
6. `model_definitions`
7. `model_policies`
8. `cost_records`
9. `audit_logs`
10. `agent_lifecycle_requests`

Then add one integration test:

```text
create OpenRouter provider
create model policy
create finance agent using policy
create project/task
simulate model call cost
read cost by project and by agent
read audit timeline
```
