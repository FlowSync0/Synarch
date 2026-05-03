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
  -> Memory Context Assembly
  -> Agent Runtime AgentResult
  -> Task Runner child TaskRecord persistence when an agent proposes sub_tasks_created
  -> Event Service timeline
```

Run it with:

```bash
make test-integration
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
