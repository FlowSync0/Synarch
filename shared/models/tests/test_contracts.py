from synarch_models import (
    AgentDefinition,
    AgentLifecycleRequest,
    AgentResult,
    AgentSoul,
    ConnectorJobKind,
    ConnectorJobMutationResult,
    ConnectorJobRecord,
    ConnectorJobResumeRequest,
    ConnectorJobRunBatchResult,
    ConnectorJobRunRecord,
    ConnectorJobRunResult,
    ConnectorJobRunStatus,
    ConnectorJobStatus,
    CostRecord,
    CredentialAccessRequest,
    EventRecord,
    EventType,
    GoalEnvelope,
    LocalWorldView,
    MemoryCompactionPlanRequest,
    MemoryCompactionPolicyRequest,
    MemoryContext,
    MemoryEmbeddingBackfillRequest,
    MemoryItem,
    MemoryRelationProposalRequest,
    MemoryStatus,
    ModelCompletionRequest,
    ModelCompletionResponse,
    ModelMessage,
    ModelUsage,
    OperatorAction,
    ProjectComplexityAssessment,
    ProjectComplexityReport,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectSplitDecision,
    ProjectSplitRequest,
    ServiceHealthCheck,
    ServiceHealthReport,
    ServiceHealthStatus,
    ServiceKind,
    SystemReadinessItem,
    SystemReadinessReport,
    TaskRecord,
    TaskRunBatchResult,
    TaskRunResult,
    TaskSkipRecord,
    TaskStatus,
    ToolCallRequest,
    ToolResult,
    WorkQueueSummary,
)


def test_goal_envelope_defaults() -> None:
    envelope = GoalEnvelope(goal="Build a finance workflow")

    assert envelope.priority == "medium"
    assert envelope.requester == "local-user"


def test_system_readiness_report_captures_manual_action_items() -> None:
    report = SystemReadinessReport(
        status="warning",
        items=[
            SystemReadinessItem(
                id="ai_runtime",
                category="runtime",
                title="AI runtime route",
                status="warning",
                detail="Task runner is using the deterministic local stub route.",
                manual_action="Set OPENROUTER_API_KEY before live AI runs.",
                evidence={"provider_id": "provider-local-runtime-stub"},
            )
        ],
    )

    payload = report.model_dump(mode="json")

    assert payload["status"] == "warning"
    assert payload["items"][0]["manual_action"] == (
        "Set OPENROUTER_API_KEY before live AI runs."
    )
    assert payload["items"][0]["evidence"]["provider_id"] == "provider-local-runtime-stub"


def test_work_queue_summary_contract_preserves_operational_counts() -> None:
    summary = WorkQueueSummary(
        queue_name="reminders",
        item_count=5,
        status_counts={"queued": 2, "running": 1, "failed": 1, "dead_lettered": 1},
        ready_count=1,
        delayed_count=1,
        running_count=1,
        failed_count=1,
        dead_lettered_count=1,
        latest_error="Needs human PDF password.",
    )

    payload = summary.model_dump(mode="json")

    assert payload["queue_name"] == "reminders"
    assert payload["item_count"] == 5
    assert payload["status_counts"]["queued"] == 2
    assert payload["ready_count"] == 1
    assert payload["delayed_count"] == 1
    assert payload["latest_error"] == "Needs human PDF password."


def test_operator_action_contract_preserves_target_and_evidence() -> None:
    action = OperatorAction(
        id="operator_action_human_human-1",
        kind="human_assistance",
        title="CAPTCHA supplier portal",
        reason="Agent needs human verification before continuing.",
        recommended_action="Answer the human assistance request, then retry the task.",
        priority="high",
        status="requested",
        target_id="human-1",
        project_id="project-1",
        task_id="task-1",
        agent_id="agent-ops",
        created_at="2026-05-20T08:00:00Z",
        evidence={"kind": "captcha"},
    )

    payload = action.model_dump(mode="json")

    assert payload["priority"] == "high"
    assert payload["target_id"] == "human-1"
    assert payload["evidence"] == {"kind": "captcha"}


