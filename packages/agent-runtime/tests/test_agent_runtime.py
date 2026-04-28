from fastapi.testclient import TestClient

from synarch_agent_runtime.main import app


def test_runtime_returns_review_result() -> None:
    response = TestClient(app).post(
        "/tasks/run",
        json={
            "task": {
                "project_id": "project_demo",
                "title": "Draft plan",
                "assigned_agent_id": "agent-dev",
            },
            "world_view": {
                "agent_id": "agent-dev",
                "role": "Code and infra",
                "division": "dev",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-dev"
    assert payload["status"] == "needs_review"
