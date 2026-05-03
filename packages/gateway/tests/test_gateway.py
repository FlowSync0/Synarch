from fastapi.testclient import TestClient

from synarch_gateway.main import (
    app,
    get_control_plane_client,
    get_memory_client,
    get_state_client,
    get_task_runner,
)
from synarch_gateway.state_client import StateServiceUnavailable
from synarch_gateway.task_runner import TaskRunner, TaskRunnerUnavailable
from synarch_models import (
    AgentProjectAssignment,
    AgentResult,
    AgentTaskRequest,
    AuditLogRecord,
    CostRecord,
    EventRecord,
    EventType,
    LocalWorldView,
    MemoryContext,
    MemoryItem,
    MemoryStatus,
    MemoryStatusUpdate,
    ModelUsage,
    PermissionBundle,
    ProjectComplexityAssessment,
    ProjectComplexityReport,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectSplitRequest,
    ProjectWorkspace,
    TaskRecord,
    TaskStatus,
)


class FakeStateClient:
    def __init__(self) -> None:
        self.projects: list[ProjectRecord] = []
        self.workspaces: list[ProjectWorkspace] = []
        self.assignments: list[AgentProjectAssignment] = []
        self.tasks: list[TaskRecord] = []
        self.events: list[EventRecord] = []
        self.costs: list[CostRecord] = []
        self.audit_logs: list[AuditLogRecord] = []
        self.complexity_assessments: list[ProjectComplexityAssessment] = []
        self.split_applications: list[ProjectSplitApplication] = []
        self.headers: list[dict[str, str]] = []

    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        self.headers.append(headers)
        self.projects.append(project)
        return project

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace:
        self.headers.append(headers)
        self.workspaces.append(workspace)
        return workspace

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment:
        self.headers.append(headers)
        self.assignments.append(assignment)
        return assignment

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        self.tasks.append(task)
        return task

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        self.headers.append(headers)
        self.events.append(event)
        return event

    def list_events(
        self,
        *,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventRecord]:
        events = self.events
        if event_type is not None:
            events = [event for event in events if event.type == event_type]
        if trace_id is not None:
            events = [event for event in events if event.trace_id == trace_id]
        return events

    def assess_project_complexity(
        self,
        project_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectComplexityAssessment:
        self.headers.append(headers)
        assessment = ProjectComplexityAssessment(
            report=ProjectComplexityReport(
                project_id=project_id,
                task_count=len([task for task in self.tasks if task.project_id == project_id]),
                open_task_count=len(
                    [
                        task
                        for task in self.tasks
                        if task.project_id == project_id
                        and task.status not in {TaskStatus.completed, TaskStatus.failed}
                    ]
                ),
                score=4,
                threshold=10,
                split_recommended=False,
            )
        )
        self.complexity_assessments.append(assessment)
        return assessment

    def apply_project_split(
        self,
        split_request_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectSplitApplication:
        self.headers.append(headers)
        source_project = ProjectRecord(
            id="project-large",
            title="Large project",
            goal="Split this approved project.",
            owner_agent_id="agent-direction",
        )
        shard_project = ProjectRecord(
            id="project-large-shard-planning",
            title="Large project - planning",
            goal="Shard of Large project.",
            owner_agent_id="agent-direction",
        )
        shard_workspace = ProjectWorkspace(
            id="workspace-large-shard-planning",
            project_id=shard_project.id,
            name=shard_project.title,
            memory_scope=f"project:{shard_project.id}",
            allowed_agent_ids=["agent-direction"],
            bridge_project_ids=[source_project.id],
        )
        shard_task = TaskRecord(
            id="task-large-shard-plan",
            project_id=shard_project.id,
            title="Define execution plan for Large project - planning",
            assigned_agent_id="agent-direction",
            acceptance_criteria=["Shard plan is explicit."],
        )
        application = ProjectSplitApplication(
            request_id=split_request_id,
            split_request=ProjectSplitRequest(
                id=split_request_id,
                project_id=source_project.id,
                complexity_report_id="complexity-large",
                requested_by="agent-direction",
                reason="Project reached the split threshold.",
                proposed_shard_titles=[shard_project.title],
                status="applied",
            ),
            source_project_id=source_project.id,
            shard_projects=[shard_project],
            shard_workspaces=[shard_workspace],
            shard_tasks=[shard_task],
        )
        self.split_applications.append(application)
        return application

    def get_project(self, project_id: str) -> ProjectRecord:
        for project in self.projects:
            if project.id == project_id:
                return project
        return ProjectRecord(
            id=project_id,
            title="Demo project",
            goal="Demo project goal.",
            owner_agent_id="agent-direction",
        )

    def list_tasks(self, *, project_id: str | None = None) -> list[TaskRecord]:
        if project_id is None:
            return self.tasks
        return [task for task in self.tasks if task.project_id == project_id]

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        started_task = task.model_copy(update={"status": TaskStatus.running})
        self.tasks[self.tasks.index(task)] = started_task
        return started_task

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        recorded_task = task.model_copy(
            update={
                "status": result.status,
                "result": {"summary": result.summary},
            }
        )
        self.tasks[self.tasks.index(task)] = recorded_task
        return recorded_task

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord:
        self.headers.append(headers)
        self.costs.append(cost)
        return cost

    def list_cost_records(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[CostRecord]:
        costs = self.costs
        if project_id is not None:
            costs = [cost for cost in costs if cost.project_id == project_id]
        if agent_id is not None:
            costs = [cost for cost in costs if cost.agent_id == agent_id]
        if provider_id is not None:
            costs = [cost for cost in costs if cost.provider_id == provider_id]
        if model_id is not None:
            costs = [cost for cost in costs if cost.model_id == model_id]
        if trace_id is not None:
            costs = [cost for cost in costs if cost.trace_id == trace_id]
        return costs

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[AuditLogRecord]:
        audits = self.audit_logs
        if actor_id is not None:
            audits = [audit for audit in audits if audit.actor_id == actor_id]
        if target_type is not None:
            audits = [audit for audit in audits if audit.target_type == target_type]
        if target_id is not None:
            audits = [audit for audit in audits if audit.target_id == target_id]
        if trace_id is not None:
            audits = [audit for audit in audits if audit.trace_id == trace_id]
        return audits

    def create_audit_log(
        self,
        audit: AuditLogRecord,
        *,
        headers: dict[str, str],
    ) -> AuditLogRecord:
        self.headers.append(headers)
        self.audit_logs.append(audit)
        return audit


class FailingStateClient(FakeStateClient):
    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        raise StateServiceUnavailable("state-service offline")


class FakeControlPlaneClient:
    def __init__(self, world_views: dict[str, LocalWorldView] | None = None) -> None:
        self.world_views = world_views or {}

    def get_world_view(self, agent_id: str) -> LocalWorldView:
        if agent_id in self.world_views:
            return self.world_views[agent_id]
        return LocalWorldView(agent_id=agent_id, role="Code and infra", division="dev")


class FakeMemoryClient:
    def __init__(self) -> None:
        self.contexts: list[MemoryContext] = []
        self.items: list[MemoryItem] = []
        self.items_by_id: dict[str, MemoryItem] = {}

    def assemble_context(self, context: MemoryContext) -> MemoryContext:
        self.contexts.append(context)
        return context.model_copy(update={"summary": "Fake context assembled."})

    def create_memory_item(self, item: MemoryItem) -> MemoryItem:
        self.items.append(item)
        self.items_by_id[item.id] = item
        return item

    def list_memory_items(
        self,
        *,
        scope: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        status: MemoryStatus | None = None,
    ) -> list[MemoryItem]:
        items = list(self.items_by_id.values())
        if scope is not None:
            items = [item for item in items if item.scope == scope]
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id]
        if project_id is not None:
            items = [item for item in items if item.project_id == project_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        return items

    def update_memory_status(self, item_id: str, update: MemoryStatusUpdate) -> MemoryItem:
        item = self.items_by_id[item_id]
        updated = item.model_copy(update={"status": update.status})
        self.items_by_id[item_id] = updated
        return updated


class FakeAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.needs_review,
            actions_taken=["Loaded LocalWorldView", "Prepared execution plan"],
            memory_candidates=[
                MemoryItem(
                    scope="global",
                    content="Remember that this project needs explicit acceptance criteria.",
                )
            ],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=123,
                output_tokens=45,
                total_cost=0.000021,
            ),
            summary="Runtime stub prepared the task for review.",
        )


class FailingAgentRuntimeClient:
    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        raise TaskRunnerUnavailable("runtime offline")


def test_goal_routes_to_dev_agent() -> None:
    response = TestClient(app).post(
        "/goals",
        json={"goal": "Corriger un bug API sur le gateway", "priority": "high"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "agent-dev" in payload["target_agents"]
    assert payload["project_intent"]["priority"] == "high"


def test_goal_submit_persists_project_tasks_and_events() -> None:
    state_client = FakeStateClient()
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/goals/submit",
            json={
                "goal": "Traiter une facture fournisseur avec TVA",
                "priority": "high",
                "requester": "hugo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["project"]["goal"] == "Traiter une facture fournisseur avec TVA"
    assert payload["project"]["owner_agent_id"] == "agent-direction"
    assert payload["workspace"]["memory_scope"] == f"project:{payload['project']['id']}"
    assert payload["workspace"]["allowed_agent_ids"] == ["agent-direction", "agent-finance"]
    assert [assignment["agent_id"] for assignment in payload["assignments"]] == [
        "agent-direction",
        "agent-finance",
    ]
    assert [task["assigned_agent_id"] for task in payload["tasks"]] == [
        "agent-direction",
        "agent-finance",
        "agent-finance",
        "agent-direction",
    ]
    assert payload["tasks"][1]["depends_on"] == [payload["tasks"][0]["id"]]
    assert payload["tasks"][2]["depends_on"] == [payload["tasks"][1]["id"]]
    assert payload["tasks"][3]["depends_on"] == [payload["tasks"][2]["id"]]
    assert all(task["acceptance_criteria"] for task in payload["tasks"])
    assert [task["sequence"] for task in payload["tasks"]] == [1, 2, 3, 4]
    assert [event["type"] for event in payload["events"]] == [
        "goal.received",
        "routing.decided",
        "project.created",
        "task.created",
        "task.created",
        "task.created",
        "task.created",
    ]
    task_events = payload["events"][3:]
    assert [event["payload"]["sequence"] for event in task_events] == [1, 2, 3, 4]
    assert {event["trace_id"] for event in payload["events"]} == {payload["trace_id"]}
    assert payload["complexity_assessment"]["report"]["project_id"] == payload["project"]["id"]
    assert payload["complexity_assessment"]["report"]["split_recommended"] is False
    assert state_client.complexity_assessments[0].report.project_id == payload["project"]["id"]
    assert state_client.projects[0].id == payload["project"]["id"]
    assert state_client.workspaces[0].project_id == payload["project"]["id"]
    assert state_client.assignments[0].workspace_id == payload["workspace"]["id"]
    assert state_client.headers[0]["x-synarch-actor-id"] == "hugo"
    assert state_client.headers[0]["x-synarch-trace-id"] == payload["trace_id"]
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-goal-submitter"
    assert state_client.headers[-1]["x-synarch-trace-id"] == payload["trace_id"]


def test_goal_submit_returns_bad_gateway_when_state_service_is_unavailable() -> None:
    app.dependency_overrides[get_state_client] = FailingStateClient

    try:
        response = TestClient(app).post(
            "/goals/submit",
            json={"goal": "Corriger un bug API", "priority": "high"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "State service unavailable"


def test_gateway_applies_project_split_through_state_service() -> None:
    state_client = FakeStateClient()
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/project-split-requests/project-split-large/apply",
            headers={"X-Synarch-Trace-Id": "trace_gateway_split_apply"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["request_id"] == "project-split-large"
    assert payload["split_request"]["status"] == "applied"
    assert payload["shard_projects"][0]["title"] == "Large project - planning"
    assert state_client.split_applications[0].request_id == "project-split-large"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-project-split-applier"
    assert state_client.headers[-1]["x-synarch-trace-id"] == "trace_gateway_split_apply"


def test_tool_gate_authorizes_allowed_tool_and_records_logs() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-dev": LocalWorldView(
                agent_id="agent-dev",
                role="Code and infra",
                division="dev",
                permissions=PermissionBundle(
                    allowed_tools=["git.read", "event.emit"],
                    denied_tools=["payment.execute"],
                ),
                available_services=["connector-github", "service-event-log"],
                available_connector_ids=["connector-github"],
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_allowed"},
            json={
                "agent_id": "agent-dev",
                "tool_name": "git.read",
                "service_id": "connector-github",
                "project_id": "project_demo",
                "task_id": "task_demo",
                "reason": "Read code before editing.",
                "arguments": {"path": "README.md"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == "git.read"
    assert payload["output"]["authorized"] is True
    assert payload["output"]["executed"] is False
    assert payload["output"]["trace_id"] == "trace_tool_allowed"
    assert state_client.events[0].type == EventType.tool_called
    assert state_client.events[0].target == "task_demo"
    assert state_client.events[0].payload["argument_keys"] == ["path"]
    assert state_client.audit_logs[0].action == "tool.allowed"
    assert state_client.audit_logs[0].actor_id == "agent-dev"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-tool-gate"


def test_tool_gate_denies_forbidden_tool_and_records_logs() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-finance": LocalWorldView(
                agent_id="agent-finance",
                role="Finance",
                division="finance",
                permissions=PermissionBundle(
                    allowed_tools=["document.read", "ledger.write", "event.emit"],
                    denied_tools=["payment.execute"],
                ),
                available_services=["service-ledger"],
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_denied"},
            json={
                "agent_id": "agent-finance",
                "tool_name": "payment.execute",
                "service_id": "service-ledger",
                "reason": "Try to pay an invoice.",
                "arguments": {"invoice_id": "invoice_demo"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Tool denied for agent: payment.execute"
    assert state_client.events[0].type == EventType.tool_failed
    assert state_client.events[0].payload["error"] == "Tool denied for agent: payment.execute"
    assert state_client.audit_logs[0].action == "tool.denied"
    assert state_client.audit_logs[0].target_id == "payment.execute"


def test_tool_gate_executes_event_emit_adapter() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-direction": LocalWorldView(
                agent_id="agent-direction",
                role="Direction",
                division="direction",
                permissions=PermissionBundle(
                    allowed_tools=["event.emit"],
                    denied_tools=[],
                ),
                available_services=["service-event-log"],
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_event_emit_adapter"},
            json={
                "agent_id": "agent-direction",
                "tool_name": "event.emit",
                "service_id": "service-event-log",
                "project_id": "project_demo",
                "reason": "Report a project blocker.",
                "arguments": {
                    "type": "agent.reported",
                    "target": "project_demo",
                    "payload": {"summary": "Supplier response is blocked."},
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["executed"] is True
    assert payload["output"]["adapter"] == "event.emit"
    assert payload["output"]["emitted_event_type"] == "agent.reported"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.agent_reported,
    ]
    assert state_client.events[1].source_agent_id == "agent-direction"
    assert state_client.events[1].target == "project_demo"
    assert state_client.events[1].payload == {"summary": "Supplier response is blocked."}


def test_run_next_task_executes_first_ready_task() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_demo",
            title="Demo project",
            goal="Deliver a verified backend slice.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            project_id="project_demo",
            title="Ready task",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Ready task can produce a recorded result."],
        )
    )
    memory_client = FakeMemoryClient()
    runtime_client = FakeAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=memory_client,
        runtime=runtime_client,
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_gateway_runner_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trace_gateway_runner_test"
    assert payload["project"]["goal"] == "Deliver a verified backend slice."
    assert runtime_client.requests[0].project is not None
    assert runtime_client.requests[0].project.goal == "Deliver a verified backend slice."
    assert payload["task"]["status"] == "needs_review"
    assert payload["task"]["result"]["summary"] == "Runtime stub prepared the task for review."
    assert payload["world_view"]["agent_id"] == "agent-dev"
    assert payload["memory_context"]["summary"] == "Fake context assembled."
    assert memory_client.contexts[0].allowed_scopes == [
        "global",
        "division:dev",
        "agent:agent-dev",
        "project:project_demo",
    ]
    assert memory_client.items[0].scope == "project:project_demo"
    assert memory_client.items[0].agent_id == "agent-dev"
    assert memory_client.items[0].project_id == "project_demo"
    assert memory_client.items[0].status == "proposed"
    assert payload["agent_result"]["memory_candidates"][0]["status"] == "proposed"
    assert payload["cost_records"][0]["provider_id"] == "provider-local-runtime-stub"
    assert payload["cost_records"][0]["task_id"] == payload["task"]["id"]
    assert payload["cost_records"][0]["input_tokens"] == 123
    assert payload["cost_records"][0]["output_tokens"] == 45
    assert payload["cost_records"][0]["total_cost"] == 0.000021
    assert [event.type for event in state_client.events] == [
        "model_call.started",
        "model_call.completed",
        "memory.candidate_created",
    ]
    assert [event["type"] for event in payload["model_call_events"]] == [
        "model_call.started",
        "model_call.completed",
    ]
    assert [event["type"] for event in payload["memory_events"]] == [
        "memory.candidate_created",
    ]
    assert payload["memory_events"][0]["payload"]["status"] == "proposed"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-task-runner"


def test_list_memory_items_filters_review_queue() -> None:
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-candidate"] = MemoryItem(
        id="memory-candidate",
        scope="project:project_demo",
        content="Candidate memory.",
        status="proposed",
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-approved"] = MemoryItem(
        id="memory-approved",
        scope="project:project_demo",
        content="Approved memory.",
        status="approved",
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-other-project"] = MemoryItem(
        id="memory-other-project",
        scope="project:project_other",
        content="Other project candidate.",
        status="proposed",
        agent_id="agent-dev",
        project_id="project_other",
    )
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).get(
            "/memory-items",
            params={"project_id": "project_demo", "status": "proposed"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["memory-candidate"]


def test_operational_records_are_listed_through_gateway() -> None:
    state_client = FakeStateClient()
    state_client.events.extend(
        [
            EventRecord(
                id="event-model-call",
                type=EventType.model_call_completed,
                target="project_demo",
                trace_id="trace_ops",
            ),
            EventRecord(
                id="event-other",
                type=EventType.task_created,
                target="project_other",
                trace_id="trace_other",
            ),
        ]
    )
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-model-call",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                trace_id="trace_ops",
                total_cost=0.0005,
            ),
            CostRecord(
                id="cost-other",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                project_id="project_other",
                trace_id="trace_other",
            ),
        ]
    )
    state_client.audit_logs.extend(
        [
            AuditLogRecord(
                id="audit-model-call",
                actor_type="user",
                actor_id="hugo",
                action="cost.recorded",
                target_type="cost_record",
                target_id="cost-model-call",
                trace_id="trace_ops",
            ),
            AuditLogRecord(
                id="audit-other",
                actor_type="service",
                actor_id="gateway",
                action="event.recorded",
                target_type="event",
                target_id="event-other",
                trace_id="trace_other",
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        client = TestClient(app)
        events_response = client.get(
            "/events",
            params={"event_type": "model_call.completed", "trace_id": "trace_ops"},
        )
        costs_response = client.get(
            "/cost-records",
            params={"project_id": "project_demo", "trace_id": "trace_ops"},
        )
        audits_response = client.get(
            "/audit-logs",
            params={"actor_id": "hugo", "trace_id": "trace_ops"},
        )
    finally:
        app.dependency_overrides.clear()

    assert events_response.status_code == 200
    assert [event["id"] for event in events_response.json()] == ["event-model-call"]
    assert costs_response.status_code == 200
    assert [cost["id"] for cost in costs_response.json()] == ["cost-model-call"]
    assert audits_response.status_code == 200
    assert [audit["id"] for audit in audits_response.json()] == ["audit-model-call"]


def test_cost_summary_groups_filtered_records() -> None:
    state_client = FakeStateClient()
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-direction-1",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                input_tokens=100,
                output_tokens=50,
                total_cost=0.25,
            ),
            CostRecord(
                id="cost-direction-2",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                input_tokens=40,
                output_tokens=20,
                total_cost=0.25,
            ),
            CostRecord(
                id="cost-dev",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-dev",
                project_id="project_demo",
                input_tokens=10,
                output_tokens=5,
                total_cost=0.5,
            ),
            CostRecord(
                id="cost-other-project",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_other",
                input_tokens=999,
                output_tokens=999,
                total_cost=9.0,
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).get(
            "/cost-records/summary",
            params={"project_id": "project_demo", "group_by": "agent"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_by"] == "agent"
    assert payload["record_count"] == 3
    assert payload["input_tokens"] == 150
    assert payload["output_tokens"] == 75
    assert payload["total_cost"] == 1.0
    assert payload["groups"] == [
        {
            "group_key": "agent-dev",
            "record_count": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_cost": 0.5,
            "currency": "USD",
        },
        {
            "group_key": "agent-direction",
            "record_count": 2,
            "input_tokens": 140,
            "output_tokens": 70,
            "total_cost": 0.5,
            "currency": "USD",
        },
    ]


def test_cost_budget_evaluation_uses_filtered_records() -> None:
    state_client = FakeStateClient()
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-1",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                input_tokens=100,
                output_tokens=50,
                total_cost=0.4,
            ),
            CostRecord(
                id="cost-2",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-dev",
                project_id="project_demo",
                input_tokens=200,
                output_tokens=100,
                total_cost=0.7,
            ),
            CostRecord(
                id="cost-other",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_other",
                input_tokens=999,
                output_tokens=999,
                total_cost=9.0,
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).get(
            "/cost-records/budget",
            params={"project_id": "project_demo", "budget": "1.0"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["budget"] == 1.0
    assert payload["spent"] == 1.1
    assert payload["remaining"] == -0.1
    assert payload["usage_ratio"] == 1.1
    assert payload["budget_exceeded"] is True
    assert payload["record_count"] == 2
    assert payload["input_tokens"] == 300
    assert payload["output_tokens"] == 150


def test_project_timeline_aggregates_project_records() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_demo",
            title="Demo project",
            goal="Track project execution.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task-demo",
                project_id="project_demo",
                title="Demo task",
                assigned_agent_id="agent-direction",
                acceptance_criteria=["Timeline contains project records."],
            ),
            TaskRecord(
                id="task-other",
                project_id="project_other",
                title="Other task",
                assigned_agent_id="agent-direction",
                acceptance_criteria=["Other project task is excluded."],
            ),
        ]
    )
    state_client.events.extend(
        [
            EventRecord(
                id="event-project",
                type=EventType.task_created,
                target="project_demo",
                trace_id="trace_demo",
            ),
            EventRecord(
                id="event-task",
                type=EventType.model_call_completed,
                target="task-demo",
                trace_id="trace_demo",
            ),
            EventRecord(
                id="event-other",
                type=EventType.task_created,
                target="project_other",
                trace_id="trace_other",
            ),
        ]
    )
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-demo",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                project_id="project_demo",
                trace_id="trace_demo",
                total_cost=0.25,
            ),
            CostRecord(
                id="cost-other",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                project_id="project_other",
                trace_id="trace_other",
                total_cost=1.0,
            ),
        ]
    )
    state_client.audit_logs.extend(
        [
            AuditLogRecord(
                id="audit-project",
                actor_type="user",
                actor_id="hugo",
                action="task.created",
                target_type="task",
                target_id="task-demo",
                payload={"project_id": "project_demo"},
                trace_id="trace_demo",
            ),
            AuditLogRecord(
                id="audit-other",
                actor_type="user",
                actor_id="hugo",
                action="task.created",
                target_type="task",
                target_id="task-other",
                payload={"project_id": "project_other"},
                trace_id="trace_other",
            ),
        ]
    )
    memory_client.items_by_id["memory-demo"] = MemoryItem(
        id="memory-demo",
        scope="project:project_demo",
        content="Demo memory.",
        project_id="project_demo",
        status="proposed",
    )
    memory_client.items_by_id["memory-other"] = MemoryItem(
        id="memory-other",
        scope="project:project_other",
        content="Other memory.",
        project_id="project_other",
        status="proposed",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).get("/projects/project_demo/timeline")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project_demo"
    assert payload["project"]["id"] == "project_demo"
    assert [task["id"] for task in payload["tasks"]] == ["task-demo"]
    assert [event["id"] for event in payload["events"]] == ["event-project", "event-task"]
    assert [cost["id"] for cost in payload["cost_records"]] == ["cost-demo"]
    assert [audit["id"] for audit in payload["audit_logs"]] == ["audit-project"]
    assert [item["id"] for item in payload["memory_items"]] == ["memory-demo"]
    assert payload["total_cost"] == 0.25


def test_update_memory_item_status_records_gateway_event() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-candidate"] = MemoryItem(
        id="memory-candidate",
        scope="project:project_demo",
        content="Candidate memory.",
        status="proposed",
        agent_id="agent-dev",
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).patch(
            "/memory-items/memory-candidate/status",
            json={"status": "approved"},
            headers={
                "X-Synarch-Actor-Type": "user",
                "X-Synarch-Actor-Id": "hugo",
                "X-Synarch-Trace-Id": "trace_memory_review_test",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert [event.type for event in state_client.events] == ["memory.status_updated"]
    assert state_client.events[0].target == "project_demo"
    assert state_client.events[0].payload == {
        "memory_id": "memory-candidate",
        "scope": "project:project_demo",
        "status": "approved",
        "project_id": "project_demo",
        "agent_id": "agent-dev",
    }
    assert state_client.events[0].trace_id == "trace_memory_review_test"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "hugo"


def test_run_next_task_records_failed_model_call_when_runtime_is_unavailable() -> None:
    state_client = FakeStateClient()
    state_client.tasks.append(
        TaskRecord(
            project_id="project_demo",
            title="Ready task",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Ready task can produce a recorded result."],
        )
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FailingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_gateway_runner_failure_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "failed"
    assert payload["agent_result"]["status"] == "failed"
    assert payload["cost_records"] == []
    assert "runtime offline" in payload["agent_result"]["summary"]
    assert [event.type for event in state_client.events] == [
        "model_call.started",
        "model_call.failed",
    ]
    assert [event["type"] for event in payload["model_call_events"]] == [
        "model_call.started",
        "model_call.failed",
    ]
    assert state_client.events[1].trace_id == "trace_gateway_runner_failure_test"


def test_run_next_task_returns_404_when_no_task_is_ready() -> None:
    runner = TaskRunner(
        state=FakeStateClient(),
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post("/tasks/run-next")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "No queued task is ready to run"