def test_memory_compaction_policy_request_defaults() -> None:
    request = MemoryCompactionPolicyRequest(scope="project:demo")

    assert request.status == "proposed"
    assert request.min_source_tokens == 1200
    assert request.max_source_items == 20


def test_memory_compaction_plan_request_defaults() -> None:
    request = MemoryCompactionPlanRequest(project_id="project_demo")

    assert request.status == "proposed"
    assert request.scopes is None
    assert request.min_source_tokens == 1200
    assert request.max_source_items == 20
    assert request.max_scopes == 20


def test_memory_embedding_backfill_request_defaults() -> None:
    request = MemoryEmbeddingBackfillRequest(project_id="project_demo")

    assert request.project_id == "project_demo"
    assert request.status == "approved"
    assert request.max_items == 10


def test_memory_relation_proposal_request_requires_related_ids() -> None:
    request = MemoryRelationProposalRequest(
        source_memory_id="memory-source",
        related_memory_ids=["memory-related"],
        reason="The related memory gives source context.",
    )

    assert request.source_memory_id == "memory-source"
    assert request.related_memory_ids == ["memory-related"]


def test_memory_context_can_carry_query_embedding() -> None:
    context = MemoryContext(
        agent_id="agent-dev",
        project_id="project_demo",
        allowed_project_ids=["project_demo", "project_source"],
        query_embedding=[0.0, 1.0],
    )

    assert context.allowed_project_ids == ["project_demo", "project_source"]
    assert context.max_related_items == 3
    assert context.query_embedding == [0.0, 1.0]
    assert context.model_dump(mode="json")["allowed_project_ids"] == [
        "project_demo",
        "project_source",
    ]
    assert context.model_dump(mode="json")["max_related_items"] == 3
    assert context.model_dump(mode="json")["query_embedding"] == [0.0, 1.0]


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
        lifecycle_requests_created=[
            AgentLifecycleRequest(
                action="create_agent",
                requested_by_type="agent",
                requested_by_id="agent-dev",
                reason="Create a specialist for a bounded workstream.",
                proposed_agent=AgentDefinition(
                    id="agent-specialist",
                    name="IA Specialist",
                    role="Bounded specialist",
                    division="dev",
                    manager_id="agent-dev",
                ),
                proposed_soul=AgentSoul(
                    agent_id="agent-specialist",
                    identity="Bounded specialist",
                    mission="Handle one narrow workstream with traceable output.",
                    created_by="agent-dev",
                ),
            )
        ],
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
    assert payload["lifecycle_requests_created"][0]["action"] == "create_agent"
    assert (
        payload["lifecycle_requests_created"][0]["proposed_soul"]["agent_id"]
        == "agent-specialist"
    )
    assert payload["tool_calls_requested"][0]["tool_name"] == "event.emit"
    assert payload["model_usage"]["model_id"] == "deepseek/deepseek-v4-flash"


def test_model_completion_contract_carries_messages_and_usage() -> None:
    request = ModelCompletionRequest(
        agent_id="agent-dev",
        purpose="agent_task",
        provider_id="provider-openrouter",
        model_id="deepseek/deepseek-v4-flash",
        model_policy_id="policy-openrouter-deepseek-v4-flash",
        task_id="task_model_gateway",
        project_id="project_model_gateway",
        messages=[
            ModelMessage(role="system", content="Return JSON."),
            ModelMessage(role="user", content="Plan the task."),
        ],
        max_output_tokens=400,
    )
    response = ModelCompletionResponse(
        provider_id="provider-openrouter",
        model_id="deepseek/deepseek-v4-flash",
        content='{"status":"needs_review"}',
        usage=ModelUsage(
            provider_id="provider-openrouter",
            model_id="deepseek/deepseek-v4-flash",
            input_tokens=20,
            output_tokens=5,
            total_cost=0.000001,
        ),
    )

    request_payload = request.model_dump(mode="json")
    response_payload = response.model_dump(mode="json")

    assert request_payload["messages"][0]["role"] == "system"
    assert request_payload["purpose"] == "agent_task"
    assert request_payload["model_policy_id"] == "policy-openrouter-deepseek-v4-flash"
    assert response_payload["usage"]["input_tokens"] == 20
    assert response_payload["content"] == '{"status":"needs_review"}'


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


