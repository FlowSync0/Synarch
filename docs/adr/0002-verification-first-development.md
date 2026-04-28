# ADR 0002: Verification-First Development

## Status

Accepted

## Context

Synarch has a broad architecture: interface, orchestration, control plane, persistent agents,
workflow state, memory, tooling, knowledge sources, and observability. Building all layers at once
would create a large surface area with no objective proof that the pieces work together.

The project also includes non-deterministic AI components. Those cannot be treated like ordinary
library calls. They need typed contracts, traceability, evals, and human approval boundaries.

## Decision

Synarch will develop by quality gates. Each gate must add one small capability and one executable
verification path before the next gate starts.

The first required cross-layer scenario is:

```text
goal -> routing -> project/task -> world view -> memory context -> agent result -> event timeline
```

The canonical command for the current backend gate is:

```bash
make verify
make test-integration
```

## Consequences

- New libraries are admitted only when they satisfy a gate and are covered by tests.
- The project can keep the nine-layer architecture as documentation without forcing nine independent
  production services too early.
- AI behavior will be tested through evals before it is trusted in user-facing workflows.
- Critical tools and finance actions remain behind explicit approval and permission checks.
