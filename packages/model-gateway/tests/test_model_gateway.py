import json

import httpx
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from synarch_model_gateway import main as model_gateway_main
from synarch_model_gateway.main import app


def test_model_gateway_health() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json()["service"] == "model-gateway"


def test_fake_completion_returns_deterministic_usage(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(model_gateway_main.settings, "model_gateway_mode", "fake")
    monkeypatch.setattr(model_gateway_main.settings, "fake_input_cost_per_million_tokens", 0.10)
    monkeypatch.setattr(model_gateway_main.settings, "fake_output_cost_per_million_tokens", 0.20)

    response = TestClient(app).post(
        "/model-calls/complete",
        json={
            "agent_id": "agent-dev",
            "purpose": "agent_task",
            "provider_id": "provider-test",
            "model_id": "model-test",
            "messages": [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "Plan this task."},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    content = json.loads(payload["content"])
    assert payload["provider_id"] == "provider-test"
    assert payload["model_id"] == "model-test"
    assert content["status"] == "needs_review"
    assert content["actions_taken"] == ["Routed through model-gateway fake provider"]
    assert payload["usage"]["input_tokens"] > 0
    assert payload["usage"]["output_tokens"] > 0
    assert payload["usage"]["total_cost"] > 0


def test_fake_completion_resolves_state_model_policy(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(model_gateway_main.settings, "model_gateway_mode", "fake")
    monkeypatch.setattr(model_gateway_main.settings, "state_service_url", "http://state-service:8020")

    def fake_get(url: str, *, timeout: float) -> httpx.Response:
        assert timeout == model_gateway_main.settings.state_service_timeout_seconds
        if url.endswith("/model-policies/policy-openrouter"):
            return httpx.Response(
                200,
                json={
                    "id": "policy-openrouter",
                    "name": "OpenRouter default",
                    "default_model_id": "deepseek/deepseek-v4-flash",
                    "allowed_model_ids": ["deepseek/deepseek-v4-flash"],
                },
                request=httpx.Request("GET", url),
            )
        if url.endswith("/model-definitions/deepseek/deepseek-v4-flash"):
            return httpx.Response(
                200,
                json={
                    "id": "deepseek/deepseek-v4-flash",
                    "provider_id": "provider-openrouter",
                    "display_name": "DeepSeek V4 Flash",
                    "input_cost_per_million_tokens": 0.10,
                    "output_cost_per_million_tokens": 0.20,
                },
                request=httpx.Request("GET", url),
            )
        if url.endswith("/model-providers/provider-openrouter"):
            return httpx.Response(
                200,
                json={
                    "id": "provider-openrouter",
                    "name": "OpenRouter",
                    "provider_type": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key_env_var": "OPENROUTER_API_KEY",
                },
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"Unexpected state URL: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)

    response = TestClient(app).post(
        "/model-calls/complete",
        json={
            "agent_id": "agent-dev",
            "purpose": "agent_task",
            "model_policy_id": "policy-openrouter",
            "messages": [{"role": "user", "content": "Plan this task."}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "provider-openrouter"
    assert payload["model_id"] == "deepseek/deepseek-v4-flash"
    assert payload["raw_response"]["model_policy_id"] == "policy-openrouter"
    assert payload["usage"]["total_cost"] > 0


def test_model_policy_rejects_disallowed_model(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(model_gateway_main.settings, "model_gateway_mode", "fake")
    monkeypatch.setattr(model_gateway_main.settings, "state_service_url", "http://state-service:8020")

    def fake_get(url: str, *, timeout: float) -> httpx.Response:
        assert timeout == model_gateway_main.settings.state_service_timeout_seconds
        return httpx.Response(
            200,
            json={
                "id": "policy-openrouter",
                "name": "OpenRouter default",
                "default_model_id": "deepseek/deepseek-v4-flash",
                "allowed_model_ids": ["deepseek/deepseek-v4-flash"],
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    response = TestClient(app).post(
        "/model-calls/complete",
        json={
            "agent_id": "agent-dev",
            "purpose": "agent_task",
            "model_policy_id": "policy-openrouter",
            "model_id": "other/model",
            "messages": [{"role": "user", "content": "Plan this task."}],
        },
    )

    assert response.status_code == 403
    assert "not allowed by policy" in response.json()["detail"]


def test_openrouter_completion_normalizes_provider_response(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_gateway_main.settings, "model_gateway_mode", "openrouter")
    monkeypatch.setattr(
        model_gateway_main.settings,
        "openrouter_input_cost_per_million_tokens",
        0.10,
    )
    monkeypatch.setattr(
        model_gateway_main.settings,
        "openrouter_output_cost_per_million_tokens",
        0.20,
    )
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
        assert timeout == model_gateway_main.settings.openrouter_timeout_seconds
        return httpx.Response(
            200,
            json={
                "id": "completion-test",
                "choices": [{"message": {"content": '{"status":"completed"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    response = TestClient(app).post(
        "/model-calls/complete",
        json={
            "agent_id": "agent-dev",
            "purpose": "agent_task",
            "model_id": "deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": "Return JSON."}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "provider-openrouter"
    assert payload["model_id"] == "deepseek/deepseek-v4-flash"
    assert payload["content"] == '{"status":"completed"}'
    assert payload["usage"] == {
        "provider_id": "provider-openrouter",
        "model_id": "deepseek/deepseek-v4-flash",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_cost": 0.00002,
        "currency": "USD",
    }


def test_openrouter_completion_retries_transient_provider_error(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_gateway_main.settings, "model_gateway_mode", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    calls: list[str] = []

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(url)
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "deepseek/deepseek-v4-flash"
        assert timeout == model_gateway_main.settings.openrouter_timeout_seconds
        if len(calls) == 1:
            return httpx.Response(
                502,
                json={"error": "provider gateway timeout"},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={
                "id": "completion-retry-test",
                "choices": [{"message": {"content": '{"status":"completed"}'}}],
                "usage": {"prompt_tokens": 25, "completion_tokens": 10},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    response = TestClient(app).post(
        "/model-calls/complete",
        json={
            "agent_id": "agent-dev",
            "purpose": "agent_task",
            "model_id": "deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": "Return JSON."}],
        },
    )

    assert response.status_code == 200
    assert len(calls) == 2
    assert response.json()["content"] == '{"status":"completed"}'


def test_openrouter_completion_does_not_retry_client_provider_error(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_gateway_main.settings, "model_gateway_mode", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    calls: list[str] = []

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        calls.append(url)
        return httpx.Response(
            400,
            json={"error": "invalid request"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    response = TestClient(app).post(
        "/model-calls/complete",
        json={
            "agent_id": "agent-dev",
            "purpose": "agent_task",
            "model_id": "deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": "Return JSON."}],
        },
    )

    assert response.status_code == 502
    assert len(calls) == 1
    assert response.json()["detail"] == {
        "provider_status": 400,
        "error": "invalid request",
    }
