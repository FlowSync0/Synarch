# ADR 0001: Monorepo Service Boundaries

## Status

Accepted

## Context

The README defines Synarch as a platform with independent layers for interface, orchestration, control,
agents, workflow, memory, execution, data, and observability. Phase 1 needs enough structure to keep these
boundaries visible without prematurely building production implementations.

## Decision

Use a monorepo with one directory per deployable service under `packages/`, and keep cross-service contracts
in `shared/models`.

Each Python service owns its FastAPI application and can later receive its own repository, database adapter,
workers, and deployment settings without changing the external contracts.

## Consequences

- The system can be bootstrapped quickly with Docker Compose.
- Contract changes are reviewed centrally through `shared/models`.
- Early implementations can use in-memory stores while database and event-bus adapters mature.
