from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings

from synarch_models import (
    ActorType,
    AgentLifecycleRequest,
    AgentResult,
    AgentTaskRequest,
    ApprovalStatus,
    EventRecord,
    EventType,
    HealthResponse,
    MemoryItem,
    ModelCompletionRequest,
    ModelCompletionResponse,
    ModelMessage,
    ModelUsage,
    TaskDraft,
    TaskStatus,
    ToolCallRequest,
)

app = FastAPI(title="Synarch Agent Runtime", version="0.1.0")


class Settings(BaseSettings):
    agent_runtime_mode: str = "stub"
    model_gateway_url: str = "http://model-gateway:8060"
    model_gateway_timeout_seconds: float = 180.0
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
    return HealthResponse(service="agent-runtime")


@app.post("/tasks/run", response_model=AgentResult)
def run_task(request: AgentTaskRequest) -> AgentResult:
    if settings.agent_runtime_mode == "model_gateway":
        return run_task_with_model_gateway(request)
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
    messages = agent_messages(request)
    body = post_openrouter_chat_completion(
        api_key=api_key,
        payload=openrouter_payload(request, model_id, messages=messages),
    )
    usage = model_usage_from_response(body, provider_id, model_id)
    content = content_from_openrouter_body(body)
    result = agent_result_from_model_content(
        request=request,
        content=content,
        usage=usage,
        mode="openrouter",
        provider_id=provider_id,
        model_id=model_id,
    )
    repair_messages = agent_result_repair_messages(request, result, messages, content)
    if repair_messages is None:
        return result

    repair_body = post_openrouter_chat_completion(
        api_key=api_key,
        payload=openrouter_payload(
            request,
            model_id,
            messages=repair_messages,
        ),
    )
    repair_usage = model_usage_from_response(repair_body, provider_id, model_id)
    repair_content = content_from_openrouter_body(repair_body)
    repaired_result = agent_result_from_model_content(
        request=request,
        content=repair_content,
        usage=combine_model_usage(usage, repair_usage),
        mode="openrouter",
        provider_id=provider_id,
        model_id=model_id,
    )
    return block_unrepaired_invalid_result(
        request,
        repaired_result,
        repair_messages,
        repair_content,
    )


def post_openrouter_chat_completion(
    *,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
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
    return body


def run_task_with_model_gateway(request: AgentTaskRequest) -> AgentResult:
    messages = agent_messages(request)
    completion = post_model_gateway_completion(request, messages)
    result = agent_result_from_model_content(
        request=request,
        content=completion.content,
        usage=completion.usage,
        mode="model-gateway",
        provider_id=completion.provider_id,
        model_id=completion.model_id,
    )
    repair_messages = agent_result_repair_messages(
        request,
        result,
        messages,
        completion.content,
    )
    if repair_messages is None:
        return result

    repair_completion = post_model_gateway_completion(
        request,
        repair_messages,
    )
    repaired_result = agent_result_from_model_content(
        request=request,
        content=repair_completion.content,
        usage=combine_model_usage(completion.usage, repair_completion.usage),
        mode="model-gateway",
        provider_id=repair_completion.provider_id,
        model_id=repair_completion.model_id,
    )
    return block_unrepaired_invalid_result(
        request,
        repaired_result,
        repair_messages,
        repair_completion.content,
    )


def post_model_gateway_completion(
    request: AgentTaskRequest,
    messages: list[ModelMessage],
) -> ModelCompletionResponse:
    completion_request = ModelCompletionRequest(
        agent_id=request.world_view.agent_id,
        purpose="agent_task",
        provider_id=request.provider_id,
        model_id=request.model_id,
        model_policy_id=model_policy_id_from_world_view(request),
        task_id=request.task.id,
        project_id=request.task.project_id,
        messages=messages,
        max_output_tokens=request.max_output_tokens,
        metadata={"runtime": "agent-runtime"},
    )
    try:
        response = httpx.post(
            f"{settings.model_gateway_url.rstrip('/')}/model-calls/complete",
            json=completion_request.model_dump(mode="json"),
            timeout=settings.model_gateway_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Model Gateway request failed") from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "provider_status": response.status_code,
                "error": response_detail(response),
            },
        )

    return ModelCompletionResponse.model_validate(response.json())


