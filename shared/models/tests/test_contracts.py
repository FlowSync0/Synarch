from synarch_models import AgentResult, EventRecord, EventType, GoalEnvelope, TaskRecord, TaskStatus


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
