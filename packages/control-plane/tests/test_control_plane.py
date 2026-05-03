import json

import httpx
import pytest
from fastapi.testclient import TestClient

from synarch_control_plane.agent_sources import StateServiceAgentSource
from synarch_control_plane.main import app, set_agent_source
from synarch_control_plane.seed import AGENT_SOULS, AGENTS


def setup_function() -> None:
    set_agent_source()


def teardown_function() -> None:
    set_agent_source()


def test_world_view_is_limited_to_agent_scope() -> None:
    response = TestClient(app).get("/agents/agent-dev/world-view")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-dev"
    assert payload["name"] == "IA Dev"
    assert payload["division"] == "dev"
    assert payload["manager"] == "agent-direction"
    assert payload["manager_agent_id"] == "agent-direction"
    assert payload["peers"] == []
    assert payload["peer_agent_ids"] == []
    assert payload["direct_report_agent_ids"] == []
    assert payload["soul"]["agent_id"] == "agent-dev"
    assert payload["soul"]["identity"].startswith("IA Dev")
    assert "payment.execute" in payload["permissions"]["denied_tools"]


def test_agents_can_be_read_from_state_service(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/agents":
            return httpx.Response(
                200,
                json=[AGENTS[0].model_dump(mode="json"), AGENTS[1].model_dump(mode="json")],
            )
        if request.url.path == "/agents/agent-finance":
            return httpx.Response(200, json=AGENTS[1].model_dump(mode="json"))
        if request.url.path == "/agents/agent-finance/soul":
            return httpx.Response(200, json=AGENT_SOULS[1].model_dump(mode="json"))
        if request.url.path == "/agent-project-assignments":
            assert request.url.params["agent_id"] == "agent-finance"
            assert request.url.params["active"] == "true"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "assignment-finance-demo",
                        "project_id": "project-finance-demo",
                        "workspace_id": "workspace-finance-demo",
                        "agent_id": "agent-finance",
                        "assignment_role": "contributor",
                    }
                ],
            )
        if request.url.path == "/services":
            return httpx.Response(200, json=[])
        if request.url.path == "/skills":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={"detail": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", client.get)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).get("/agents/agent-finance/world-view")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-finance"
    assert payload["name"] == "IA Finance"
    assert payload["manager"] == "agent-direction"
    assert payload["manager_agent_id"] == "agent-direction"
    assert payload["peer_agent_ids"] == []
    assert payload["direct_report_agent_ids"] == []
    assert payload["soul"]["id"] == "soul-agent-finance-v1"
    assert payload["active_projects"] == ["project-finance-demo"]


def test_state_service_source_404_becomes_control_plane_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", client.get)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).get("/agents/missing-agent")

    assert response.status_code == 404


def test_world_view_includes_state_backed_services_and_model_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finance_agent = AGENTS[1].model_copy(update={"model_policy_id": "policy-finance-default"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/agents":
            return httpx.Response(200, json=[finance_agent.model_dump(mode="json")])
        if request.url.path == "/agents/agent-finance":
            return httpx.Response(200, json=finance_agent.model_dump(mode="json"))
        if request.url.path == "/agents/agent-finance/soul":
            return httpx.Response(404, json={"detail": "No active soul for agent: agent-finance"})
        if request.url.path == "/agent-project-assignments":
            return httpx.Response(200, json=[])
        if request.url.path == "/services":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "service-ledger",
                        "name": "Ledger",
                        "kind": "internal",
                        "capabilities": ["ledger.write"],
                    },
                    {
                        "id": "connector-finance-docs",
                        "name": "Finance Documents",
                        "kind": "tool_provider",
                        "capabilities": ["document.read"],
                        "allowed_divisions": ["finance"],
                    },
                    {
                        "id": "connector-dev-github",
                        "name": "GitHub",
                        "kind": "tool_provider",
                        "capabilities": ["git.read"],
                        "allowed_divisions": ["dev"],
                    },
                ],
            )
        if request.url.path == "/skills":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "invoice_ocr",
                        "name": "Invoice OCR",
                        "required_tools": ["document.read"],
                        "allowed_divisions": ["finance"],
                    },
                    {
                        "id": "software_design",
                        "name": "Software Design",
                        "required_tools": ["git.read"],
                        "allowed_divisions": ["dev"],
                    },
                    {
                        "id": "bank_reconciliation",
                        "name": "Bank Reconciliation",
                        "required_tools": ["payment.execute"],
                        "allowed_divisions": ["finance"],
                    },
                ],
            )
        if request.url.path == "/model-policies/policy-finance-default":
            return httpx.Response(
                200,
                json={
                    "id": "policy-finance-default",
                    "name": "Finance default",
                    "default_model_id": "model-finance",
                    "allowed_model_ids": ["model-finance"],
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", client.get)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).get("/agents/agent-finance/world-view")

    assert response.status_code == 200
    payload = response.json()
    assert "service-ledger" in payload["available_services"]
    assert "connector-finance-docs" in payload["available_services"]
    assert "connector-dev-github" not in payload["available_services"]
    assert payload["available_connector_ids"] == ["connector-finance-docs"]
    assert payload["available_skill_ids"] == ["invoice_ocr"]
    assert "model_policy:policy-finance-default" in payload["policies"]
    assert "default_model:model-finance" in payload["policies"]


def test_lifecycle_requests_can_be_listed_from_state_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/agent-lifecycle-requests":
            assert request.url.params["status"] == "requested"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "lifecycle-create-reviewer",
                        "action": "create_agent",
                        "requested_by_type": "agent",
                        "requested_by_id": "agent-direction",
                        "reason": "Create reviewer",
                    }
                ],
            )
        return httpx.Response(404, json={"detail": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", client.get)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).get("/agent-lifecycle-requests", params={"status": "requested"})

    assert response.status_code == 200
    assert response.json()[0]["id"] == "lifecycle-create-reviewer"


def test_lifecycle_request_creation_forwards_actor_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["actor_id"] = request.headers["x-synarch-actor-id"]
        captured["trace_id"] = request.headers["x-synarch-trace-id"]
        payload = json.loads(request.content)
        assert payload["id"] == "lifecycle-create-dev-reviewer"
        return httpx.Response(201, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "post", client.post)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).post(
        "/agent-lifecycle-requests",
        headers={
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": "trace_control_lifecycle_create",
        },
        json={
            "id": "lifecycle-create-dev-reviewer",
            "action": "create_agent",
            "requested_by_type": "user",
            "requested_by_id": "local-user",
            "reason": "Create a dev reviewer",
            "proposed_agent": {
                "id": "agent-dev-reviewer",
                "name": "IA Dev Reviewer",
                "role": "Review code changes",
                "division": "dev",
            },
        },
    )

    assert response.status_code == 201
    assert captured == {
        "actor_id": "local-user",
        "trace_id": "trace_control_lifecycle_create",
    }


def test_lifecycle_decision_is_forwarded_to_state_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent-lifecycle-requests/lifecycle-create-dev/decisions"
        payload = json.loads(request.content)
        assert payload["status"] == "approved"
        return httpx.Response(
            201,
            json={
                **payload,
                "status": "applied",
                "events_emitted": [
                    {
                        "type": "approval.decided",
                        "target": "lifecycle-create-dev",
                        "payload": {},
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "post", client.post)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).post(
        "/agent-lifecycle-requests/lifecycle-create-dev/decisions",
        headers={"X-Synarch-Trace-Id": "trace_control_lifecycle_decision"},
        json={
            "request_id": "lifecycle-create-dev",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Looks safe.",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "applied"


def test_lifecycle_write_conflict_is_preserved_from_state_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Lifecycle request is already applied"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "post", client.post)
    set_agent_source(StateServiceAgentSource("http://state-service:8020"))

    response = TestClient(app).post(
        "/agent-lifecycle-requests/lifecycle-create-dev/decisions",
        json={
            "request_id": "lifecycle-create-dev",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Duplicate approval.",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Lifecycle request is already applied"
