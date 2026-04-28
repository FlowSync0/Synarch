import pytest
from fastapi.testclient import TestClient

from synarch_agent_runtime.main import app as agent_runtime_app
from synarch_control_plane.main import app as control_plane_app
from synarch_event_service.main import app as event_service_app
from synarch_gateway.main import app as gateway_app
from synarch_memory_service.main import app as memory_service_app
from synarch_state_service.main import app as state_service_app


@pytest.mark.integration
def test_goal_to_agent_result_flow_across_current_layers() -> None:
    gateway = TestClient(gateway_app)
    control_plane = TestClient(control_plane_app)
    state = TestClient(state_service_app)
    memory = TestClient(memory_service_app)
    events = TestClient(event_service_app)
    agent_runtime = TestClient(agent_runtime_app)

    routing_response = gateway.post(
        "/goals",
        json={
            "goal": "Traiter une facture fournisseur avec TVA et rapprochement bancaire",
            "priority": "high",
            "requester": "integration-test",
        },
    )
    assert routing_response.status_code == 200
    routing = routing_response.json()
    assert "agent-finance" in routing["target_agents"]

    project_response = state.post(
        "/projects",
        json={
            "title": routing["project_intent"]["title"],
            "goal": routing["project_intent"]["goal"],
            "priority": routing["project_intent"]["priority"],
            "owner_agent_id": routing["project_intent"]["owner_agent_id"],
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()

    specialist_draft = next(
        draft for draft in routing["task_drafts"] if draft["assigned_agent_id"] == "agent-finance"
    )
    task_response = state.post(
        "/tasks",
        json={
            "project_id": project["id"],
            "title": specialist_draft["title"],
            "assigned_agent_id": specialist_draft["assigned_agent_id"],
            "depends_on": specialist_draft["depends_on"],
        },
    )
    assert task_response.status_code == 201
    task = task_response.json()

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

    event_response = events.post("/events", json=agent_result["events_emitted"][0])
    assert event_response.status_code == 202

    timeline_response = events.get("/events", params={"event_type": "agent.reported"})
    assert timeline_response.status_code == 200
    assert any(event["payload"]["task_id"] == task["id"] for event in timeline_response.json())