def agent_result_from_model_content(
    *,
    request: AgentTaskRequest,
    content: str,
    usage: ModelUsage,
    mode: str,
    provider_id: str,
    model_id: str,
) -> AgentResult:
    parsed = parse_agent_json(content)
    status = parsed_status(parsed.get("status"))
    event = EventRecord(
        type=EventType.agent_reported,
        source_agent_id=request.world_view.agent_id,
        target=request.task.project_id,
        payload={
            "task_id": request.task.id,
            "division": request.world_view.division,
            "mode": mode,
            "provider_id": provider_id,
            "model_id": model_id,
        },
    )
    return AgentResult(
        agent_id=request.world_view.agent_id,
        task_id=request.task.id,
        status=status,
        actions_taken=parsed_actions(parsed),
        sub_tasks_created=parsed_sub_tasks(parsed, request),
        lifecycle_requests_created=parsed_lifecycle_requests(parsed, request),
        tool_calls_requested=parsed_tool_calls(parsed, request),
        events_emitted=[event],
        memory_candidates=parsed_memory_candidates(parsed, request),
        model_usage=usage,
        summary=parsed_summary(parsed, content),
    )


def agent_messages(request: AgentTaskRequest) -> list[ModelMessage]:
    return [
        ModelMessage(
            role="system",
            content=(
                "You are a Synarch AI employee. Return raw valid JSON only, "
                "without Markdown code fences, with keys "
                "status, summary, actions_taken, sub_tasks_created, and "
                "memory_candidates, tool_calls_requested, lifecycle_requests_created. "
                "status must be one of completed, needs_review, blocked, failed. "
                "sub_tasks_created must be a list of small debuggable task objects "
                "with title, description, assigned_agent_id, depends_on, "
                "required_tools, required_tool_scopes, acceptance_criteria, and sequence. "
                "tool_calls_requested must be a list of tool call objects with "
                "tool_name, service_id, reason, and arguments. Request a tool only "
                "when it is in world_view.permissions.allowed_tools and you need "
                "external evidence before finalizing. If tool_results are present, "
                "use them before deciding. Request another allowed tool only when "
                "the previous tool result is an intermediate step required by the "
                "acceptance criteria; otherwise return a final answer with no new "
                "tool calls. If a tool_result status is failed, request a corrected "
                "allowed tool when possible, or return blocked or needs_review. "
                "lifecycle_requests_created must be empty unless an org change is "
                "required; proposed org changes stay requested and require human approval. "
                "For create_agent, include proposed_agent and, when useful, proposed_soul. "
                "For update_agent or deactivate_agent, include target_agent_id. "
                "Do not claim a lifecycle request was created in summary or actions_taken "
                "unless the lifecycle_requests_created array contains the request object. "
                "For web.fetch, arguments must include url and may include max_bytes. "
                "For connector.job.create, select the service that will run the job; "
                "arguments must include kind, purpose, run_tool_name, and may include "
                "schedule, webhook_path, run_arguments, run_reason, and metadata. "
                "connector job kind values are cron or webhook. "
                "For connector.job.list, select the service to inspect; arguments "
                "may include project_id, task_id, kind, status, and limit. "
                "For connector.job.list, omit kind when the task does not specify "
                "cron or webhook; use status for active, stopped, or paused. "
                "When a task requires stopping a connector job and connector.job.list "
                "returns the target job, request connector.job.stop with the exact "
                "job id from the tool result. "
                "For connector.job.stop, arguments must include job_id and reason. "
                "For web.extract, arguments must include url and may include provider "
                "local_fetch, local_playwright, or firecrawl plus max_bytes. Use "
                "local_fetch when no browser or external extraction API is required. "
                "Keep the answer operational and auditable."
            ),
        ),
        ModelMessage(
            role="user",
            content=json.dumps(
                {
                    "task": request.task.model_dump(mode="json"),
                    "project": request.project.model_dump(mode="json")
                    if request.project is not None
                    else None,
                    "world_view": request.world_view.model_dump(mode="json"),
                    "memory_context": request.memory_context.model_dump(mode="json")
                    if request.memory_context is not None
                    else None,
                    "tool_results": [
                        tool_result.model_dump(mode="json")
                        for tool_result in request.tool_results
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ]


def model_policy_id_from_world_view(request: AgentTaskRequest) -> str | None:
    prefix = "model_policy:"
    for policy in request.world_view.policies:
        if policy.startswith(prefix):
            return policy.removeprefix(prefix)
    return None


def openrouter_payload(
    request: AgentTaskRequest,
    model_id: str,
    *,
    messages: list[ModelMessage],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [message.model_dump(mode="json") for message in messages],
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


def content_from_openrouter_body(body: dict[str, Any]) -> str:
    raw_choices = body.get("choices")
    choices = raw_choices if isinstance(raw_choices, list) and raw_choices else [{}]
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        message = {}
    content = message.get("content") or ""
    if not isinstance(content, str):
        return ""
    return content


def lifecycle_repair_required(
    request: AgentTaskRequest,
    result: AgentResult,
) -> bool:
    if result.lifecycle_requests_created:
        return False
    return task_requests_lifecycle_change(request)


def agent_result_repair_messages(
    request: AgentTaskRequest,
    result: AgentResult,
    messages: list[ModelMessage],
    previous_content: str,
) -> list[ModelMessage] | None:
    if lifecycle_repair_required(request, result):
        return lifecycle_repair_messages(request, messages, previous_content)
    failed_tools = unresolved_failed_completed_tool_results(request, result)
    if failed_tools:
        return failed_tool_repair_messages(
            request,
            messages,
            previous_content,
            failed_tools,
        )
    missing_tools = missing_completed_required_tools(request, result)
    if missing_tools:
        return required_tool_repair_messages(
            request,
            messages,
            previous_content,
            missing_tools,
        )
    return None


def block_unrepaired_invalid_result(
    request: AgentTaskRequest,
    result: AgentResult,
    messages: list[ModelMessage],
    previous_content: str,
) -> AgentResult:
    if agent_result_repair_messages(request, result, messages, previous_content) is None:
        return result
    return result.model_copy(
        update={
            "status": TaskStatus.blocked,
            "tool_calls_requested": [],
            "summary": (
                "Model result stayed invalid after one repair attempt; blocked for review."
            ),
        }
    )


def unresolved_failed_completed_tool_results(
    request: AgentTaskRequest,
    result: AgentResult,
) -> list[str]:
    if result.status != TaskStatus.completed:
        return []

    failed_tools: list[str] = []
    for index, tool_result in enumerate(request.tool_results):
        if tool_result.status != TaskStatus.failed:
            continue
        has_later_success = any(
            later_result.tool_name == tool_result.tool_name
            and later_result.status == TaskStatus.completed
            for later_result in request.tool_results[index + 1 :]
        )
        if has_later_success:
            continue
        failed_tools.append(failed_tool_result_summary(tool_result.tool_name, tool_result.error))
    return failed_tools


def failed_tool_result_summary(tool_name: str, error: str | None) -> str:
    if not error:
        return f"{tool_name}: failed"
    return f"{tool_name}: {error}"


def missing_completed_required_tools(
    request: AgentTaskRequest,
    result: AgentResult,
) -> list[str]:
    if result.status != TaskStatus.completed:
        return []
    requested_tool_names = {tool_call.tool_name for tool_call in result.tool_calls_requested}
    completed_tool_names = {
        tool_result.tool_name
        for tool_result in request.tool_results
        if tool_result.status == TaskStatus.completed
    }
    missing_tools: list[str] = []
    for required_tool in request.task.required_tools:
        if required_tool in completed_tool_names or required_tool in requested_tool_names:
            continue
        missing_tools.append(required_tool)
    return missing_tools


def task_requests_lifecycle_change(request: AgentTaskRequest) -> bool:
    text = " ".join(
        [
            request.task.title,
            request.task.description,
            " ".join(request.task.acceptance_criteria),
        ]
    ).lower()
    if "lifecycle_requests_created" in text:
        return True
    if "lifecycle" not in text:
        return False
    return any(
        action in text
        for action in ("create_agent", "update_agent", "deactivate_agent")
    )


def lifecycle_repair_messages(
    request: AgentTaskRequest,
    messages: list[ModelMessage],
    previous_content: str,
) -> list[ModelMessage]:
    return [
        *messages,
        ModelMessage(role="assistant", content=previous_content),
        ModelMessage(
            role="user",
            content=(
                "Your previous JSON failed validation: the task requires a lifecycle "
                "proposal, but lifecycle_requests_created was empty or missing. "
                "Return corrected JSON only. Include exactly one object in "
                "lifecycle_requests_created with action, reason, proposed_agent, "
                "and proposed_soul when action is create_agent."
            ),
        ),
    ]


def failed_tool_repair_messages(
    request: AgentTaskRequest,
    messages: list[ModelMessage],
    previous_content: str,
    failed_tools: list[str],
) -> list[ModelMessage]:
    return [
        *messages,
        ModelMessage(role="assistant", content=previous_content),
        ModelMessage(
            role="user",
            content=(
                "Your previous JSON failed validation: status was completed, "
                "but these tool_results failed without a later completed result "
                f"for the same tool: {', '.join(failed_tools)}. Do not mark the "
                "task completed while tool failures are unresolved. Return "
                "corrected JSON only. Request a corrected allowed tool if possible; "
                "otherwise use status needs_review or blocked."
            ),
        ),
    ]


def required_tool_repair_messages(
    request: AgentTaskRequest,
    messages: list[ModelMessage],
    previous_content: str,
    missing_tools: list[str],
) -> list[ModelMessage]:
    completed_tools = [
        tool_result.tool_name
        for tool_result in request.tool_results
        if tool_result.status == TaskStatus.completed
    ]
    return [
        *messages,
        ModelMessage(role="assistant", content=previous_content),
        ModelMessage(
            role="user",
            content=(
                "Your previous JSON failed validation: status was completed, "
                "but these task.required_tools do not have completed tool_results: "
                f"{', '.join(missing_tools)}. Completed tool_results are: "
                f"{', '.join(completed_tools) or 'none'}. Do not claim a tool was "
                "executed unless it appears in tool_results. Return corrected JSON "
                "only. Request the next missing allowed tool if one is needed; "
                "otherwise use status needs_review or blocked."
            ),
        ),
    ]


def combine_model_usage(first: ModelUsage, second: ModelUsage) -> ModelUsage:
    return ModelUsage(
        provider_id=second.provider_id,
        model_id=second.model_id,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        total_cost=round(first.total_cost + second.total_cost, 8),
        currency=second.currency,
    )


def parse_agent_json(content: str) -> dict[str, Any]:
    for candidate in agent_json_candidates(content):
        parsed = json_dict_from_candidate(candidate)
        if parsed is not None:
            return parsed
        repaired_candidate = remove_malformed_empty_key_lines(candidate)
        if repaired_candidate != candidate:
            parsed = json_dict_from_candidate(repaired_candidate)
            if parsed is not None:
                return parsed
        closed_candidate = close_unclosed_json_containers(repaired_candidate)
        if closed_candidate != repaired_candidate:
            parsed = json_dict_from_candidate(closed_candidate)
            if parsed is not None:
                return parsed
    return {}


def agent_json_candidates(content: str) -> list[str]:
    stripped = content.strip()
    candidates = [stripped]
    candidates.extend(fenced_json_blocks(stripped))
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    return deduplicate_strings(candidates)


def fenced_json_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    chunks = content.split("```")
    for chunk in chunks:
        stripped = chunk.strip()
        if stripped.startswith("json"):
            blocks.append(stripped.removeprefix("json").strip())
    return blocks


def json_dict_from_candidate(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def remove_malformed_empty_key_lines(candidate: str) -> str:
    lines = candidate.splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith('":'))


def close_unclosed_json_containers(candidate: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in candidate:
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            stack.append("}")
            continue
        if char == "[":
            stack.append("]")
            continue
        if char in ("}", "]"):
            if not stack or stack[-1] != char:
                return candidate
            stack.pop()

    if in_string or not stack:
        return candidate
    return f"{candidate}{''.join(reversed(stack))}"


def deduplicate_strings(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


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


def parsed_sub_tasks(
    parsed: dict[str, Any],
    request: AgentTaskRequest,
) -> list[TaskDraft]:
    raw_sub_tasks = parsed.get("sub_tasks_created", [])
    if not isinstance(raw_sub_tasks, list):
        return []

    drafts: list[TaskDraft] = []
    for index, raw_sub_task in enumerate(raw_sub_tasks, start=1):
        if not isinstance(raw_sub_task, dict):
            continue
        title = raw_sub_task.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        assigned_agent_id = raw_sub_task.get("assigned_agent_id")
        if not isinstance(assigned_agent_id, str) or not assigned_agent_id.strip():
            assigned_agent_id = request.world_view.agent_id
        acceptance_criteria = string_list(raw_sub_task.get("acceptance_criteria"))
        if not acceptance_criteria:
            continue
        drafts.append(
            TaskDraft(
                title=title.strip(),
                description=string_value(raw_sub_task.get("description")),
                assigned_agent_id=assigned_agent_id,
                depends_on=string_list(raw_sub_task.get("depends_on")),
                required_tools=string_list(raw_sub_task.get("required_tools")),
                required_tool_scopes=string_list_map(
                    raw_sub_task.get("required_tool_scopes")
                ),
                acceptance_criteria=acceptance_criteria,
                sequence=integer_value(raw_sub_task.get("sequence"), index),
            )
        )
    return drafts


def parsed_tool_calls(
    parsed: dict[str, Any],
    request: AgentTaskRequest,
) -> list[ToolCallRequest]:
    raw_tool_calls = parsed.get("tool_calls_requested", [])
    if not isinstance(raw_tool_calls, list):
        return []

    tool_calls: list[ToolCallRequest] = []
    for raw_tool_call in raw_tool_calls:
        if not isinstance(raw_tool_call, dict):
            continue
        tool_name = raw_tool_call.get("tool_name")
        reason = raw_tool_call.get("reason")
        if not isinstance(tool_name, str) or not tool_name.strip():
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        arguments = raw_tool_call.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        service_id = raw_tool_call.get("service_id")
        if service_id is not None and not isinstance(service_id, str):
            service_id = None
        tool_calls.append(
            ToolCallRequest(
                agent_id=request.world_view.agent_id,
                tool_name=tool_name.strip(),
                service_id=service_id,
                project_id=request.task.project_id,
                task_id=request.task.id,
                reason=reason.strip(),
                arguments=arguments,
            )
        )
    return tool_calls


def parsed_lifecycle_requests(
    parsed: dict[str, Any],
    request: AgentTaskRequest,
) -> list[AgentLifecycleRequest]:
    raw_requests = raw_lifecycle_requests(parsed)
    if isinstance(raw_requests, dict):
        raw_requests = [raw_requests]
    if not isinstance(raw_requests, list):
        return []

    lifecycle_requests: list[AgentLifecycleRequest] = []
    for raw_request in raw_requests:
        if not isinstance(raw_request, dict):
            continue
        normalized = normalized_lifecycle_request(raw_request, request)
        try:
            lifecycle_requests.append(AgentLifecycleRequest.model_validate(normalized))
        except ValueError:
            continue
    return lifecycle_requests


def raw_lifecycle_requests(parsed: dict[str, Any]) -> Any:
    for key in (
        "lifecycle_requests_created",
        "lifecycle_request_created",
        "lifecycle_requests",
        "agent_lifecycle_requests",
        "agent_lifecycle_request",
    ):
        raw_requests = parsed.get(key)
        if raw_requests:
            return raw_requests
    return []


def normalized_lifecycle_request(
    raw_request: dict[str, Any],
    request: AgentTaskRequest,
) -> dict[str, Any]:
    normalized = dict(raw_request)
    normalized["requested_by_type"] = ActorType.agent.value
    normalized["requested_by_id"] = request.world_view.agent_id
    normalized["status"] = ApprovalStatus.requested.value
    normalized["requires_human_approval"] = True
    normalized["reason"] = string_value(normalized.get("reason")).strip()

    proposed_agent = normalized.get("proposed_agent")
    if isinstance(proposed_agent, dict):
        proposed_agent = {
            **proposed_agent,
            "created_by": proposed_agent.get("created_by") or request.world_view.agent_id,
        }
        normalized["proposed_agent"] = proposed_agent

    proposed_soul = normalized.get("proposed_soul")
    if isinstance(proposed_soul, dict):
        proposed_soul = {
            **proposed_soul,
            "created_by": proposed_soul.get("created_by") or request.world_view.agent_id,
        }
        if not proposed_soul.get("agent_id") and isinstance(proposed_agent, dict):
            proposed_soul["agent_id"] = proposed_agent.get("id")
        if not proposed_soul.get("agent_id") and isinstance(
            normalized.get("target_agent_id"), str
        ):
            proposed_soul["agent_id"] = normalized["target_agent_id"]
        normalized["proposed_soul"] = proposed_soul

    return normalized


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


def string_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def string_list_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): string_list(raw_scopes)
        for key, raw_scopes in value.items()
        if str(key).strip() and string_list(raw_scopes)
    }


def integer_value(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    return default


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
