from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings

from synarch_models import (
    AgentResult,
    AgentTaskRequest,
    EventRecord,
    EventType,
    HealthResponse,
    MemoryItem,
    ModelUsage,
    TaskStatus,
)

app = FastAPI(title="Synarch Agent Runtime", version="0.1.0")


class Settings(BaseSettings):
    agent_runtime_mode: str = "stub"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key_env_var: str = "OPENROUTER_API_KEY"
    openrouter_provider_id: str = "provider-openrouter"
    openrouter_model_id: str = "deepseek/deepseek-v4-flash"
    openrouter_max_output_tokens: int = 700
    openrouter_timeout_seconds: float = 45.0
    openrouter_reasoning_enabled: bool = False
    openrouter_reasoning_effort: str = "none"
    openrouter_reasoning_exclude: bool = True
    openrouter_input_cost_per_million_tokens: float = 0.0
    openrouter_output_cost_per_million_tokens: float = 0.0
    openrouter_currency: str = "USD"


settings = Settings()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="agent-runtime")


@app.post("/tasks/run", response_model=AgentResult)
def run_task(request: AgentTaskRequest) -> AgentResult:
    if settings.agent_runtime_mode == "openrouter":
        return run_task_with_openrouter(request)
    if settings.agent_runtime_mode != "stub":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported agent runtime mode: {settings.agent_runtime_mode}",
        )

    status = task_status_for_stub(request)
    event = EventRecord(
        type=EventType.agent_reported,
        source_agent_id=request.world_view.agent_id,
        target=request.task.project_id,
        payload={
            "task_id": request.task.id,
            "division": request.world_view.division,
            "mode": "stub-runtime",
        },
    )
    return AgentResult(
        agent_id=request.world_view.agent_id,
        task_id=request.task.id,
        status=status,
        actions_taken=["Loaded LocalWorldView", "Prepared execution plan"],
        events_emitted=[event],
        summary=summary_for_status(status),
    )


def run_task_with_openrouter(request: AgentTaskRequest) -> AgentResult:
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
    raw_choices = body.get("choices")
    choices = raw_choices if isinstance(raw_choices, list) and raw_choices else [{}]
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        message = {}
    content = message.get("content") or ""
    parsed = parse_agent_json(content)
    status = parsed_status(parsed.get("status"))
    usage = model_usage_from_response(body, provider_id, model_id)
    event = EventRecord(
        type=EventType.agent_reported,
        source_agent_id=request.world_view.agent_id,
        target=request.task.project_id,
        payload={
            "task_id": request.task.id,
            "division": request.world_view.division,
            "mode": "openrouter",
            "model_id": model_id,
        },
    )
    return AgentResult(
        agent_id=request.world_view.agent_id,
        task_id=request.task.id,
        status=status,
        actions_taken=parsed_actions(parsed),
        events_emitted=[event],
        memory_candidates=parsed_memory_candidates(parsed, request),
        model_usage=usage,
        summary=parsed_summary(parsed, content),
    )


def openrouter_payload(request: AgentTaskRequest, model_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Synarch AI employee. Return only valid JSON with keys "
                    "status, summary, actions_taken, and memory_candidates. "
                    "status must be one of completed, needs_review, blocked, failed. "
                    "Keep the answer operational and auditable."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": request.task.model_dump(mode="json"),
                        "project": request.project.model_dump(mode="json")
                        if request.project is not None
                        else None,
                        "world_view": request.world_view.model_dump(mode="json"),
                        "memory_context": request.memory_context.model_dump(mode="json")
                        if request.memory_context is not None
                        else None,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "max_tokens": request.max_output_tokens or settings.openrouter_max_output_tokens,
        "temperature": 0.2,
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


def parse_agent_json(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def parsed_status(value: Any) -> TaskStatus:
    try:
        return TaskStatus(value)
    except (TypeError, ValueError):
        return TaskStatus.needs_review


def parsed_actions(parsed: dict[str, Any]) -> list[str]:
    actions = parsed.get("actions_taken", [])
    if not isinstance(actions, list):
        return []
    return [str(action) for action in actions]


def parsed_memory_candidates(
    parsed: dict[str, Any],
    request: AgentTaskRequest,
) -> list[MemoryItem]:
    candidates = parsed.get("memory_candidates", [])
    if not isinstance(candidates, list):
        return []
    return [
        MemoryItem(
            scope=f"project:{request.task.project_id}",
            agent_id=request.world_view.agent_id,
            project_id=request.task.project_id,
            content=str(candidate),
        )
        for candidate in candidates
        if str(candidate).strip()
    ]


def parsed_summary(parsed: dict[str, Any], content: str) -> str:
    summary = parsed.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    if content.strip():
        return content.strip()[:1200]
    return "OpenRouter returned an empty response."


def model_usage_from_response(
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


def response_detail(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict):
        return body.get("error", body)
    return body


def task_status_for_stub(request: AgentTaskRequest) -> TaskStatus:
    if (
        request.world_view.agent_id == "agent-direction"
        and request.task.title == "Clarify success criteria"
    ):
        return TaskStatus.completed
    return TaskStatus.needs_review


def summary_for_status(status: TaskStatus) -> str:
    if status == TaskStatus.completed:
        return "Runtime stub completed the deterministic preparation step."
    return "Runtime stub prepared the task for a real agent executor."
