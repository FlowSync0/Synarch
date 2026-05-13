import httpx
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from synarch_agent_runtime import main as runtime_main
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


def test_runtime_completes_direction_clarification_step() -> None:
    response = TestClient(app).post(
        "/tasks/run",
        json={
            "task": {
                "project_id": "project_demo",
                "title": "Clarify success criteria",
                "assigned_agent_id": "agent-direction",
            },
            "world_view": {
                "agent_id": "agent-direction",
                "role": "Direction",
                "division": "direction",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "agent-direction"
    assert payload["status"] == "completed"


def test_runtime_can_call_openrouter_with_fake_response(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "openrouter")
    monkeypatch.setattr(runtime_main.settings, "openrouter_input_cost_per_million_tokens", 0.10)
    monkeypatch.setattr(runtime_main.settings, "openrouter_output_cost_per_million_tokens", 0.20)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "deepseek/deepseek-v4-flash"
        assert json["reasoning"] == {"effort": "none", "exclude": True}
        messages = json["messages"]
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        assert '"tool_results": []' in str(user_message["content"])
        assert timeout == runtime_main.settings.openrouter_timeout_seconds
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"status":"needs_review",'
                                '"summary":"DeepSeek prepared the work package.",'
                                '"actions_taken":["Reviewed task and context"],'
                                '"sub_tasks_created":[{'
                                '"title":"Verify supplier source",'
                                '"description":"Check one supplier source before contact.",'
                                '"assigned_agent_id":"agent-dev",'
                                '"depends_on":[],'
                                '"acceptance_criteria":["Source URL and blocker are recorded."],'
                                '"sequence":1}],'
                                '"tool_calls_requested":[{'
                                '"tool_name":"web.fetch",'
                                '"service_id":"connector-supplier-web",'
                                '"reason":"Fetch source evidence.",'
                                '"arguments":{"url":"https://example.com"}}],'
                                '"memory_candidates":["Remember supplier MOQ constraint."]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    response = TestClient(app).post(
        "/tasks/run",
        json={
            "provider_id": "provider-openrouter",
            "model_id": "deepseek/deepseek-v4-flash",
            "task": {
                "id": "task_openrouter_demo",
                "project_id": "project_demo",
                "title": "Draft plan",
                "assigned_agent_id": "agent-dev",
                "acceptance_criteria": ["Plan has a verifiable next action."],
            },
            "world_view": {
                "agent_id": "agent-dev",
                "role": "Code and infra",
                "division": "dev",
                "permissions": {
                    "allowed_tools": ["web.fetch"],
                    "denied_tools": [],
                    "can_read_scopes": [],
                    "can_write_scopes": [],
                },
                "available_services": ["connector-supplier-web"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_review"
    assert payload["summary"] == "DeepSeek prepared the work package."
    assert payload["actions_taken"] == ["Reviewed task and context"]
    assert payload["sub_tasks_created"][0]["title"] == "Verify supplier source"
    assert payload["sub_tasks_created"][0]["acceptance_criteria"] == [
        "Source URL and blocker are recorded."
    ]
    assert payload["tool_calls_requested"][0]["tool_name"] == "web.fetch"
    assert payload["tool_calls_requested"][0]["service_id"] == "connector-supplier-web"
    assert payload["tool_calls_requested"][0]["arguments"] == {"url": "https://example.com"}
    assert payload["memory_candidates"][0]["content"] == "Remember supplier MOQ constraint."
    assert payload["model_usage"] == {
        "provider_id": "provider-openrouter",
        "model_id": "deepseek/deepseek-v4-flash",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_cost": 0.00002,
        "currency": "USD",
    }


def test_runtime_can_call_model_gateway_with_fake_response(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "model_gateway")
    monkeypatch.setattr(runtime_main.settings, "model_gateway_url", "http://model-gateway:8060")

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        assert url == "http://model-gateway:8060/model-calls/complete"
        assert json["agent_id"] == "agent-dev"
        assert json["purpose"] == "agent_task"
        assert json["provider_id"] == "provider-openrouter"
        assert json["model_id"] == "deepseek/deepseek-v4-flash"
        messages = json["messages"]
        assert isinstance(messages, list)
        first_message = messages[0]
        assert isinstance(first_message, dict)
        assert first_message["role"] == "system"
        assert timeout == runtime_main.settings.model_gateway_timeout_seconds
        return httpx.Response(
            200,
            json={
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "content": (
                    '{"status":"completed",'
                    '"summary":"Model gateway completed the task.",'
                    '"actions_taken":["Called model gateway"],'
                    '"sub_tasks_created":[],'
                    '"tool_calls_requested":[],'
                    '"memory_candidates":[]}'
                ),
                "usage": {
                    "provider_id": "provider-openrouter",
                    "model_id": "deepseek/deepseek-v4-flash",
                    "input_tokens": 90,
                    "output_tokens": 40,
                    "total_cost": 0.000017,
                    "currency": "USD",
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    response = TestClient(app).post(
        "/tasks/run",
        json={
            "provider_id": "provider-openrouter",
            "model_id": "deepseek/deepseek-v4-flash",
            "task": {
                "id": "task_model_gateway_demo",
                "project_id": "project_demo",
                "title": "Draft plan",
                "assigned_agent_id": "agent-dev",
                "acceptance_criteria": ["Plan has a verifiable next action."],
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
    assert payload["status"] == "completed"
    assert payload["summary"] == "Model gateway completed the task."
    assert payload["actions_taken"] == ["Called model gateway"]
    assert payload["events_emitted"][0]["payload"]["mode"] == "model-gateway"
    assert payload["model_usage"] == {
        "provider_id": "provider-openrouter",
        "model_id": "deepseek/deepseek-v4-flash",
        "input_tokens": 90,
        "output_tokens": 40,
        "total_cost": 0.000017,
        "currency": "USD",
    }
