from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings

from synarch_models import (
    HealthResponse,
    ModelCompletionRequest,
    ModelCompletionResponse,
    ModelUsage,
)

app = FastAPI(title="Synarch Model Gateway", version="0.1.0")


class Settings(BaseSettings):
    model_gateway_mode: str = "fake"
    fake_provider_id: str = "provider-model-gateway-fake"
    fake_model_id: str = "model-gateway-fake-json"
    fake_input_cost_per_million_tokens: float = 0.0
    fake_output_cost_per_million_tokens: float = 0.0
    fake_currency: str = "USD"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key_env_var: str = "OPENROUTER_API_KEY"
    openrouter_provider_id: str = "provider-openrouter"
    openrouter_model_id: str = "deepseek/deepseek-v4-flash"
    openrouter_max_output_tokens: int = 1800
    openrouter_timeout_seconds: float = 180.0
    openrouter_reasoning_enabled: bool = False
    openrouter_reasoning_effort: str = "none"
    openrouter_reasoning_exclude: bool = True
    openrouter_input_cost_per_million_tokens: float = 0.0
    openrouter_output_cost_per_million_tokens: float = 0.0
    openrouter_currency: str = "USD"


settings = Settings()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="model-gateway")


@app.post("/model-calls/complete", response_model=ModelCompletionResponse)
def complete_model_call(request: ModelCompletionRequest) -> ModelCompletionResponse:
    if settings.model_gateway_mode == "fake":
        return fake_completion(request)
    if settings.model_gateway_mode == "openrouter":
        return openrouter_completion(request)
    raise HTTPException(
        status_code=500,
        detail=f"Unsupported model gateway mode: {settings.model_gateway_mode}",
    )


def fake_completion(request: ModelCompletionRequest) -> ModelCompletionResponse:
    provider_id = request.provider_id or settings.fake_provider_id
    model_id = request.model_id or settings.fake_model_id
    content = json.dumps(
        {
            "status": "needs_review",
            "summary": "Model gateway fake provider prepared the task.",
            "actions_taken": ["Routed through model-gateway fake provider"],
            "sub_tasks_created": [],
            "tool_calls_requested": [],
            "memory_candidates": [],
        },
        separators=(",", ":"),
    )
    usage = usage_from_counts(
        provider_id=provider_id,
        model_id=model_id,
        input_tokens=estimated_tokens(*(message.content for message in request.messages)),
        output_tokens=estimated_tokens(content),
        input_cost_per_million_tokens=settings.fake_input_cost_per_million_tokens,
        output_cost_per_million_tokens=settings.fake_output_cost_per_million_tokens,
        currency=settings.fake_currency,
    )
    return ModelCompletionResponse(
        provider_id=provider_id,
        model_id=model_id,
        content=content,
        usage=usage,
        raw_response={"mode": "fake"},
    )


def openrouter_completion(request: ModelCompletionRequest) -> ModelCompletionResponse:
    api_key = os.getenv(settings.openrouter_api_key_env_var)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"{settings.openrouter_api_key_env_var} is not configured",
        )

    provider_id = request.provider_id or settings.openrouter_provider_id
    model_id = request.model_id or settings.openrouter_model_id
    payload = openrouter_payload(request, model_id)
    try:
        response = httpx.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.openrouter_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="OpenRouter request failed") from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"provider_status": response.status_code, "error": response_detail(response)},
        )

    body = response.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="OpenRouter returned an invalid response")
    return ModelCompletionResponse(
        provider_id=provider_id,
        model_id=model_id,
        content=content_from_openrouter_body(body),
        usage=usage_from_openrouter_body(body, provider_id, model_id),
        raw_response={"id": body.get("id"), "provider": body.get("provider")},
    )


def openrouter_payload(request: ModelCompletionRequest, model_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "max_tokens": request.max_output_tokens or settings.openrouter_max_output_tokens,
        "temperature": request.temperature,
    }
    reasoning: dict[str, Any] = {}
    if settings.openrouter_reasoning_enabled:
        reasoning["enabled"] = True
    elif settings.openrouter_reasoning_effort:
        reasoning["effort"] = settings.openrouter_reasoning_effort
    if settings.openrouter_reasoning_exclude:
        reasoning["exclude"] = True
    if reasoning:
        payload["reasoning"] = reasoning
    return payload


def content_from_openrouter_body(body: dict[str, Any]) -> str:
    raw_choices = body.get("choices")
    choices = raw_choices if isinstance(raw_choices, list) and raw_choices else [{}]
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def usage_from_openrouter_body(
    body: dict[str, Any],
    provider_id: str,
    model_id: str,
) -> ModelUsage:
    raw_usage = body.get("usage", {})
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_cost = usage.get("cost") or usage.get("total_cost")
    if total_cost is None:
        total_cost = (
            input_tokens * settings.openrouter_input_cost_per_million_tokens / 1_000_000
        ) + (output_tokens * settings.openrouter_output_cost_per_million_tokens / 1_000_000)
    return ModelUsage(
        provider_id=provider_id,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost=round(float(total_cost), 8),
        currency=settings.openrouter_currency,
    )


def usage_from_counts(
    *,
    provider_id: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    input_cost_per_million_tokens: float,
    output_cost_per_million_tokens: float,
    currency: str,
) -> ModelUsage:
    total_cost = (
        input_tokens * input_cost_per_million_tokens / 1_000_000
    ) + (output_tokens * output_cost_per_million_tokens / 1_000_000)
    return ModelUsage(
        provider_id=provider_id,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost=round(total_cost, 8),
        currency=currency,
    )


def estimated_tokens(*texts: str) -> int:
    return max(1, (sum(len(text) for text in texts) + 3) // 4)


def response_detail(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict):
        return body.get("error", body)
    return body
