import httpx
from fastapi.testclient import TestClient

from synarch_control_plane.agent_sources import StateServiceAgentSource
from synarch_control_plane.main import app, set_agent_source
from synarch_control_plane.seed import AGENTS


def setup_function() -> None:
    set_agent_source()


def teardown_function() -> None:
    set_agent_source()


def test_world_view_is_limited_to_agent_scope() -> None:
    response = TestClient(app).get("/agents/agent-dev/world-view")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-dev"
    assert payload["division"] == "dev"
    assert "payment.execute" in payload["permissions"]["denied_tools"]


def test_agents_can_be_read_from_state_service(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/agents":
            return httpx.Response(
                200,
                json=[AGENTS[0].model_dump(mode="json"), AGENTS[1].model_dump(mode="json")],
            )
        if request.url.path == "/agents/agent-finance":
            return httpx.Response(200, json=AGENTS[1].model_dump(mode="json"))
        return httpx.Response(404, json={"detail": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", client.get)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).get("/agents/agent-finance/world-view")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-finance"
    assert payload["manager"] == "agent-direction"


def test_state_service_source_404_becomes_control_plane_404(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", client.get)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).get("/agents/missing-agent")

    assert response.status_code == 404
