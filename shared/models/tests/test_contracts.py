from synarch_models import (
    AgentResult,
    CostRecord,
    CredentialAccessRequest,
    EventRecord,
    EventType,
    GoalEnvelope,
    LocalWorldView,
    MemoryContext,
    MemoryItem,
    MemoryStatus,
    ModelUsage,
    ProjectComplexityAssessment,
    ProjectComplexityReport,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectSplitDecision,
    ProjectSplitRequest,
    TaskRecord,
    TaskRunBatchResult,
    TaskRunResult,
    TaskSkipRecord,
    TaskStatus,
    ToolCallRequest,
    ToolResult,
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
        required_tools=["git.read"],
        required_tool_scopes={"git.read": ["github:contents:read"]},
        acceptance_criteria=["Plan has a verifiable next action."],
        sequence=1,
    )
    event = EventRecord(type=EventType.task_completed, source_agent_id="agent-dev")
    result = AgentResult(
        agent_id="agent-dev",
        task_id=task.id,
        status=TaskStatus.completed,
        events_emitted=[event],
        tool_calls_requested=[
            ToolCallRequest(
                agent_id="agent-dev",
                tool_name="event.emit",
                reason="Record completion.",
                arguments={"type": "task.completed"},
            )
        ],
        model_usage=ModelUsage(
            provider_id="provider-openrouter",
            model_id="deepseek/deepseek-v4-flash",
            input_tokens=10,
            output_tokens=20,
            total_cost=0.00001,
        ),
        summary="Task completed.",
    )

    payload = result.model_dump(mode="json")

    assert payload["status"] == "completed"
    assert payload["events_emitted"][0]["type"] == "task.completed"
    assert payload["tool_calls_requested"][0]["tool_name"] == "event.emit"
    assert payload["model_usage"]["model_id"] == "deepseek/deepseek-v4-flash"


def test_task_run_result_captures_execution_boundary() -> None:
    task = TaskRecord(
        project_id="project_demo",
        title="Draft plan",
        assigned_agent_id="agent-dev",
        required_tools=["git.read"],
        required_tool_scopes={"git.read": ["github:contents:read"]},
        acceptance_criteria=["Plan has a verifiable next action."],
        sequence=1,
    )
    world_view = LocalWorldView(
        agent_id="agent-dev",
        role="Code and infra",
        division="dev",
        available_services=["connector-github"],
        available_service_capabilities={"connector-github": ["git.read"]},
        available_service_credential_scopes={
            "connector-github": ["github:contents:read"]
        },
    )
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
        tool_results=[
            ToolResult(
                tool_name="event.emit",
                output={"authorized": True, "adapter": "event.emit"},
            )
        ],
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
    assert payload["task"]["required_tools"] == ["git.read"]
    assert payload["task"]["required_tool_scopes"] == {
        "git.read": ["github:contents:read"]
    }
    assert payload["memory_context"]["tokens_used"] == 42
    assert payload["world_view"]["agent_id"] == "agent-dev"
    assert payload["world_view"]["available_service_capabilities"] == {
        "connector-github": ["git.read"]
    }
    assert payload["world_view"]["available_service_credential_scopes"] == {
        "connector-github": ["github:contents:read"]
    }
    assert payload["agent_result"]["status"] == "needs_review"
    assert payload["tool_results"][0]["tool_name"] == "event.emit"
    assert payload["model_call_events"][0]["type"] == "model_call.completed"
    assert payload["cost_records"][0]["trace_id"] == "trace_123"


def test_task_run_batch_result_captures_skip_reasons() -> None:
    result = TaskRunBatchResult(
        trace_id="trace_scheduler",
        max_tasks=2,
        project_id="project_demo",
        stop_reason="no_ready_task",
        skipped_task_ids=["task_blocked"],
        skipped_tasks=[
            TaskSkipRecord(
                task_id="task_blocked",
                category="credential_readiness",
                reason="Credential scopes missing for required tool: web.fetch",
            )
        ],
        credential_access_requests=[
            CredentialAccessRequest(
                id="credential-access-task-blocked-web-fetch",
                task_id="task_blocked",
                project_id="project_demo",
                agent_id="agent-dev",
                tool_name="web.fetch",
                requested_scopes=["browser:authenticated_fetch"],
                candidate_service_ids=["connector-web"],
                reason="Credential scopes missing for required tool: web.fetch",
            )
        ],
        credential_resumed_task_ids=["task_blocked"],
    )

    payload = result.model_dump(mode="json")

    assert payload["skipped_task_ids"] == ["task_blocked"]
    assert payload["skipped_tasks"] == [
        {
            "task_id": "task_blocked",
            "category": "credential_readiness",
            "reason": "Credential scopes missing for required tool: web.fetch",
        }
    ]
    assert payload["credential_access_requests"][0]["id"] == (
        "credential-access-task-blocked-web-fetch"
    )
    assert payload["credential_resumed_task_ids"] == ["task_blocked"]


def test_memory_item_defaults_to_approved_status() -> None:
    item = MemoryItem(scope="global", content="Company memory.")

    assert item.status == MemoryStatus.approved
    assert item.model_dump(mode="json")["status"] == "approved"


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
    decision = ProjectSplitDecision(
        request_id=split_request.id,
        status="approved",
        decided_by_type="user",
        decided_by_id="local-user",
        rationale="The project should be split before more execution work starts.",
    )
    application = ProjectSplitApplication(
        request_id=split_request.id,
        split_request=split_request.model_copy(update={"status": "applied"}),
        source_project_id=split_request.project_id,
        shard_projects=[
            ProjectRecord(
                title="Supplier search - planning",
                goal="Shard of Supplier search.",
                owner_agent_id="agent-direction",
            )
        ],
    )

    payload = assessment.model_dump(mode="json")
    decision_payload = decision.model_dump(mode="json")
    application_payload = application.model_dump(mode="json")

    assert payload["report"]["split_recommended"] is True
    assert payload["split_request"]["status"] == "requested"
    assert payload["split_request"]["complexity_report_id"] == report.id
    assert decision_payload["status"] == "approved"
    assert decision_payload["request_id"] == split_request.id
    assert application_payload["split_request"]["status"] == "applied"
    assert application_payload["shard_projects"][0]["title"] == "Supplier search - planning"
