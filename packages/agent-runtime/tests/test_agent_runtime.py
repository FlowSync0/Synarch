import httpx
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from synarch_agent_runtime import main as runtime_main
from synarch_agent_runtime.main import app
from synarch_models import AgentResult, AgentTaskRequest, TaskStatus


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


def test_parse_agent_json_closes_truncated_container_response() -> None:
    parsed = runtime_main.parse_agent_json(
        """{
  "status": "needs_review",
  "summary": "Requested connector.job.list on connector-supplier-web.",
  "actions_taken": [
    "Requested connector.job.list on service connector-supplier-web with status active."
  ],
  "sub_tasks_created": [],
  "memory_candidates": [],
  "tool_calls_requested": [
    {
      "tool_name": "connector.job.list",
      "service_id": "connector-supplier-web",
      "reason": "Discover the active owned connector job before stopping it.",
      "arguments": {
        "status": "active"
      }
    }
  """
    )

    assert parsed["status"] == "needs_review"
    assert parsed["tool_calls_requested"][0]["tool_name"] == "connector.job.list"
    assert parsed["tool_calls_requested"][0]["arguments"] == {"status": "active"}


def test_agent_messages_describe_connector_job_list_filter_values() -> None:
    request = AgentTaskRequest.model_validate(
        {
            "task": {
                "id": "task_connector_contract",
                "project_id": "project_demo",
                "title": "Stop connector job",
                "assigned_agent_id": "agent-ops-sourcing",
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
        }
    )

    system_content = runtime_main.agent_messages(request)[0].content

    assert "connector job kind values are cron or webhook" in system_content
    assert "omit kind when the task does not specify cron or webhook" in system_content
    assert "use status for active, stopped, or paused" in system_content


def test_runtime_parses_structured_memory_candidate_content() -> None:
    request = AgentTaskRequest.model_validate(
        {
            "task": {
                "id": "task_memory_candidate",
                "project_id": "project_demo",
                "title": "Record blocker",
                "assigned_agent_id": "agent-ops-sourcing",
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
        }
    )

    candidates = runtime_main.parsed_memory_candidates(
        {
            "memory_candidates": [
                {
                    "scope": "global",
                    "content": "Blocked web extraction requires human review.",
                    "metadata": {"blocked_reason": "http_access_denied"},
                }
            ]
        },
        request,
    )

    assert len(candidates) == 1
    assert candidates[0].scope == "project:project_demo"
    assert candidates[0].agent_id == "agent-ops-sourcing"
    assert candidates[0].project_id == "project_demo"
    assert candidates[0].content == "Blocked web extraction requires human review."
    assert candidates[0].metadata == {"blocked_reason": "http_access_denied"}


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


def test_runtime_repairs_completed_result_missing_required_tool(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "model_gateway")
    monkeypatch.setattr(runtime_main.settings, "model_gateway_url", "http://model-gateway:8060")
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(json)
        if len(calls) == 1:
            content = (
                '{"status":"completed",'
                '"summary":"Listed and stopped the connector job.",'
                '"actions_taken":["Claimed stop without tool result"],'
                '"sub_tasks_created":[],'
                '"tool_calls_requested":[],'
                '"memory_candidates":[]}'
            )
            usage = {
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "input_tokens": 50,
                "output_tokens": 10,
                "total_cost": 0.000006,
                "currency": "USD",
            }
        else:
            messages = json["messages"]
            assert isinstance(messages, list)
            assert "connector.job.stop" in str(messages[-1]["content"])
            content = (
                '{"status":"needs_review",'
                '"summary":"Need to stop the listed connector job.",'
                '"actions_taken":["Requested missing stop tool"],'
                '"sub_tasks_created":[],'
                '"tool_calls_requested":[{'
                '"tool_name":"connector.job.stop",'
                '"service_id":"connector-supplier-web",'
                '"reason":"Stop the listed active job.",'
                '"arguments":{"job_id":"connector-job-owned","reason":"Supplier replied."}'
                '}],'
                '"memory_candidates":[]}'
            )
            usage = {
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "input_tokens": 60,
                "output_tokens": 15,
                "total_cost": 0.000009,
                "currency": "USD",
            }
        return httpx.Response(
            200,
            json={
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "content": content,
                "usage": usage,
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
                "id": "task_required_tool_repair",
                "project_id": "project_demo",
                "title": "Stop listed connector job",
                "assigned_agent_id": "agent-ops-sourcing",
                "required_tools": ["connector.job.list", "connector.job.stop"],
                "acceptance_criteria": ["The stop tool result exists."],
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
            "tool_results": [
                {
                    "tool_name": "connector.job.list",
                    "status": "completed",
                    "output": {
                        "connector_jobs": [
                            {
                                "id": "connector-job-owned",
                                "status": "active",
                            }
                        ]
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 2
    assert payload["status"] == "needs_review"
    assert payload["tool_calls_requested"][0]["tool_name"] == "connector.job.stop"
    assert payload["tool_calls_requested"][0]["arguments"]["job_id"] == "connector-job-owned"
    assert payload["model_usage"]["input_tokens"] == 110
    assert payload["model_usage"]["output_tokens"] == 25


def test_runtime_repairs_completed_result_with_unresolved_failed_tool(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "model_gateway")
    monkeypatch.setattr(runtime_main.settings, "model_gateway_url", "http://model-gateway:8060")
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(json)
        if len(calls) == 1:
            content = (
                '{"status":"completed",'
                '"summary":"Stopped the connector job.",'
                '"actions_taken":["Claimed stop despite failed tool"],'
                '"sub_tasks_created":[],'
                '"tool_calls_requested":[],'
                '"memory_candidates":[]}'
            )
            usage = {
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "input_tokens": 40,
                "output_tokens": 10,
                "total_cost": 0.000005,
                "currency": "USD",
            }
        else:
            messages = json["messages"]
            assert isinstance(messages, list)
            repair_content = str(messages[-1]["content"])
            assert "connector.job.stop: Unknown connector job: bad-job" in repair_content
            assert "failed without a later completed result" in repair_content
            content = (
                '{"status":"blocked",'
                '"summary":"The connector job stop failed because the job id was unknown.",'
                '"actions_taken":["Reported unresolved tool failure"],'
                '"sub_tasks_created":[],'
                '"tool_calls_requested":[],'
                '"memory_candidates":[]}'
            )
            usage = {
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "input_tokens": 55,
                "output_tokens": 12,
                "total_cost": 0.000007,
                "currency": "USD",
            }
        return httpx.Response(
            200,
            json={
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "content": content,
                "usage": usage,
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
                "id": "task_failed_tool_repair",
                "project_id": "project_demo",
                "title": "Stop connector job",
                "assigned_agent_id": "agent-ops-sourcing",
                "acceptance_criteria": ["The connector job is stopped or a blocker is reported."],
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
            "tool_results": [
                {
                    "tool_name": "connector.job.stop",
                    "status": "failed",
                    "error": "Unknown connector job: bad-job",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 2
    assert payload["status"] == "blocked"
    assert payload["summary"] == "The connector job stop failed because the job id was unknown."
    assert payload["tool_calls_requested"] == []
    assert payload["model_usage"]["input_tokens"] == 95
    assert payload["model_usage"]["output_tokens"] == 22


def test_runtime_repairs_completed_result_with_unresolved_blocked_tool(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "model_gateway")
    monkeypatch.setattr(runtime_main.settings, "model_gateway_url", "http://model-gateway:8060")
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(json)
        if len(calls) == 1:
            content = (
                '{"status":"completed",'
                '"summary":"Fetched the protected source.",'
                '"actions_taken":["Claimed source despite blocked tool"],'
                '"sub_tasks_created":[],'
                '"tool_calls_requested":[],'
                '"memory_candidates":[]}'
            )
            usage = {
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "input_tokens": 42,
                "output_tokens": 10,
                "total_cost": 0.000005,
                "currency": "USD",
            }
        else:
            messages = json["messages"]
            assert isinstance(messages, list)
            repair_content = str(messages[-1]["content"])
            assert "web.fetch: http_access_denied" in repair_content
            assert "blocked without a later completed result" in repair_content
            content = (
                '{"status":"blocked",'
                '"summary":"The protected source fetch is blocked for human review.",'
                '"actions_taken":["Reported unresolved tool block"],'
                '"sub_tasks_created":[],'
                '"tool_calls_requested":[],'
                '"memory_candidates":[]}'
            )
            usage = {
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "input_tokens": 58,
                "output_tokens": 12,
                "total_cost": 0.000007,
                "currency": "USD",
            }
        return httpx.Response(
            200,
            json={
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "content": content,
                "usage": usage,
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
                "id": "task_blocked_tool_repair",
                "project_id": "project_demo",
                "title": "Fetch protected supplier source",
                "assigned_agent_id": "agent-ops-sourcing",
                "acceptance_criteria": ["The source is fetched or a blocker is reported."],
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
            "tool_results": [
                {
                    "tool_name": "web.fetch",
                    "status": "blocked",
                    "error": "http_access_denied",
                    "output": {"blocked_reason": "http_access_denied"},
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 2
    assert payload["status"] == "blocked"
    assert payload["summary"] == "The protected source fetch is blocked for human review."
    assert payload["tool_calls_requested"] == []
    assert payload["model_usage"]["input_tokens"] == 100
    assert payload["model_usage"]["output_tokens"] == 22


def test_runtime_allows_completed_result_when_failed_tool_was_retried_successfully(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_main.settings, "agent_runtime_mode", "model_gateway")
    monkeypatch.setattr(runtime_main.settings, "model_gateway_url", "http://model-gateway:8060")
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(json)
        return httpx.Response(
            200,
            json={
                "provider_id": "provider-openrouter",
                "model_id": "deepseek/deepseek-v4-flash",
                "content": (
                    '{"status":"completed",'
                    '"summary":"Retried and stopped the connector job.",'
                    '"actions_taken":["Used successful retry result"],'
                    '"sub_tasks_created":[],'
                    '"tool_calls_requested":[],'
                    '"memory_candidates":[]}'
                ),
                "usage": {
                    "provider_id": "provider-openrouter",
                    "model_id": "deepseek/deepseek-v4-flash",
                    "input_tokens": 40,
                    "output_tokens": 10,
                    "total_cost": 0.000005,
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
                "id": "task_failed_tool_retried",
                "project_id": "project_demo",
                "title": "Stop connector job",
                "assigned_agent_id": "agent-ops-sourcing",
                "acceptance_criteria": ["The connector job is stopped."],
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
            "tool_results": [
                {
                    "tool_name": "connector.job.stop",
                    "status": "failed",
                    "error": "Unknown connector job: bad-job",
                },
                {
                    "tool_name": "connector.job.stop",
                    "status": "completed",
                    "output": {"connector_job_id": "good-job", "status": "stopped"},
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 1
    assert payload["status"] == "completed"
    assert payload["summary"] == "Retried and stopped the connector job."


def test_runtime_blocks_when_repair_result_is_still_invalid() -> None:
    request = AgentTaskRequest.model_validate(
        {
            "task": {
                "id": "task_unrepaired_invalid",
                "project_id": "project_demo",
                "title": "Stop connector job",
                "assigned_agent_id": "agent-ops-sourcing",
            },
            "world_view": {
                "agent_id": "agent-ops-sourcing",
                "role": "Ops sourcing manager",
                "division": "ops",
            },
            "tool_results": [
                {
                    "tool_name": "connector.job.stop",
                    "status": "failed",
                    "error": "Unknown connector job: bad-job",
                }
            ],
        }
    )
    unsafe_result = AgentResult(
        agent_id="agent-ops-sourcing",
        task_id="task_unrepaired_invalid",
        status=TaskStatus.completed,
        summary="Stopped the connector job.",
    )

    blocked = runtime_main.block_unrepaired_invalid_result(
        request,
        unsafe_result,
        [],
        "{}",
    )

    assert blocked.status == TaskStatus.blocked
    assert blocked.tool_calls_requested == []
    assert (
        blocked.summary
        == "Model result stayed invalid after one repair attempt; blocked for review."
    )
