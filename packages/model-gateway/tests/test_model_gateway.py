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
