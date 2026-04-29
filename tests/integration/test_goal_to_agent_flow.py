import pytest
from fastapi.testclient import TestClient

from synarch_agent_runtime.main import app as agent_runtime_app
from synarch_control_plane.main import app as control_plane_app
from synarch_event_service.main import app as event_service_app
from synarch_gateway.main import app as gateway_app
from synarch_gateway.main import get_state_client, get_task_runner
from synarch_gateway.state_client import StateServiceRequestError
from synarch_gateway.task_runner import (
    LOCAL_RUNTIME_MODEL_ID,
    LOCAL_RUNTIME_PROVIDER_ID,
    TaskRunner,
    TaskRunnerRequestError,
)
from synarch_memory_service.main import app as memory_service_app
from synarch_models import (
    AgentProjectAssignment,
    AgentResult,
    AgentTaskRequest,
    CostRecord,
    EventRecord,
    LocalWorldView,
    MemoryContext,
    ProjectRecord,
    ProjectWorkspace,
    TaskRecord,
)
from synarch_state_service.main import app as state_service_app
from synarch_state_service.main import reset_repositories


class StateServiceTestClient:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        response = self.client.post(
            "/projects",
            json=project.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 201:
            raise StateServiceRequestError(response.status_code, response.json())
        return ProjectRecord.model_validate(response.json())

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self.client.post(
            "/tasks",
            json=task.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 201:
            raise StateServiceRequestError(response.status_code, response.json())
        return TaskRecord.model_validate(response.json())

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace:
        response = self.client.post(
            "/project-workspaces",
            json=workspace.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 201:
            raise StateServiceRequestError(response.status_code, response.json())
        return ProjectWorkspace.model_validate(response.json())

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment:
        response = self.client.post(
            "/agent-project-assignments",
            json=assignment.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 201:
            raise StateServiceRequestError(response.status_code, response.json())
        return AgentProjectAssignment.model_validate(response.json())

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        response = self.client.post(
            "/events",
            json=event.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 201:
            raise StateServiceRequestError(response.status_code, response.json())
        return EventRecord.model_validate(response.json())

    def list_tasks(self) -> list[TaskRecord]:
        response = self.client.get("/tasks")
        if response.status_code != 200:
            raise StateServiceRequestError(response.status_code, response.json())
        return [TaskRecord.model_validate(task) for task in response.json()]

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self.client.post(f"/tasks/{task_id}/start", headers=headers)
        if response.status_code != 200:
            raise StateServiceRequestError(response.status_code, response.json())
        return TaskRecord.model_validate(response.json())

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self.client.post(
            f"/tasks/{task_id}/results",
            json=result.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 200:
            raise StateServiceRequestError(response.status_code, response.json())
        return TaskRecord.model_validate(response.json())

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord:
        response = self.client.post(
            "/cost-records",
            json=cost.model_dump(mode="json"),
            headers=headers,
        )
        if response.status_code != 201:
            raise StateServiceRequestError(response.status_code, response.json())
        return CostRecord.model_validate(response.json())


class ControlPlaneTestClient:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def get_world_view(self, agent_id: str) -> LocalWorldView:
        response = self.client.get(f"/agents/{agent_id}/world-view")
        if response.status_code != 200:
            raise TaskRunnerRequestError(response.status_code, response.json())
        return LocalWorldView.model_validate(response.json())


class MemoryServiceTestClient:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def assemble_context(self, context: MemoryContext) -> MemoryContext:
        response = self.client.post("/context/assemble", json=context.model_dump(mode="json"))
        if response.status_code != 200:
            raise TaskRunnerRequestError(response.status_code, response.json())
        return MemoryContext.model_validate(response.json())


class AgentRuntimeTestClient:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        response = self.client.post("/tasks/run", json=request.model_dump(mode="json"))
        if response.status_code != 200:
            raise TaskRunnerRequestError(response.status_code, response.json())
        return AgentResult.model_validate(response.json())


@pytest.mark.integration
def test_goal_to_agent_result_flow_across_current_layers() -> None:
    reset_repositories()
    gateway = TestClient(gateway_app)
    control_plane = TestClient(control_plane_app)
    state = TestClient(state_service_app)
    memory = TestClient(memory_service_app)
    events = TestClient(event_service_app)
    agent_runtime = TestClient(agent_runtime_app)

    provider_response = state.post(
        "/model-providers",
        json={
            "id": LOCAL_RUNTIME_PROVIDER_ID,
            "name": "Local Runtime Stub",
            "provider_type": "local",
            "default_model_id": LOCAL_RUNTIME_MODEL_ID,
        },
    )
    assert provider_response.status_code == 201
    model_response = state.post(
        "/model-definitions",
        json={
            "id": LOCAL_RUNTIME_MODEL_ID,
            "provider_id": LOCAL_RUNTIME_PROVIDER_ID,
            "display_name": "Local Runtime Stub",
            "input_cost_per_million_tokens": 0.01,
            "output_cost_per_million_tokens": 0.02,
        },
    )
    assert model_response.status_code == 201
    for agent_id, division in [
        ("agent-direction", "direction"),
        ("agent-finance", "finance"),
    ]:
        agent_response = state.post(
            "/agents",
            json={
                "id": agent_id,
                "name": agent_id,
                "role": "Integration participant",
                "division": division,
            },
        )
        assert agent_response.status_code == 201

    gateway_app.dependency_overrides[get_state_client] = lambda: StateServiceTestClient(state)
    try:
        submission_response = gateway.post(
            "/goals/submit",
            json={
                "goal": "Traiter une facture fournisseur avec TVA et rapprochement bancaire",
                "priority": "high",
                "requester": "integration-test",
            },
        )
    finally:
        gateway_app.dependency_overrides.clear()

    assert submission_response.status_code == 201
    submission = submission_response.json()
    assert "agent-finance" in submission["routing_decision"]["target_agents"]
    assert len(submission["tasks"]) == 4
    assert all(task["acceptance_criteria"] for task in submission["tasks"])
    assert submission["workspace"]["memory_scope"] == f"project:{submission['project']['id']}"
    assert {assignment["agent_id"] for assignment in submission["assignments"]} == {
        "agent-direction",
        "agent-finance",
    }
    project = submission["project"]

    timeline_response = state.get("/events", params={"trace_id": submission["trace_id"]})
    assert timeline_response.status_code == 200
    assert [event["type"] for event in timeline_response.json()] == [
        "project_workspace.created",
        "agent_project.assigned",
        "agent_project.assigned",
        "goal.received",
        "routing.decided",
        "project.created",
        "task.created",
        "task.created",
        "task.created",
        "task.created",
    ]

    audit_response = state.get("/audit-logs", params={"trace_id": submission["trace_id"]})
    assert audit_response.status_code == 200
    assert {record["actor_id"] for record in audit_response.json()} == {"integration-test"}

    memory_item_response = memory.post(
        "/memory-items",
        json={
            "scope": "division:finance",
            "agent_id": "agent-finance",
            "project_id": project["id"],
            "content": "Les paiements fournisseurs restent interdits sans validation humaine.",
        },
    )
    assert memory_item_response.status_code == 201

    runner = TaskRunner(
        state=StateServiceTestClient(state),
        control_plane=ControlPlaneTestClient(control_plane),
        memory=MemoryServiceTestClient(memory),
        runtime=AgentRuntimeTestClient(agent_runtime),
    )
    gateway_app.dependency_overrides[get_task_runner] = lambda: runner
    try:
        direction_run_response = gateway.post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": submission["trace_id"]},
        )
        finance_run_response = gateway.post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": submission["trace_id"]},
        )
    finally:
        gateway_app.dependency_overrides.clear()

    assert direction_run_response.status_code == 200
    direction_run = direction_run_response.json()
    assert direction_run["task"]["assigned_agent_id"] == "agent-direction"
    assert direction_run["task"]["status"] == "completed"
    assert [event["type"] for event in direction_run["model_call_events"]] == [
        "model_call.started",
        "model_call.completed",
    ]
    assert direction_run["cost_records"][0]["total_cost"] > 0

    assert finance_run_response.status_code == 200
    finance_run = finance_run_response.json()
    assert finance_run["world_view"]["agent_id"] == "agent-finance"
    assert finance_run["world_view"]["soul"]["id"] == "soul-agent-finance-v1"
    assert finance_run["world_view"]["soul"]["created_by"] == "agent-direction"
    assert "payment.execute" in finance_run["world_view"]["permissions"]["denied_tools"]
    assert finance_run["memory_context"]["items"][0]["content"].startswith(
        "Les paiements fournisseurs"
    )

    task = finance_run["task"]
    agent_result = finance_run["agent_result"]
    assert agent_result["status"] == "needs_review"
    assert agent_result["events_emitted"]
    assert task["status"] == "needs_review"
    assert task["result"]["summary"] == agent_result["summary"]
    assert finance_run["cost_records"][0]["model_id"] == LOCAL_RUNTIME_MODEL_ID
    assert finance_run["cost_records"][0]["task_id"] == task["id"]

    state_timeline_response = state.get("/events", params={"trace_id": submission["trace_id"]})
    assert state_timeline_response.status_code == 200
    state_events = state_timeline_response.json()
    assert "task.started" in [event["type"] for event in state_events]
    assert "task.completed" in [event["type"] for event in state_events]
    assert "model_call.started" in [event["type"] for event in state_events]
    assert "model_call.completed" in [event["type"] for event in state_events]
    assert "cost.recorded" in [event["type"] for event in state_events]
    assert any(
        event["type"] == "agent.reported" and event["payload"]["task_id"] == task["id"]
        for event in state_events
    )
    costs_response = state.get("/cost-records", params={"trace_id": submission["trace_id"]})
    assert costs_response.status_code == 200
    assert len(costs_response.json()) == 2
    model_costs_response = state.get("/cost-records", params={"model_id": LOCAL_RUNTIME_MODEL_ID})
    assert model_costs_response.status_code == 200
    assert len(model_costs_response.json()) == 2

    event_response = events.post("/events", json=agent_result["events_emitted"][0])
    assert event_response.status_code == 202

    timeline_response = events.get("/events", params={"event_type": "agent.reported"})
    assert timeline_response.status_code == 200
    assert any(event["payload"]["task_id"] == task["id"] for event in timeline_response.json())
