# ADR 0003: Model Router, Org Lifecycle, and Cost Ledger Are Core Backend Systems

## Status

Accepted

## Context

Synarch must support local deployment and always-on server deployment. It must also allow an operator
to choose AI providers, route calls through OpenRouter or another backend, create or deactivate AI
employees, let authorized agents propose organization changes, and track costs/logs at a granular level.

These requirements are not frontend concerns. They are core backend concerns because they affect
permissions, autonomy, safety, observability, and operating cost.

## Decision

Synarch will treat the following systems as first-class backend services:

- Model Gateway: routes model calls to OpenRouter, OpenAI, Ollama, vLLM, local, or custom providers.
- Model Policy: defines which agents/divisions can use which models and at what budget.
- Org Lifecycle: creates, updates, deactivates, and approves AI employees.
- Service Registry: records internal services and external service providers available to the company.
- Cost Ledger: records token usage, provider, model, agent, project, task, trace ID, and estimated cost.
- Audit Log: records who requested or performed every important action.

Agents may propose creating, updating, or deactivating employees, but lifecycle changes are approval-gated
by default. This keeps the system evolvable without allowing unbounded self-modification.

## Required Contracts

The shared model layer includes:

- `ModelProviderConfig`
- `ModelDefinition`
- `ModelPolicy`
- `ModelCallRequest`
- `CostRecord`
- `AuditLogRecord`
- `ServiceDefinition`
- `AgentLifecycleRequest`
- `AgentLifecycleDecision`

## Consequences

- Every model call can be traced to provider, model, agent, project, task, and cost.
- Provider choice is data-driven, not hardcoded inside agents.
- The control plane can expose exactly which services an agent can communicate with.
- The organization can evolve at runtime while preserving auditability.
- The first PostgreSQL implementation must include cost and audit tables early, not as a late add-on.
