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
                                '"lifecycle_request_created":{'
                                '"action":"create_agent",'
                                '"requested_by_type":"user",'
                                '"requested_by_id":"wrong-actor",'
                                '"reason":"Need a bounded sourcing researcher.",'
                                '"requires_human_approval":false,'
                                '"proposed_agent":{'
                                '"id":"agent-sourcing-researcher",'
                                '"name":"IA Sourcing Researcher",'
                                '"role":"Supplier research specialist",'
                                '"division":"ops",'
                                '"manager_id":"agent-dev"},'
                                '"proposed_soul":{'
                                '"identity":"Sourcing researcher",'
                                '"mission":"Find suppliers with source evidence."}},'
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
    assert payload["lifecycle_requests_created"][0]["requested_by_type"] == "agent"
    assert payload["lifecycle_requests_created"][0]["requested_by_id"] == "agent-dev"
    assert payload["lifecycle_requests_created"][0]["requires_human_approval"] is True
    assert (
        payload["lifecycle_requests_created"][0]["proposed_agent"]["created_by"]
        == "agent-dev"
    )
    assert (
        payload["lifecycle_requests_created"][0]["proposed_soul"]["agent_id"]
        == "agent-sourcing-researcher"
    )
    assert (
        payload["lifecycle_requests_created"][0]["proposed_soul"]["created_by"]
        == "agent-dev"
    )
    assert payload["memory_candidates"][0]["content"] == "Remember supplier MOQ constraint."
    assert payload["model_usage"] == {
        "provider_id": "provider-openrouter",
        "model_id": "deepseek/deepseek-v4-flash",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_cost": 0.00002,
        "currency": "USD",
    }


def test_parse_agent_json_recovers_fenced_json_with_malformed_empty_key_line() -> None:
    parsed = runtime_main.parse_agent_json(
        """```json
{
  "status": "needs_review",
  "summary": "Need to stop the connector job.",
  "actions_taken": [],
  ": [],
  "sub_tasks_created": [],
  "memory_candidates": [],
  "tool_calls_requested": [
    {
      "tool_name": "connector.job.stop",
      "service_id": "connector-supplier-web",
      "reason": "Stop the completed connector job.",
      "arguments": {
        "job_id": "connector-job-live-stop",
        "reason": "Supplier replied, follow-up complete."
      }
    }
  ],
  "lifecycle_requests_created": []
}
```"""
    )

    assert parsed["status"] == "needs_review"
    assert parsed["tool_calls_requested"][0]["tool_name"] == "connector.job.stop"
    assert (
        parsed["tool_calls_requested"][0]["arguments"]["job_id"]
        == "connector-job-live-stop"
    )


def test_runtime_repairs_missing_lifecycle_request_from_openrouter(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(json)
        messages = json["messages"]
        assert isinstance(messages, list)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"status":"completed",'
                                    '"summary":"Lifecycle request created.",'
                                    '"actions_taken":["Mentioned lifecycle request"],'
                                    '"sub_tasks_created":[],'
                                    '"tool_calls_requested":[],'
                                    '"memory_candidates":[]}'
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 80, "completion_tokens": 20},
                },
                request=httpx.Request("POST", url),
            )
        assert len(messages) == 4
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"status":"completed",'
                                '"summary":"Corrected lifecycle request.",'
                                '"actions_taken":["Returned typed lifecycle request"],'
                                '"sub_tasks_created":[],'
                                '"tool_calls_requested":[],'
                                '"lifecycle_requests_created":[{'
                                '"action":"create_agent",'
                                '"requested_by_type":"user",'
                                '"requested_by_id":"wrong-actor",'
                                '"reason":"Need a sourcing researcher.",'
                                '"proposed_agent":{'
                                '"id":"agent-sourcing-researcher",'
                                '"name":"IA Sourcing Researcher",'
                                '"role":"Supplier research specialist",'
                                '"division":"ops",'
                                '"manager_id":"agent-ops-sourcing"},'
                                '"proposed_soul":{'
                                '"identity":"Sourcing researcher",'
                                '"mission":"Find suppliers with source evidence."}}],'
                                '"memory_candidates":[]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 90, "completion_tokens": 40},
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
                "id": "task_lifecycle_repair",
                "project_id": "project_demo",
                "title": "Propose lifecycle worker",
                "description": "Use lifecycle_requests_created to create_agent.",
                "assigned_agent_id": "agent-ops-sourcing",
                "acceptance_criteria": ["A lifecycle request is returned as typed JSON."],
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 2
    assert payload["summary"] == "Corrected lifecycle request."
    assert payload["lifecycle_requests_created"][0]["requested_by_type"] == "agent"
    assert payload["lifecycle_requests_created"][0]["requested_by_id"] == "agent-ops-sourcing"
    assert payload["model_usage"]["input_tokens"] == 170
    assert payload["model_usage"]["output_tokens"] == 60


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
        assert json["model_policy_id"] == "policy-openrouter-deepseek-v4-flash"
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
                "policies": ["model_policy:policy-openrouter-deepseek-v4-flash"],
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
