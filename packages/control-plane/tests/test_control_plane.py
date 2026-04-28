from fastapi.testclient import TestClient

from synarch_control_plane.main import app


def test_world_view_is_limited_to_agent_scope() -> None:
    response = TestClient(app).get("/agents/agent-dev/world-view")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-dev"
    assert payload["division"] == "dev"
    assert "payment.execute" in payload["permissions"]["denied_tools"]
