from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from synarch_models import (
    ActorType,
    AgentResult,
    AgentTaskRequest,
    AuditLogRecord,
    CostRecord,
    EventRecord,
    EventType,
    LocalWorldView,
    MemoryContext,
    MemoryItem,
    MemoryStatus,
    MemoryStatusUpdate,
    TaskDraft,
    TaskLeaseRecoveryResult,
    TaskRecord,
    TaskRunBatchResult,
    TaskRunResult,
    TaskStatus,
)

from .state_client import StateClient, StateServiceRequestError

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

    def create_memory_item(self, item: MemoryItem) -> MemoryItem: ...

    def list_memory_items(
        self,
        *,
        scope: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        status: MemoryStatus | None = None,
    ) -> list[MemoryItem]: ...

    def update_memory_status(self, item_id: str, update: MemoryStatusUpdate) -> MemoryItem: ...


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

    def create_memory_item(self, item: MemoryItem) -> MemoryItem:
        response = post_json(
            f"{self.base_url.rstrip('/')}/memory-items",
            item.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return MemoryItem.model_validate(response)

    def list_memory_items(
        self,
        *,
        scope: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        status: MemoryStatus | None = None,
    ) -> list[MemoryItem]:
        params = memory_query_params(
            scope=scope,
            agent_id=agent_id,
            project_id=project_id,
            status=status,
        )
        response = get_json(
            f"{self.base_url.rstrip('/')}/memory-items",
            self.timeout_seconds,
            params=params,
        )
        return [MemoryItem.model_validate(item) for item in response]

    def update_memory_status(self, item_id: str, update: MemoryStatusUpdate) -> MemoryItem:
        response = patch_json(
            f"{self.base_url.rstrip('/')}/memory-items/{item_id}/status",
            update.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return MemoryItem.model_validate(response)


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
    provider_id: str = LOCAL_RUNTIME_PROVIDER_ID
    model_id: str = LOCAL_RUNTIME_MODEL_ID
    input_cost_per_million_tokens: float = LOCAL_RUNTIME_INPUT_COST_PER_MILLION
    output_cost_per_million_tokens: float = LOCAL_RUNTIME_OUTPUT_COST_PER_MILLION

    def run_next(self, *, trace_id: str, headers: dict[str, str]) -> TaskRunResult:
        task = next_ready_task(self.state.list_tasks())
        if task is None:
            raise NoReadyTask("No queued task is ready to run")

        return self.run_task(task.id, trace_id=trace_id, headers=headers)

    def run_ready(
        self,
        *,
        max_tasks: int,
        trace_id: str,
        headers: dict[str, str],
        project_id: str | None = None,
    ) -> TaskRunBatchResult:
        lease_recovery = self.state.recover_expired_task_leases(headers=headers)
        runs: list[TaskRunResult] = []
        skipped_task_ids: list[str] = []
        stop_reason = "max_tasks_reached"
        while len(runs) < max_tasks:
            task = next_ready_task(
                self.state.list_tasks(project_id=project_id),
                excluded_task_ids=set(skipped_task_ids),
            )
            if task is None:
                stop_reason = "no_ready_task"
                break
            try:
                runs.append(self.run_task(task.id, trace_id=trace_id, headers=headers))
            except StateServiceRequestError as error:
                if not is_task_claim_conflict(error):
                    raise
                skipped_task_ids.append(task.id)

        batch_result = TaskRunBatchResult(
            trace_id=trace_id,
            max_tasks=max_tasks,
            project_id=project_id,
            stop_reason=stop_reason,
            runs=runs,
            skipped_task_ids=skipped_task_ids,
            lease_recovery=lease_recovery,
        )
        scheduler_event = self.state.create_event(
            scheduler_tick_event(batch_result),
            headers=headers,
        )
        scheduler_audit_log = self.state.create_audit_log(
            scheduler_tick_audit(batch_result),
            headers=headers,
        )
        return batch_result.model_copy(
            update={
                "scheduler_event": scheduler_event,
                "scheduler_audit_log": scheduler_audit_log,
            }
        )

    def run_task(
        self,
        task_id: str,
        *,
        trace_id: str,
        headers: dict[str, str],
    ) -> TaskRunResult:
        task = self.state.get_task(task_id)
        started_task = self.state.start_task(task.id, headers=headers)
        project = self.state.get_project(started_task.project_id)
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
                provider_id=self.provider_id,
                model_id=self.model_id,
                trace_id=trace_id,
            ),
            headers=headers,
        )
        try:
            agent_result = self.runtime.run_task(
                AgentTaskRequest(
                    task=started_task,
                    project=project,
                    world_view=world_view,
                    memory_context=memory_context,
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                )
            )
        except (TaskRunnerRequestError, TaskRunnerUnavailable) as error:
            failed_event = self.state.create_event(
                model_call_failed_event(
                    task=started_task,
                    world_view=world_view,
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    trace_id=trace_id,
                    error=str(error),
                ),
                headers=headers,
            )
            failure_result = AgentResult(
                agent_id=world_view.agent_id,
                task_id=started_task.id,
                status=TaskStatus.failed,
                actions_taken=["Model call failed before task completion."],
                summary=f"Model call failed: {error}",
            )
            recorded_task = self.state.record_task_result(
                started_task.id,
                failure_result,
                headers=headers,
            )
            return TaskRunResult(
                trace_id=trace_id,
                task=recorded_task,
                project=project,
                world_view=world_view,
                memory_context=memory_context,
                agent_result=failure_result,
                model_call_events=[started_event, failed_event],
                cost_records=[],
            )

        agent_result = agent_result.model_copy(
            update={
                "memory_candidates": proposed_memory_candidates(
                    task=started_task,
                    world_view=world_view,
                    agent_result=agent_result,
                )
            }
        )
        cost_record = cost_record_for_run(
            task=started_task,
            world_view=world_view,
            memory_context=memory_context,
            agent_result=agent_result,
            provider_id=self.provider_id,
            model_id=self.model_id,
            input_cost_per_million_tokens=self.input_cost_per_million_tokens,
            output_cost_per_million_tokens=self.output_cost_per_million_tokens,
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
        memory_events = self.persist_memory_candidates(
            task=recorded_task,
            world_view=world_view,
            agent_result=agent_result,
            trace_id=trace_id,
            headers=headers,
        )
        created_sub_tasks, sub_task_events = self.persist_sub_tasks(
            parent_task=recorded_task,
            world_view=world_view,
            agent_result=agent_result,
            trace_id=trace_id,
            headers=headers,
        )
        return TaskRunResult(
            trace_id=trace_id,
            task=recorded_task,
            project=project,
            world_view=world_view,
            memory_context=memory_context,
            agent_result=agent_result,
            model_call_events=[started_event, completed_event],
            created_sub_tasks=created_sub_tasks,
            sub_task_events=sub_task_events,
            memory_events=memory_events,
            cost_records=[cost_record],
        )

    def persist_memory_candidates(
        self,
        *,
        task: TaskRecord,
        world_view: LocalWorldView,
        agent_result: AgentResult,
        trace_id: str,
        headers: dict[str, str],
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        for candidate in agent_result.memory_candidates:
            memory_item = self.memory.create_memory_item(candidate)
            events.append(
                self.state.create_event(
                    memory_candidate_created_event(
                        task=task,
                        world_view=world_view,
                        memory_item=memory_item,
                        trace_id=trace_id,
                    ),
                    headers=headers,
                )
            )
        return events

    def persist_sub_tasks(
        self,
        *,
        parent_task: TaskRecord,
        world_view: LocalWorldView,
        agent_result: AgentResult,
        trace_id: str,
        headers: dict[str, str],
    ) -> tuple[list[TaskRecord], list[EventRecord]]:
        created_tasks: list[TaskRecord] = []
        events: list[EventRecord] = []
        task_ids_by_title: dict[str, str] = {}
        for index, draft in enumerate(agent_result.sub_tasks_created, start=1):
            created_task = self.state.create_task(
                child_task_record(parent_task, draft, index, task_ids_by_title),
                headers=headers,
            )
            created_tasks.append(created_task)
            task_ids_by_title[draft.title] = created_task.id
            events.append(
                self.state.create_event(
                    sub_task_created_event(
                        task=created_task,
                        parent_task=parent_task,
                        world_view=world_view,
                        trace_id=trace_id,
                    ),
                    headers=headers,
                )
            )
        return created_tasks, events


def proposed_memory_candidates(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    agent_result: AgentResult,
) -> list[MemoryItem]:
    return [
        candidate.model_copy(
            update={
                "scope": f"project:{task.project_id}",
                "agent_id": world_view.agent_id,
                "project_id": task.project_id,
                "status": MemoryStatus.proposed,
            }
        )
        for candidate in agent_result.memory_candidates
    ]


def child_task_record(
    parent_task: TaskRecord,
    draft: TaskDraft,
    index: int,
    task_ids_by_title: dict[str, str],
) -> TaskRecord:
    sequence = draft.sequence or parent_task.sequence * 100 + index
    return TaskRecord(
        project_id=parent_task.project_id,
        title=draft.title,
        description=draft.description,
        assigned_agent_id=draft.assigned_agent_id,
        depends_on=child_task_dependencies(parent_task, draft, task_ids_by_title),
        acceptance_criteria=draft.acceptance_criteria,
        parent_task_id=parent_task.id,
        sequence=sequence,
    )


def child_task_dependencies(
    parent_task: TaskRecord,
    draft: TaskDraft,
    task_ids_by_title: dict[str, str],
) -> list[str]:
    dependencies = [parent_task.id]
    for dependency in draft.depends_on:
        if dependency in task_ids_by_title:
            dependencies.append(task_ids_by_title[dependency])
        elif dependency in task_ids_by_title.values():
            dependencies.append(dependency)
        elif dependency == parent_task.id:
            dependencies.append(parent_task.id)
    return deduplicate(dependencies)


def deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def next_ready_task(
    tasks: list[TaskRecord],
    *,
    excluded_task_ids: set[str] | None = None,
) -> TaskRecord | None:
    excluded_task_ids = excluded_task_ids or set()
    task_by_id = {task.id: task for task in tasks}
    now = datetime.now(UTC)
    for task in tasks:
        if task.id in excluded_task_ids:
            continue
        if task.status != TaskStatus.queued:
            continue
        if task.retry_after_at is not None and task.retry_after_at > now:
            continue
        if all(
            (dependency := task_by_id.get(dependency_id)) is not None
            and dependency.status == TaskStatus.completed
            for dependency_id in task.depends_on
        ):
            return task
    return None


def is_task_claim_conflict(error: StateServiceRequestError) -> bool:
    if error.status_code != 409:
        return False
    detail = str(error.detail)
    return detail.startswith("Task is already ") or detail.startswith(
        "Task dependencies are not completed:"
    )


def cost_record_for_run(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    memory_context: MemoryContext,
    agent_result: AgentResult,
    provider_id: str,
    model_id: str,
    input_cost_per_million_tokens: float,
    output_cost_per_million_tokens: float,
    trace_id: str,
) -> CostRecord:
    if agent_result.model_usage is not None:
        return CostRecord(
            provider_id=agent_result.model_usage.provider_id,
            model_id=agent_result.model_usage.model_id,
            agent_id=agent_result.agent_id,
            project_id=task.project_id,
            task_id=task.id,
            trace_id=trace_id,
            input_tokens=agent_result.model_usage.input_tokens,
            output_tokens=agent_result.model_usage.output_tokens,
            total_cost=agent_result.model_usage.total_cost,
            currency=agent_result.model_usage.currency,
        )

    input_tokens = estimated_tokens(
        task.model_dump_json(),
        world_view.model_dump_json(),
        memory_context.model_dump_json(),
    )
    output_tokens = estimated_tokens(agent_result.model_dump_json())
    total_cost = round(
        (input_tokens * input_cost_per_million_tokens / 1_000_000)
        + (output_tokens * output_cost_per_million_tokens / 1_000_000),
        8,
    )
    return CostRecord(
        provider_id=provider_id,
        model_id=model_id,
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
    provider_id: str,
    model_id: str,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.model_call_started,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "provider_id": provider_id,
            "model_id": model_id,
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
    provider_id: str,
    model_id: str,
    trace_id: str,
    error: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.model_call_failed,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "provider_id": provider_id,
            "model_id": model_id,
            "error": error,
        },
        trace_id=trace_id,
    )


def memory_candidate_created_event(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    memory_item: MemoryItem,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.memory_candidate_created,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "memory_id": memory_item.id,
            "scope": memory_item.scope,
            "status": memory_item.status,
        },
        trace_id=trace_id,
    )


