from synarch_models import (
    AgentResult,
    CostRecord,
    EventRecord,
    EventType,
    GoalEnvelope,
    LocalWorldView,
    MemoryContext,
    ProjectComplexityAssessment,
    ProjectComplexityReport,
    ProjectSplitRequest,
    TaskRecord,
    TaskRunResult,
    TaskStatus,
)


def test_goal_envelope_defaults() -> None:
    envelope = GoalEnvelope(goal="Build a finance workflow")

    assert envelope.priority == "medium"
    assert envelope.requester == "local-user"


def test_agent_result_is_serializable() -> None:
    task = TaskRecord(
        project_id="project_demo",
        title="Draft plan",
        assigned_agent_id="agent-dev",
        acceptance_criteria=["Plan has a verifiable next action."],
        sequence=1,
    )
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
    task = TaskRecord(
        project_id="project_demo",
        title="Draft plan",
        assigned_agent_id="agent-dev",
        acceptance_criteria=["Plan has a verifiable next action."],
        sequence=1,
    )
    world_view = LocalWorldView(agent_id="agent-dev", role="Code and infra", division="dev")
    memory_context = MemoryContext(
        agent_id="agent-dev",
        project_id=task.project_id,
        allowed_scopes=["global", "division:dev", "agent:agent-dev", "project:project_demo"],
        tokens_used=42,
    )
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
    assert payload["task"]["acceptance_criteria"] == ["Plan has a verifiable next action."]
    assert payload["memory_context"]["tokens_used"] == 42
    assert payload["world_view"]["agent_id"] == "agent-dev"
    assert payload["agent_result"]["status"] == "needs_review"
    assert payload["model_call_events"][0]["type"] == "model_call.completed"
    assert payload["cost_records"][0]["trace_id"] == "trace_123"


def test_project_workspace_and_assignment_isolate_project_context() -> None:
    from synarch_models import AgentProjectAssignment, ProjectWorkspace

    workspace = ProjectWorkspace(
        project_id="project_supplier_search",
        name="Supplier search workspace",
        memory_scope="project:project_supplier_search",
        allowed_agent_ids=["agent-direction", "agent-ops-sourcing"],
    )
    assignment = AgentProjectAssignment(
        project_id=workspace.project_id,
        workspace_id=workspace.id,
        agent_id="agent-ops-sourcing",
        assignment_role="owner",
    )

    assert workspace.memory_scope == "project:project_supplier_search"
    assert assignment.workspace_id == workspace.id
    assert assignment.active is True


def test_project_complexity_assessment_serializes_split_request() -> None:
    report = ProjectComplexityReport(
        project_id="project_supplier_search",
        task_count=10,
        open_task_count=9,
        blocked_task_count=1,
        assigned_agent_count=2,
        score=16,
        threshold=10,
        split_recommended=True,
        reasons=["Project has 9 open tasks."],
    )
    split_request = ProjectSplitRequest(
        project_id=report.project_id,
        complexity_report_id=report.id,
        requested_by="agent-direction",
        reason="Project has 9 open tasks.",
        proposed_shard_titles=["Supplier search - planning", "Supplier search - execution"],
    )
    assessment = ProjectComplexityAssessment(report=report, split_request=split_request)

    payload = assessment.model_dump(mode="json")

    assert payload["report"]["split_recommended"] is True
    assert payload["split_request"]["status"] == "requested"
    assert payload["split_request"]["complexity_report_id"] == report.id
