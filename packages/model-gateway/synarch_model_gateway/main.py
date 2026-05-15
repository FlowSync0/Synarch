from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings

from synarch_models import (
    AiProviderType,
    HealthResponse,
    ModelCompletionRequest,
    ModelCompletionResponse,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ModelUsage,
)

app = FastAPI(title="Synarch Model Gateway", version="0.1.0")

OPENROUTER_MAX_ATTEMPTS = 2
OPENROUTER_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class Settings(BaseSettings):
    model_gateway_mode: str = "fake"
    state_service_url: str | None = None
    state_service_timeout_seconds: float = 5.0
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


@dataclass(frozen=True)
class ModelRoute:
    provider_id: str
    model_id: str
    provider_type: AiProviderType | str
    base_url: str | None = None
    api_key_env_var: str | None = None
    input_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float = 0.0
    currency: str = "USD"
    model_policy_id: str | None = None


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
    route = fake_model_route(request)
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
        provider_id=route.provider_id,
        model_id=route.model_id,
        input_tokens=estimated_tokens(*(message.content for message in request.messages)),
        output_tokens=estimated_tokens(content),
        input_cost_per_million_tokens=route.input_cost_per_million_tokens,
        output_cost_per_million_tokens=route.output_cost_per_million_tokens,
        currency=route.currency,
    )
    return ModelCompletionResponse(
        provider_id=route.provider_id,
        model_id=route.model_id,
        content=content,
        usage=usage,
        raw_response={"mode": "fake", "model_policy_id": route.model_policy_id},
    )


def openrouter_completion(request: ModelCompletionRequest) -> ModelCompletionResponse:
    route = openrouter_model_route(request)
    api_key_env_var = route.api_key_env_var or settings.openrouter_api_key_env_var
    api_key = os.getenv(api_key_env_var)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"{api_key_env_var} is not configured",
        )

    payload = openrouter_payload(request, route.model_id)
    response: httpx.Response | None = None
    endpoint = f"{(route.base_url or settings.openrouter_base_url).rstrip('/')}/chat/completions"
    for attempt in range(OPENROUTER_MAX_ATTEMPTS):
        try:
            response = httpx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=settings.openrouter_timeout_seconds,
            )
        except httpx.HTTPError as error:
            if attempt < OPENROUTER_MAX_ATTEMPTS - 1:
                continue
            raise HTTPException(status_code=502, detail="OpenRouter request failed") from error

        if (
            response.status_code in OPENROUTER_RETRYABLE_STATUS_CODES
            and attempt < OPENROUTER_MAX_ATTEMPTS - 1
        ):
            continue
        break

    if response is None:
        raise HTTPException(status_code=502, detail="OpenRouter request failed")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"provider_status": response.status_code, "error": response_detail(response)},
        )

    body = response.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="OpenRouter returned an invalid response")
    return ModelCompletionResponse(
        provider_id=route.provider_id,
        model_id=route.model_id,
        content=content_from_openrouter_body(body),
        usage=usage_from_openrouter_body(body, route),
        raw_response={
            "id": body.get("id"),
            "provider": body.get("provider"),
            "model_policy_id": route.model_policy_id,
        },
    )


def fake_model_route(request: ModelCompletionRequest) -> ModelRoute:
    state_route = state_model_route(request)
    if state_route is not None:
        return state_route
    return ModelRoute(
        provider_id=request.provider_id or settings.fake_provider_id,
        model_id=request.model_id or settings.fake_model_id,
        provider_type=AiProviderType.local,
        input_cost_per_million_tokens=settings.fake_input_cost_per_million_tokens,
        output_cost_per_million_tokens=settings.fake_output_cost_per_million_tokens,
        currency=settings.fake_currency,
        model_policy_id=request.model_policy_id,
    )


def openrouter_model_route(request: ModelCompletionRequest) -> ModelRoute:
    state_route = state_model_route(request)
    if state_route is not None:
        if state_route.provider_type != AiProviderType.openrouter:
            raise HTTPException(
                status_code=400,
                detail=f"Model policy resolved non-OpenRouter provider: {state_route.provider_id}",
            )
        return state_route
    return ModelRoute(
        provider_id=request.provider_id or settings.openrouter_provider_id,
        model_id=request.model_id or settings.openrouter_model_id,
        provider_type=AiProviderType.openrouter,
        base_url=settings.openrouter_base_url,
        api_key_env_var=settings.openrouter_api_key_env_var,
        input_cost_per_million_tokens=settings.openrouter_input_cost_per_million_tokens,
        output_cost_per_million_tokens=settings.openrouter_output_cost_per_million_tokens,
        currency=settings.openrouter_currency,
        model_policy_id=request.model_policy_id,
    )


def state_model_route(request: ModelCompletionRequest) -> ModelRoute | None:
    if not settings.state_service_url or not request.model_policy_id:
        return None

    policy = get_state_model_policy(request.model_policy_id)
    selected_model_id = request.model_id or policy.default_model_id
    allowed_model_ids = {policy.default_model_id, *policy.allowed_model_ids}
    if selected_model_id not in allowed_model_ids:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Model {selected_model_id} is not allowed by policy "
                f"{request.model_policy_id}"
            ),
        )

    model = get_state_model_definition(selected_model_id)
    if not model.enabled:
        raise HTTPException(status_code=403, detail=f"Model is disabled: {selected_model_id}")
    provider = get_state_model_provider(model.provider_id)
    if not provider.enabled:
        raise HTTPException(status_code=403, detail=f"Model provider is disabled: {provider.id}")
    return ModelRoute(
        provider_id=provider.id,
        model_id=model.id,
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        api_key_env_var=provider.api_key_env_var,
        input_cost_per_million_tokens=model.input_cost_per_million_tokens,
        output_cost_per_million_tokens=model.output_cost_per_million_tokens,
        currency=model.currency,
        model_policy_id=policy.id,
    )


def get_state_model_policy(policy_id: str) -> ModelPolicy:
    body = state_get(f"/model-policies/{policy_id}")
    return ModelPolicy.model_validate(body)


def get_state_model_definition(model_id: str) -> ModelDefinition:
    body = state_get(f"/model-definitions/{model_id}")
    return ModelDefinition.model_validate(body)


def get_state_model_provider(provider_id: str) -> ModelProviderConfig:
    body = state_get(f"/model-providers/{provider_id}")
    return ModelProviderConfig.model_validate(body)


def state_get(path: str) -> Any:
    if not settings.state_service_url:
        raise HTTPException(status_code=500, detail="STATE_SERVICE_URL is not configured")
    try:
        response = httpx.get(
            f"{settings.state_service_url.rstrip('/')}{path}",
            timeout=settings.state_service_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="State service request failed") from error
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"state_status": response.status_code, "error": response_detail(response)},
        )
    return response.json()


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


def usage_from_openrouter_body(body: dict[str, Any], route: ModelRoute) -> ModelUsage:
    raw_usage = body.get("usage", {})
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_cost = usage.get("cost") or usage.get("total_cost")
    if total_cost is None:
        total_cost = (
            input_tokens * route.input_cost_per_million_tokens / 1_000_000
        ) + (output_tokens * route.output_cost_per_million_tokens / 1_000_000)
    return ModelUsage(
        provider_id=route.provider_id,
        model_id=route.model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost=round(float(total_cost), 8),
        currency=route.currency,
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