def scheduler_tick_event(batch_result: TaskRunBatchResult) -> EventRecord:
    return EventRecord(
        type=EventType.scheduler_tick,
        target=batch_result.project_id or "scheduler",
        payload=scheduler_tick_payload(batch_result),
        trace_id=batch_result.trace_id,
    )


def scheduler_tick_audit(batch_result: TaskRunBatchResult) -> AuditLogRecord:
    return AuditLogRecord(
        actor_type=ActorType.service,
        actor_id="gateway-scheduler",
        action="scheduler.tick",
        target_type="project" if batch_result.project_id is not None else "scheduler",
        target_id=batch_result.project_id or "scheduler",
        payload=scheduler_tick_payload(batch_result),
        trace_id=batch_result.trace_id,
    )


def scheduler_tick_payload(batch_result: TaskRunBatchResult) -> dict[str, object]:
    return {
        "project_id": batch_result.project_id,
        "max_tasks": batch_result.max_tasks,
        "stop_reason": batch_result.stop_reason,
        "run_count": len(batch_result.runs),
        "task_ids": [run.task.id for run in batch_result.runs],
        "skipped_task_ids": batch_result.skipped_task_ids,
        "skipped_task_count": len(batch_result.skipped_task_ids),
        "lease_recovered_task_ids": lease_recovered_task_ids(batch_result.lease_recovery),
        "lease_failed_task_ids": lease_failed_task_ids(batch_result.lease_recovery),
        "created_sub_task_count": sum(
            len(run.created_sub_tasks) for run in batch_result.runs
        ),
        "cost_ids": [
            cost_record.id
            for run in batch_result.runs
            for cost_record in run.cost_records
        ],
    }


