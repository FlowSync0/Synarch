from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from synarch_models import (
    AgentResult,
    AgentTaskRequest,
    CostRecord,
    EventRecord,
    EventType,
    LocalWorldView,
    MemoryContext,
    TaskRecord,
    TaskRunResult,
    TaskStatus,
)

from .state_client import StateClient

LOCAL_RUNTIME_PROVIDER_ID = "provider-local-runtime-stub"
LOCAL_RUNTIME_MODEL_ID = "model-local-runtime-stub"
LOCAL_RUNTIME_INPUT_COST_PER_MILLION = 0.01
LOCAL_RUNTIME_OUTPUT_COST_PER_MILLION = 0.02


class NoReadyTask(Exception):
    pass


class TaskRunnerUnavailable(Exception):
    pass


class TaskRunnerRequestError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class ControlPlaneClient(Protocol):
    def get_world_view(self, agent_id: str) -> LocalWorldView: ...


class MemoryClient(Protocol):
    def assemble_context(self, context: MemoryContext) -> MemoryContext: ...


class AgentRuntimeClient(Protocol):
    def run_task(self, request: AgentTaskRequest) -> AgentResult: ...


@dataclass(frozen=True)
class HttpControlPlaneClient:
    base_url: str
    timeout_seconds: float = 5.0

    def get_world_view(self, agent_id: str) -> LocalWorldView:
        response = get_json(
            f"{self.base_url.rstrip('/')}/agents/{agent_id}/world-view",
            self.timeout_seconds,
        )
        return LocalWorldView.model_validate(response)


