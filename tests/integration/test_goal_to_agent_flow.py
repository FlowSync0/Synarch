import pytest
from fastapi.testclient import TestClient

from synarch_agent_runtime.main import app as agent_runtime_app
from synarch_control_plane.main import app as control_plane_app
from synarch_event_service.main import app as event_service_app
from synarch_gateway.main import app as gateway_app
from synarch_gateway.main import get_state_client
from synarch_gateway.state_client import StateServiceRequestError
from synarch_memory_service.main import app as memory_service_app
from synarch_models import EventRecord, ProjectRecord, TaskRecord
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


@pytest.mark.integration
def test_goal_to_agent_result_flow_across_current_layers() -> None:
    reset_repositories()
    gateway = TestClient(gateway_app)
    control_plane = TestClient(control_plane_app)
    state = TestClient(state_service_app)
    memory = TestClient(memory_service_app)
    events = TestClient(event_service_app)
    agent_runtime = TestClient(agent_runtime_app)

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
    project = submission["project"]

    timeline_response = state.get("/events", params={"trace_id": submission["trace_id"]})
    assert timeline_response.status_code == 200
    assert [event["type"] for event in timeline_response.json()] == [
        "goal.received",
        "routing.decided",
        "project.created",
        "task.created",
        "task.created",
    ]

    audit_response = state.get("/audit-logs", params={"trace_id": submission["trace_id"]})
    assert audit_response.status_code == 200
    assert {record["actor_id"] for record in audit_response.json()} == {"integration-test"}

    task = next(
        task for task in submission["tasks"] if task["assigned_agent_id"] == "agent-finance"
    )

    world_view_response = control_plane.get(f"/agents/{task['assigned_agent_id']}/world-view")
    assert world_view_response.status_code == 200
    world_view = world_view_response.json()
    assert world_view["agent_id"] == "agent-finance"
    assert "payment.execute" in world_view["permissions"]["denied_tools"]

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

    context_response = memory.post(
        "/context/assemble",
        json={"agent_id": "agent-finance", "project_id": project["id"], "token_budget": 1200},
    )
    assert context_response.status_code == 200
    memory_context = context_response.json()
    assert memory_context["items"][0]["content"].startswith("Les paiements fournisseurs")

    result_response = agent_runtime.post(
        "/tasks/run",
        json={"task": task, "world_view": world_view, "memory_context": memory_context},
    )
    assert result_response.status_code == 200
    agent_result = result_response.json()
    assert agent_result["status"] == "needs_review"
    assert agent_result["events_emitted"]

    result_record_response = state.post(
        f"/tasks/{task['id']}/results",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": task["assigned_agent_id"],
            "X-Synarch-Trace-Id": submission["trace_id"],
        },
        json=agent_result,
    )
    assert result_record_response.status_code == 200
    recorded_task = result_record_response.json()
    assert recorded_task["status"] == "needs_review"
    assert recorded_task["result"]["summary"] == agent_result["summary"]

    state_timeline_response = state.get("/events", params={"trace_id": submission["trace_id"]})
    assert state_timeline_response.status_code == 200
    assert any(
        event["type"] == "agent.reported" and event["payload"]["task_id"] == task["id"]
        for event in state_timeline_response.json()
    )

    event_response = events.post("/events", json=agent_result["events_emitted"][0])
    assert event_response.status_code == 202

    timeline_response = events.get("/events", params={"event_type": "agent.reported"})
    assert timeline_response.status_code == 200
    assert any(event["payload"]["task_id"] == task["id"] for event in timeline_response.json())
