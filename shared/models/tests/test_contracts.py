from synarch_models import (
    AgentResult,
    CostRecord,
    EventRecord,
    EventType,
    GoalEnvelope,
    LocalWorldView,
    MemoryContext,
    TaskRecord,
    TaskRunResult,
    TaskStatus,
)


def test_goal_envelope_defaults() -> None:
    envelope = GoalEnvelope(goal="Build a finance workflow")

    assert envelope.priority == "medium"
    assert envelope.requester == "local-user"


def test_agent_result_is_serializable() -> None:
    task = TaskRecord(project_id="project_demo", title="Draft plan", assigned_agent_id="agent-dev")
    event = EventRecord(type=EventType.task_completed, source_agent_id="agent-dev")
    result = AgentResult(
        agent_id="agent-dev",
        task_id=task.id,
        status=TaskStatus.completed,
        events_emitted=[event],
        summary="Task completed.",
    )

    payload = result.model_dump(mode="json")

    assert payload["status"] == "completed"
    assert payload["events_emitted"][0]["type"] == "task.completed"


def test_task_run_result_captures_execution_boundary() -> None:
    task = TaskRecord(project_id="project_demo", title="Draft plan", assigned_agent_id="agent-dev")
    world_view = LocalWorldView(agent_id="agent-dev", role="Code and infra", division="dev")
    memory_context = MemoryContext(agent_id="agent-dev", project_id=task.project_id)
    agent_result = AgentResult(
        agent_id="agent-dev",
        task_id=task.id,
        status=TaskStatus.needs_review,
        summary="Task prepared for review.",
    )
    result = TaskRunResult(
        trace_id="trace_123",
        task=task,
        world_view=world_view,
        memory_context=memory_context,
        agent_result=agent_result,
        model_call_events=[
            EventRecord(
                type=EventType.model_call_completed,
                source_agent_id="agent-dev",
                target=task.project_id,
                trace_id="trace_123",
            )
        ],
        cost_records=[
            CostRecord(
                provider_id="provider-local-runtime-stub",
                model_id="model-local-runtime-stub",
                agent_id="agent-dev",
                project_id=task.project_id,
                task_id=task.id,
                trace_id="trace_123",
                input_tokens=120,
                output_tokens=40,
                total_cost=0.000002,
            )
        ],
    )

    payload = result.model_dump(mode="json")

    assert payload["trace_id"] == "trace_123"
    assert payload["task"]["id"] == task.id
    assert payload["world_view"]["agent_id"] == "agent-dev"
    assert payload["agent_result"]["status"] == "needs_review"
    assert payload["model_call_events"][0]["type"] == "model_call.completed"
    assert payload["cost_records"][0]["trace_id"] == "trace_123"