def lease_recovered_task_ids(lease_recovery: TaskLeaseRecoveryResult | None) -> list[str]:
    if lease_recovery is None:
        return []
    return lease_recovery.recovered_task_ids


def lease_failed_task_ids(lease_recovery: TaskLeaseRecoveryResult | None) -> list[str]:
    if lease_recovery is None:
        return []
    return lease_recovery.failed_task_ids


def sub_task_created_event(
    *,
    task: TaskRecord,
    parent_task: TaskRecord,
    world_view: LocalWorldView,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.task_created,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "parent_task_id": parent_task.id,
            "assigned_agent_id": task.assigned_agent_id,
            "depends_on": task.depends_on,
            "acceptance_criteria": task.acceptance_criteria,
            "sequence": task.sequence,
        },
        trace_id=trace_id,
    )


def memory_query_params(
    *,
    scope: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    status: MemoryStatus | None = None,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if scope is not None:
        params["scope"] = scope
    if agent_id is not None:
        params["agent_id"] = agent_id
    if project_id is not None:
        params["project_id"] = project_id
    if status is not None:
        params["status"] = status.value
    return params


def get_json(
    url: str,
    timeout_seconds: float,
    *,
    params: dict[str, str] | None = None,
) -> Any:
    try:
        response = httpx.get(url, params=params, timeout=timeout_seconds)
    except httpx.HTTPError as error:
        raise TaskRunnerUnavailable(str(error)) from error
    return checked_json(response)


def post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> Any:
    try:
        response = httpx.post(url, json=payload, timeout=timeout_seconds)
    except httpx.HTTPError as error:
        raise TaskRunnerUnavailable(str(error)) from error
    return checked_json(response)


def patch_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> Any:
    try:
        response = httpx.patch(url, json=payload, timeout=timeout_seconds)
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