def test_service_health_report_captures_probe_result() -> None:
    report = ServiceHealthReport(
        trace_id="trace_service_health",
        agent_id="agent-ops-sourcing",
        checks=[
            ServiceHealthCheck(
                service_id="connector-supplier-web",
                name="Supplier Web",
                kind=ServiceKind.tool_provider,
                enabled=True,
                status=ServiceHealthStatus.healthy,
                base_url="https://example.com",
                health_endpoint="/healthz",
                status_code=200,
                response_time_ms=12,
                capabilities=["web.fetch"],
                credential_scopes=["browser:authenticated_fetch"],
            )
        ],
        event=EventRecord(
            type=EventType.service_health_checked,
            trace_id="trace_service_health",
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload["agent_id"] == "agent-ops-sourcing"
    assert payload["checks"][0]["status"] == "healthy"
    assert payload["checks"][0]["response_time_ms"] == 12
    assert payload["event"]["type"] == "service_health.checked"


def test_connector_job_lifecycle_contracts_are_serializable() -> None:
    job = ConnectorJobRecord(
        id="connector-job-supplier-followup",
        service_id="connector-supplier-web",
        project_id="project_supplier_search",
        task_id="task_supplier_followup",
        owner_agent_id="agent-ops-sourcing",
        kind=ConnectorJobKind.cron,
        status=ConnectorJobStatus.active,
        schedule="0 */6 * * *",
        purpose="Relance fournisseur toutes les six heures jusqu'a reponse.",
        created_by_type="agent",
        created_by_id="agent-ops-sourcing",
        metadata={"stop_condition": "supplier replied"},
    )
    run = ConnectorJobRunRecord(
        id="connector-job-run-supplier-followup",
        job_id=job.id,
        service_id=job.service_id,
        project_id=job.project_id,
        task_id=job.task_id,
        owner_agent_id=job.owner_agent_id,
        status=ConnectorJobRunStatus.completed,
        triggered_by_type="service",
        triggered_by_id="connector-job-runner",
        trace_id="trace_connector_job",
        output={"message": "Follow-up sent."},
    )
    mutation = ConnectorJobMutationResult(
        job=job,
        event=EventRecord(type=EventType.connector_job_created),
    )
    resume = ConnectorJobResumeRequest(
        resumed_by_type="user",
        resumed_by_id="local-user",
        reason="Manual resume from dashboard.",
    )
    run_result = ConnectorJobRunResult(
        run=run,
        event=EventRecord(type=EventType.connector_job_run_recorded),
    )
    batch_result = ConnectorJobRunBatchResult(
        trace_id="trace_connector_job",
        max_jobs=1,
        stop_reason="max_jobs_reached",
        runs=[
            ConnectorJobRunResult(
                run=run.model_copy(update={"status": ConnectorJobRunStatus.blocked}),
                event=EventRecord(type=EventType.connector_job_run_recorded),
            )
        ],
        tick_event=EventRecord(type=EventType.connector_job_tick),
    )

    job_payload = mutation.model_dump(mode="json")["job"]
    run_payload = run_result.model_dump(mode="json")["run"]
    batch_payload = batch_result.model_dump(mode="json")

    assert job_payload["kind"] == "cron"
    assert job_payload["status"] == "active"
    assert job_payload["next_run_at"] is None
    assert job_payload["metadata"] == {"stop_condition": "supplier replied"}
    assert resume.model_dump(mode="json")["resumed_by_id"] == "local-user"
    assert run_payload["status"] == "completed"
    assert run_payload["output"] == {"message": "Follow-up sent."}
    assert batch_payload["runs"][0]["run"]["status"] == "blocked"
    assert batch_payload["tick_event"]["type"] == "connector_job.tick"


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
