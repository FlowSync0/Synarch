from fastapi.testclient import TestClient

from synarch_state_service.main import app


def test_project_then_task_flow() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Gateway API phase 1",
            "goal": "Create the first gateway route",
            "owner_agent_id": "agent-direction",
        },
    )

    assert project_response.status_code == 201
    project = project_response.json()

    task_response = client.post(
        "/tasks",
        json={
            "project_id": project["id"],
            "title": "Implement route",
            "assigned_agent_id": "agent-dev",
        },
    )

    assert task_response.status_code == 201
    assert task_response.json()["project_id"] == project["id"]