@dataclass(frozen=True)
class HttpMemoryClient:
    base_url: str
    timeout_seconds: float = 5.0

    def assemble_context(self, context: MemoryContext) -> MemoryContext:
        response = post_json(
            f"{self.base_url.rstrip('/')}/context/assemble",
            context.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return MemoryContext.model_validate(response)


@dataclass(frozen=True)
class HttpAgentRuntimeClient:
    base_url: str
    timeout_seconds: float = 5.0

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        response = post_json(
            f"{self.base_url.rstrip('/')}/tasks/run",
            request.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return AgentResult.model_validate(response)


@dataclass(frozen=True)
class TaskRunner:
    state: StateClient
    control_plane: ControlPlaneClient
    memory: MemoryClient
    runtime: AgentRuntimeClient
    memory_token_budget: int = 1200

    def run_next(self, *, trace_id: str, headers: dict[str, str]) -> TaskRunResult:
        task = next_ready_task(self.state.list_tasks())
        if task is None:
            raise NoReadyTask("No queued task is ready to run")

        started_task = self.state.start_task(task.id, headers=headers)
        world_view = self.control_plane.get_world_view(started_task.assigned_agent_id)
        memory_context = self.memory.assemble_context(
            MemoryContext(
                agent_id=started_task.assigned_agent_id,
                project_id=started_task.project_id,
                token_budget=self.memory_token_budget,
                allowed_scopes=memory_scopes_for_run(started_task, world_view),
            )
        )
        started_event = self.state.create_event(
            model_call_started_event(
                task=started_task,
                world_view=world_view,
                memory_context=memory_context,
                trace_id=trace_id,
            ),
            headers=headers,
        )
        try:
            agent_result = self.runtime.run_task(
                AgentTaskRequest(
                    task=started_task,
                    world_view=world_view,
                    memory_context=memory_context,
                )
            )
        except (TaskRunnerRequestError, TaskRunnerUnavailable) as error:
            self.state.create_event(
                model_call_failed_event(
                    task=started_task,
                    world_view=world_view,
                    trace_id=trace_id,
                    error=str(error),
                ),
                headers=headers,
            )
            raise

        cost_record = cost_record_for_run(
            task=started_task,
            world_view=world_view,
            memory_context=memory_context,
            agent_result=agent_result,
            trace_id=trace_id,
        )
        completed_event = self.state.create_event(
            model_call_completed_event(
                task=started_task,
                world_view=world_view,
                agent_result=agent_result,
                cost_record=cost_record,
                trace_id=trace_id,
            ),
            headers=headers,
        )
        recorded_task = self.state.record_task_result(
            started_task.id,
            agent_result,
            headers=headers,
        )
        cost_record = self.state.create_cost_record(
            cost_record,
            headers=headers,
        )
        return TaskRunResult(
            trace_id=trace_id,
            task=recorded_task,
            world_view=world_view,
            memory_context=memory_context,
            agent_result=agent_result,
            model_call_events=[started_event, completed_event],
            cost_records=[cost_record],
        )


def next_ready_task(tasks: list[TaskRecord]) -> TaskRecord | None:
    task_by_id = {task.id: task for task in tasks}
    for task in tasks:
        if task.status != TaskStatus.queued:
            continue
        if all(
            (dependency := task_by_id.get(dependency_id)) is not None
            and dependency.status == TaskStatus.completed
            for dependency_id in task.depends_on
        ):
            return task
    return None


def cost_record_for_run(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    memory_context: MemoryContext,
    agent_result: AgentResult,
    trace_id: str,
) -> CostRecord:
    input_tokens = estimated_tokens(
        task.model_dump_json(),
        world_view.model_dump_json(),
        memory_context.model_dump_json(),
    )
    output_tokens = estimated_tokens(agent_result.model_dump_json())
    total_cost = round(
        (input_tokens * LOCAL_RUNTIME_INPUT_COST_PER_MILLION / 1_000_000)
        + (output_tokens * LOCAL_RUNTIME_OUTPUT_COST_PER_MILLION / 1_000_000),
        8,
    )
    return CostRecord(
        provider_id=LOCAL_RUNTIME_PROVIDER_ID,
        model_id=LOCAL_RUNTIME_MODEL_ID,
        agent_id=agent_result.agent_id,
        project_id=task.project_id,
        task_id=task.id,
        trace_id=trace_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost=total_cost,
    )


def estimated_tokens(*texts: str) -> int:
    return max(1, (sum(len(text) for text in texts) + 3) // 4)


def memory_scopes_for_run(task: TaskRecord, world_view: LocalWorldView) -> list[str]:
    return [
        "global",
        f"division:{world_view.division}",
        f"agent:{world_view.agent_id}",
        f"project:{task.project_id}",
    ]


def model_call_started_event(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    memory_context: MemoryContext,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.model_call_started,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "provider_id": LOCAL_RUNTIME_PROVIDER_ID,
            "model_id": LOCAL_RUNTIME_MODEL_ID,
            "purpose": "task.run",
            "input_tokens_estimate": estimated_tokens(
                task.model_dump_json(),
                world_view.model_dump_json(),
                memory_context.model_dump_json(),
            ),
        },
        trace_id=trace_id,
    )


def model_call_completed_event(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    agent_result: AgentResult,
    cost_record: CostRecord,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.model_call_completed,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "provider_id": cost_record.provider_id,
            "model_id": cost_record.model_id,
            "cost_id": cost_record.id,
            "status": agent_result.status,
            "input_tokens": cost_record.input_tokens,
            "output_tokens": cost_record.output_tokens,
            "total_cost": cost_record.total_cost,
            "currency": cost_record.currency,
        },
        trace_id=trace_id,
    )


def model_call_failed_event(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    trace_id: str,
    error: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.model_call_failed,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "provider_id": LOCAL_RUNTIME_PROVIDER_ID,
            "model_id": LOCAL_RUNTIME_MODEL_ID,
            "error": error,
        },
        trace_id=trace_id,
    )


def get_json(url: str, timeout_seconds: float) -> Any:
    try:
        response = httpx.get(url, timeout=timeout_seconds)
    except httpx.HTTPError as error:
        raise TaskRunnerUnavailable(str(error)) from error
    return checked_json(response)


def post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> Any:
    try:
        response = httpx.post(url, json=payload, timeout=timeout_seconds)
    except httpx.HTTPError as error:
        raise TaskRunnerUnavailable(str(error)) from error
    return checked_json(response)


def checked_json(response: httpx.Response) -> Any:
    if 400 <= response.status_code < 500:
        raise TaskRunnerRequestError(response.status_code, response_detail(response))
    try:
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise TaskRunnerUnavailable(str(error)) from error
    return response.json()


def response_detail(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict):
        return body.get("detail", body)
    return body
