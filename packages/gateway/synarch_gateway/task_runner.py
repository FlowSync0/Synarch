import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from synarch_models import (
    ActorType,
    AgentLifecycleRequest,
    AgentResult,
    AgentTaskRequest,
    ApprovalStatus,
    AuditLogRecord,
    CostRecord,
    CredentialAccessRequest,
    EventRecord,
    EventType,
    LocalWorldView,
    MemoryCompactionPlanRequest,
    MemoryCompactionPlanResult,
    MemoryCompactionPolicyRequest,
    MemoryCompactionPolicyResult,
    MemoryCompactionRequest,
    MemoryCompactionResult,
    MemoryContext,
    MemoryItem,
    MemoryStatus,
    MemoryStatusUpdate,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ModelUsage,
    ProjectRecord,
    TaskDraft,
    TaskLeaseRecoveryResult,
    TaskRecord,
    TaskRunBatchResult,
    TaskRunResult,
    TaskSkipRecord,
    TaskStatus,
    ToolCallRequest,
    ToolResult,
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

    def compact_memory_items(
        self, request: MemoryCompactionRequest
    ) -> MemoryCompactionResult: ...

    def compact_memory_items_if_needed(
        self, request: MemoryCompactionPolicyRequest
    ) -> MemoryCompactionPolicyResult: ...

    def plan_memory_compaction(
        self, request: MemoryCompactionPlanRequest
    ) -> MemoryCompactionPlanResult: ...


class AgentRuntimeClient(Protocol):
    def run_task(self, request: AgentTaskRequest) -> AgentResult: ...


class QueryEmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...


class ToolRunner(Protocol):
    def call_tool(
        self,
        tool_call: ToolCallRequest,
        *,
        state_client: StateClient,
        control_plane: ControlPlaneClient,
        headers: dict[str, str],
        trace_id: str,
    ) -> ToolResult: ...


@dataclass(frozen=True)
class CredentialReadinessBlocker:
    tool_name: str
    reason: str
    requested_scopes: tuple[str, ...] = ()
    candidate_service_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelRoute:
    provider_id: str
    model_id: str
    input_cost_per_million_tokens: float
    output_cost_per_million_tokens: float
    currency: str = "USD"
    model_policy_id: str | None = None


class ToolReadinessChecker(Protocol):
    def credential_blockers(
        self,
        task: TaskRecord,
        world_view: LocalWorldView,
    ) -> list[CredentialReadinessBlocker]: ...


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

    def compact_memory_items(
        self, request: MemoryCompactionRequest
    ) -> MemoryCompactionResult:
        response = post_json(
            f"{self.base_url.rstrip('/')}/memory-items/compact",
            request.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return MemoryCompactionResult.model_validate(response)

    def compact_memory_items_if_needed(
        self, request: MemoryCompactionPolicyRequest
    ) -> MemoryCompactionPolicyResult:
        response = post_json(
            f"{self.base_url.rstrip('/')}/memory-items/compact-if-needed",
            request.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return MemoryCompactionPolicyResult.model_validate(response)

    def plan_memory_compaction(
        self, request: MemoryCompactionPlanRequest
    ) -> MemoryCompactionPlanResult:
        response = post_json(
            f"{self.base_url.rstrip('/')}/memory-items/compaction-plan",
            request.model_dump(mode="json"),
            self.timeout_seconds,
        )
        return MemoryCompactionPlanResult.model_validate(response)


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
class OpenRouterQueryEmbeddingProvider:
    api_key: str
    model_id: str
    provider_id: str = "provider-openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 20.0
    expected_dimensions: int = 1536

    def embed_text(self, text: str) -> list[float]:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "input": text,
                    "encoding_format": "float",
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise TaskRunnerUnavailable("Query embedding request failed") from error

        if response.status_code >= 400:
            raise TaskRunnerUnavailable(
                f"Query embedding provider returned {response.status_code}"
            )

        body = response.json()
        raw_data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(raw_data, list) or not raw_data:
            raise TaskRunnerUnavailable("Query embedding provider returned no data")
        first_item = raw_data[0]
        raw_embedding = first_item.get("embedding") if isinstance(first_item, dict) else None
        if not isinstance(raw_embedding, list):
            raise TaskRunnerUnavailable("Query embedding provider returned no embedding")

        embedding = [float(value) for value in raw_embedding]
        if len(embedding) != self.expected_dimensions:
            raise TaskRunnerUnavailable(
                "Query embedding provider returned "
                f"{len(embedding)} dimensions, expected {self.expected_dimensions}"
            )
        return embedding


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
    tool_runner: ToolRunner | None = None
    tool_readiness: ToolReadinessChecker | None = None
    query_embedding_provider: QueryEmbeddingProvider | None = None
    max_tool_rounds: int = 1
    max_tool_calls_per_round: int = 1

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
        skipped_tasks: list[TaskSkipRecord] = []
        credential_access_requests: list[CredentialAccessRequest] = []
        credential_resumed_task_ids: list[str] = []
        stop_reason = "max_tasks_reached"
        while len(runs) < max_tasks:
            task = next_ready_task(
                self.state.list_tasks(project_id=project_id),
                excluded_task_ids=set(skipped_task_ids),
            )
            if task is None:
                stop_reason = "no_ready_task"
                break
            blockers = self.credential_blockers_for_task(task)
            if blockers:
                skipped_task_ids.append(task.id)
                skipped_tasks.append(
                    TaskSkipRecord(
                        task_id=task.id,
                        category="credential_readiness",
                        reason="; ".join(blocker.reason for blocker in blockers),
                    )
                )
                credential_access_requests.extend(
                    self.create_credential_access_requests(
                        task,
                        blockers,
                        headers=headers,
                    )
                )
                continue
            was_credential_resumed = self.task_has_applied_credential_request(task)
            try:
                run = self.run_task(task.id, trace_id=trace_id, headers=headers)
                runs.append(run)
                if was_credential_resumed:
                    credential_resumed_task_ids.append(task.id)
            except StateServiceRequestError as error:
                inactive_agent_skip_reason = inactive_agent_skip_reason_from_error(error)
                if inactive_agent_skip_reason is not None:
                    skipped_task_ids.append(task.id)
                    skipped_tasks.append(
                        TaskSkipRecord(
                            task_id=task.id,
                            category="inactive_agent",
                            reason=inactive_agent_skip_reason,
                        )
                    )
                    continue
                if not is_task_claim_conflict(error):
                    raise
                skipped_task_ids.append(task.id)
                skipped_tasks.append(
                    TaskSkipRecord(
                        task_id=task.id,
                        category="claim_conflict",
                        reason="Task was already claimed by another scheduler.",
                    )
                )

        batch_result = TaskRunBatchResult(
            trace_id=trace_id,
            max_tasks=max_tasks,
            project_id=project_id,
            stop_reason=stop_reason,
            runs=runs,
            skipped_task_ids=skipped_task_ids,
            skipped_tasks=skipped_tasks,
            credential_access_requests=credential_access_requests,
            credential_resumed_task_ids=credential_resumed_task_ids,
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

    def credential_blockers_for_task(self, task: TaskRecord) -> list[CredentialReadinessBlocker]:
        if self.tool_readiness is None or not task.required_tools:
            return []
        world_view = self.control_plane.get_world_view(task.assigned_agent_id)
        return self.tool_readiness.credential_blockers(task, world_view)

    def task_has_applied_credential_request(self, task: TaskRecord) -> bool:
        return bool(
            self.state.list_credential_access_requests(
                task_id=task.id,
                status=ApprovalStatus.applied.value,
            )
        )

    def model_route_for_world_view(self, world_view: LocalWorldView) -> ModelRoute:
        model_policy_id = model_policy_id_from_world_view(world_view)
        if model_policy_id is None:
            return ModelRoute(
                provider_id=self.provider_id,
                model_id=self.model_id,
                input_cost_per_million_tokens=self.input_cost_per_million_tokens,
                output_cost_per_million_tokens=self.output_cost_per_million_tokens,
            )

        policy = self.state.get_model_policy(model_policy_id)
        selected_model_id = selected_model_id_for_policy(self.model_id, policy)
        allowed_model_ids = {policy.default_model_id, *policy.allowed_model_ids}
        if selected_model_id not in allowed_model_ids:
            raise TaskRunnerUnavailable(
                f"Model {selected_model_id} is not allowed by policy {policy.id}"
            )

        model = self.state.get_model_definition(selected_model_id)
        if not model.enabled:
            raise TaskRunnerUnavailable(f"Model is disabled: {model.id}")
        provider = self.state.get_model_provider(model.provider_id)
        if not provider.enabled:
            raise TaskRunnerUnavailable(f"Model provider is disabled: {provider.id}")
        return model_route_from_state(policy, model, provider)

    def create_credential_access_requests(
        self,
        task: TaskRecord,
        blockers: list[CredentialReadinessBlocker],
        *,
        headers: dict[str, str],
    ) -> list[CredentialAccessRequest]:
        created_requests: list[CredentialAccessRequest] = []
        for blocker in blockers:
            access_request = CredentialAccessRequest(
                id=credential_access_request_id(task.id, blocker.tool_name),
                task_id=task.id,
                project_id=task.project_id,
                agent_id=task.assigned_agent_id,
                tool_name=blocker.tool_name,
                requested_scopes=list(blocker.requested_scopes),
                candidate_service_ids=list(blocker.candidate_service_ids),
                reason=blocker.reason,
            )
            try:
                created_requests.append(
                    self.state.create_credential_access_request(
                        access_request,
                        headers=headers,
                    )
                )
            except StateServiceRequestError as error:
                if error.status_code != 409:
                    raise
        return created_requests

    def run_task(
        self,
        task_id: str,
        *,
        trace_id: str,
        headers: dict[str, str],
    ) -> TaskRunResult:
        task = self.state.get_task(task_id)
        try:
            started_task = self.state.start_task(task.id, headers=headers)
        except StateServiceRequestError as error:
            self.record_task_start_rejection(
                task=task,
                error=error,
                trace_id=trace_id,
                headers=headers,
            )
            raise
        project = self.state.get_project(started_task.project_id)
        world_view = self.control_plane.get_world_view(started_task.assigned_agent_id)
        bridge_project_ids = bridge_project_ids_for_run(
            self.state,
            project_id=started_task.project_id,
        )
        query_embedding = self.query_embedding_for_task(started_task, project)
        memory_context = self.memory.assemble_context(
            MemoryContext(
                agent_id=started_task.assigned_agent_id,
                project_id=started_task.project_id,
                token_budget=self.memory_token_budget,
                allowed_scopes=memory_scopes_for_run(
                    started_task,
                    world_view,
                    bridge_project_ids=bridge_project_ids,
                ),
                allowed_project_ids=deduplicate(
                    [started_task.project_id, *bridge_project_ids]
                ),
                query_embedding=query_embedding,
            )
        )
        query_embedding_dimensions = len(query_embedding) if query_embedding is not None else 0
        memory_context = memory_context_without_embeddings(memory_context)
        try:
            model_route = self.model_route_for_world_view(world_view)
        except (StateServiceRequestError, TaskRunnerUnavailable) as error:
            failed_event = self.state.create_event(
                model_call_failed_event(
                    task=started_task,
                    world_view=world_view,
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    model_policy_id=model_policy_id_from_world_view(world_view),
                    trace_id=trace_id,
                    error=f"Model route failed: {error}",
                ),
                headers=headers,
            )
            failure_result = AgentResult(
                agent_id=world_view.agent_id,
                task_id=started_task.id,
                status=TaskStatus.failed,
                actions_taken=["Model route failed before task execution."],
                summary=f"Model route failed: {error}",
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
                model_call_events=[failed_event],
                tool_results=[],
                cost_records=[],
            )
        started_event = self.state.create_event(
            model_call_started_event(
                task=started_task,
                world_view=world_view,
                memory_context=memory_context,
                provider_id=model_route.provider_id,
                model_id=model_route.model_id,
                model_policy_id=model_route.model_policy_id,
                trace_id=trace_id,
                memory_query_embedding_used=query_embedding is not None,
                memory_query_embedding_dimensions=query_embedding_dimensions,
            ),
            headers=headers,
        )
        try:
            agent_result, tool_results = self.run_agent_task_with_tools(
                task=started_task,
                project=project,
                world_view=world_view,
                memory_context=memory_context,
                model_route=model_route,
                trace_id=trace_id,
                headers=headers,
            )
        except (TaskRunnerRequestError, TaskRunnerUnavailable) as error:
            failed_event = self.state.create_event(
                model_call_failed_event(
                    task=started_task,
                    world_view=world_view,
                    provider_id=model_route.provider_id,
                    model_id=model_route.model_id,
                    model_policy_id=model_route.model_policy_id,
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
                tool_results=[],
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
            provider_id=model_route.provider_id,
            model_id=model_route.model_id,
            input_cost_per_million_tokens=model_route.input_cost_per_million_tokens,
            output_cost_per_million_tokens=model_route.output_cost_per_million_tokens,
            currency=model_route.currency,
            trace_id=trace_id,
        )
        completed_event = self.state.create_event(
            model_call_completed_event(
                task=started_task,
                world_view=world_view,
                agent_result=agent_result,
                cost_record=cost_record,
                model_policy_id=model_route.model_policy_id,
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
        lifecycle_requests_created = self.persist_lifecycle_requests(
            world_view=world_view,
            agent_result=agent_result,
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
            lifecycle_requests_created=lifecycle_requests_created,
            memory_events=memory_events,
            tool_results=tool_results,
            cost_records=[cost_record],
        )

    def query_embedding_for_task(
        self,
        task: TaskRecord,
        project: ProjectRecord | None,
    ) -> list[float] | None:
        if self.query_embedding_provider is None:
            return None
        try:
            return self.query_embedding_provider.embed_text(memory_query_text(task, project))
        except TaskRunnerUnavailable:
            return None

    def record_task_start_rejection(
        self,
        *,
        task: TaskRecord,
        error: StateServiceRequestError,
        trace_id: str,
        headers: dict[str, str],
    ) -> None:
        skipped_task = task_start_skip_record_from_error(task, error)
        self.state.create_event(
            task_run_skipped_event(
                task=task,
                skipped_task=skipped_task,
                error=error,
                trace_id=trace_id,
            ),
            headers=headers,
        )
        self.state.create_audit_log(
            task_run_skipped_audit(
                task=task,
                skipped_task=skipped_task,
                error=error,
                trace_id=trace_id,
                headers=headers,
            ),
            headers=headers,
        )

    def run_agent_task_with_tools(
        self,
        *,
        task: TaskRecord,
        project: ProjectRecord | None,
        world_view: LocalWorldView,
        memory_context: MemoryContext,
        model_route: ModelRoute,
        trace_id: str,
        headers: dict[str, str],
    ) -> tuple[AgentResult, list[ToolResult]]:
        tool_results: list[ToolResult] = []
        agent_result = self.runtime.run_task(
            AgentTaskRequest(
                task=task,
                project=project,
                world_view=world_view,
                memory_context=memory_context,
                tool_results=tool_results,
                provider_id=model_route.provider_id,
                model_id=model_route.model_id,
            )
        )
        combined_usage = agent_result.model_usage
        combined_actions = list(agent_result.actions_taken)
        completed_tool_call_keys: set[str] = set()
        failed_tool_call_keys: set[str] = set()
        completed_tool_rounds = 0

        for _ in range(self.max_tool_rounds):
            if self.tool_runner is None or not agent_result.tool_calls_requested:
                break
            selected_tool_calls = select_tool_calls_for_round(
                agent_result.tool_calls_requested,
                task=task,
                world_view=world_view,
                trace_id=trace_id,
                skipped_tool_call_keys=completed_tool_call_keys | failed_tool_call_keys,
                max_tool_calls=self.max_tool_calls_per_round,
            )
            if not selected_tool_calls:
                failed_pending_tools = failed_pending_tool_names(
                    agent_result,
                    task=task,
                    world_view=world_view,
                    trace_id=trace_id,
                    failed_tool_call_keys=failed_tool_call_keys,
                )
                if failed_pending_tools:
                    combined_actions.append(
                        "Tool loop paused because requested tool calls already failed or blocked."
                    )
                    next_status = unresolved_tool_result_review_status(tool_results)
                    agent_result = agent_result.model_copy(
                        update={
                            "status": next_status,
                            "summary": (
                                "Tool loop paused because requested tool calls already "
                                "failed or blocked with the same arguments; corrected "
                                f"tool calls are required for: {', '.join(failed_pending_tools)}."
                            ),
                        }
                    )
                break
            for normalized_tool_call in selected_tool_calls:
                tool_call_key = tool_call_execution_key(normalized_tool_call)
                tool_result = self.tool_runner.call_tool(
                    normalized_tool_call,
                    state_client=self.state,
                    control_plane=self.control_plane,
                    headers=headers,
                    trace_id=trace_id,
                )
                tool_results.append(tool_result)
                combined_actions.append(f"Tool gate executed {tool_result.tool_name}.")
                if tool_result.status == TaskStatus.completed:
                    completed_tool_call_keys.add(tool_call_key)
                if tool_result.status != TaskStatus.completed:
                    failed_tool_call_keys.add(tool_call_key)

            completed_tool_rounds += 1
            agent_result = self.runtime.run_task(
                AgentTaskRequest(
                    task=task,
                    project=project,
                    world_view=world_view,
                    memory_context=memory_context,
                    tool_results=tool_results,
                    provider_id=model_route.provider_id,
                    model_id=model_route.model_id,
                )
            )
            combined_usage = combine_model_usage(combined_usage, agent_result.model_usage)
            combined_actions.extend(agent_result.actions_taken)

        if tool_round_limit_reached(
            agent_result=agent_result,
            tool_runner=self.tool_runner,
            max_tool_rounds=self.max_tool_rounds,
            completed_rounds=completed_tool_rounds,
        ):
            pending_tools = pending_tool_names(agent_result)
            combined_actions.append(
                "Tool loop paused after reaching the configured round limit."
            )
            agent_result = agent_result.model_copy(
                update={
                    "status": TaskStatus.needs_review,
                    "summary": (
                        "Tool loop paused after reaching the configured round limit; "
                        f"pending tool calls remain: {', '.join(pending_tools)}."
                    ),
                }
            )

        unresolved_tools = unresolved_non_completed_tool_result_summaries(tool_results)
        if agent_result.status == TaskStatus.completed and unresolved_tools:
            combined_actions.append(
                "Completion overridden because tool results still need review."
            )
            next_status = unresolved_tool_result_review_status(tool_results)
            agent_result = agent_result.model_copy(
                update={
                    "status": next_status,
                    "summary": (
                        "Task cannot be completed because tool results still need "
                        f"review: {', '.join(unresolved_tools)}."
                    ),
                }
            )

        return agent_result.model_copy(
            update={
                "actions_taken": deduplicate(combined_actions),
                "tool_results": tool_results,
                "model_usage": combined_usage,
            }
        ), tool_results

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
            memory_item = self.memory.create_memory_item(
                self.memory_candidate_with_embedding(candidate)
            )
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

    def memory_candidate_with_embedding(self, candidate: MemoryItem) -> MemoryItem:
        if self.query_embedding_provider is None or candidate.embedding is not None:
            return candidate
        try:
            embedding = self.query_embedding_provider.embed_text(candidate.content)
        except TaskRunnerUnavailable:
            return candidate
        return candidate.model_copy(update={"embedding": embedding})

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
            normalized_draft = sub_task_draft_with_safe_agent(
                parent_task,
                world_view,
                draft,
            )
            original_assigned_agent_id = (
                draft.assigned_agent_id
                if normalized_draft.assigned_agent_id != draft.assigned_agent_id
                else None
            )
            created_task = self.state.create_task(
                child_task_record(parent_task, normalized_draft, index, task_ids_by_title),
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
                        original_assigned_agent_id=original_assigned_agent_id,
                    ),
                    headers=headers,
                )
            )
        return created_tasks, events

    def persist_lifecycle_requests(
        self,
        *,
        world_view: LocalWorldView,
        agent_result: AgentResult,
        headers: dict[str, str],
    ) -> list[AgentLifecycleRequest]:
        created_requests: list[AgentLifecycleRequest] = []
        for lifecycle_request in agent_result.lifecycle_requests_created:
            normalized_request = lifecycle_request.model_copy(
                update={
                    "requested_by_type": ActorType.agent.value,
                    "requested_by_id": world_view.agent_id,
                    "status": ApprovalStatus.requested.value,
                    "requires_human_approval": True,
                }
            )
            try:
                created_requests.append(
                    self.state.create_agent_lifecycle_request(
                        normalized_request,
                        headers=headers,
                    )
                )
            except StateServiceRequestError as error:
                if error.status_code != 409:
                    raise
        return created_requests


def tool_call_for_task(
    *,
    tool_call: ToolCallRequest,
    task: TaskRecord,
    world_view: LocalWorldView,
    trace_id: str,
) -> ToolCallRequest:
    return tool_call.model_copy(
        update={
            "agent_id": world_view.agent_id,
            "project_id": tool_call.project_id or task.project_id,
            "task_id": tool_call.task_id or task.id,
            "trace_id": tool_call.trace_id or trace_id,
        }
    )


def select_tool_calls_for_round(
    tool_calls: list[ToolCallRequest],
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    trace_id: str,
    skipped_tool_call_keys: set[str],
    max_tool_calls: int,
) -> list[ToolCallRequest]:
    selected_tool_calls: list[ToolCallRequest] = []
    for tool_call in tool_calls:
        normalized_tool_call = tool_call_for_task(
            tool_call=tool_call,
            task=task,
            world_view=world_view,
            trace_id=trace_id,
        )
        if tool_call_execution_key(normalized_tool_call) in skipped_tool_call_keys:
            continue
        selected_tool_calls.append(normalized_tool_call)
        if len(selected_tool_calls) >= max_tool_calls:
            break
    return selected_tool_calls


def tool_call_execution_key(tool_call: ToolCallRequest) -> str:
    return json.dumps(
        {
            "tool_name": tool_call.tool_name,
            "service_id": tool_call.service_id,
            "project_id": tool_call.project_id,
            "task_id": tool_call.task_id,
            "arguments": tool_call.arguments,
        },
        sort_keys=True,
        default=str,
    )


def failed_pending_tool_names(
    agent_result: AgentResult,
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    trace_id: str,
    failed_tool_call_keys: set[str],
) -> list[str]:
    return deduplicate(
        [
            normalized_tool_call.tool_name
            for normalized_tool_call in (
                tool_call_for_task(
                    tool_call=tool_call,
                    task=task,
                    world_view=world_view,
                    trace_id=trace_id,
                )
                for tool_call in agent_result.tool_calls_requested
            )
            if tool_call_execution_key(normalized_tool_call) in failed_tool_call_keys
        ]
    )


def tool_round_limit_reached(
    *,
    agent_result: AgentResult,
    tool_runner: ToolRunner | None,
    max_tool_rounds: int,
    completed_rounds: int,
) -> bool:
    if tool_runner is None:
        return False
    if not agent_result.tool_calls_requested:
        return False
    return completed_rounds >= max_tool_rounds


def pending_tool_names(agent_result: AgentResult) -> list[str]:
    return deduplicate(
        [tool_call.tool_name for tool_call in agent_result.tool_calls_requested]
    )


def unresolved_non_completed_tool_result_summaries(
    tool_results: list[ToolResult],
) -> list[str]:
    return [
        non_completed_tool_result_summary(tool_result)
        for tool_result in unresolved_non_completed_tool_results(tool_results)
    ]


def unresolved_non_completed_tool_results(
    tool_results: list[ToolResult],
) -> list[ToolResult]:
    completed_tool_names: set[str] = set()
    unresolved_results: list[ToolResult] = []
    seen_keys: set[str] = set()
    for tool_result in reversed(tool_results):
        if tool_result.status == TaskStatus.completed:
            completed_tool_names.add(tool_result.tool_name)
            continue
        if tool_result.tool_name in completed_tool_names:
            continue
        key = non_completed_tool_result_key(tool_result)
        if key in seen_keys:
            continue
        unresolved_results.append(tool_result)
        seen_keys.add(key)
    return list(reversed(unresolved_results))


def non_completed_tool_result_key(tool_result: ToolResult) -> str:
    return json.dumps(
        {
            "tool_name": tool_result.tool_name,
            "status": str(tool_result.status),
            "error": tool_result.error,
            "blocked_reason": tool_result.output.get("blocked_reason"),
            "error_output": tool_result.output.get("error"),
        },
        sort_keys=True,
        default=str,
    )


def unresolved_tool_result_review_status(tool_results: list[ToolResult]) -> TaskStatus:
    if any(
        tool_result.status == TaskStatus.blocked
        for tool_result in unresolved_non_completed_tool_results(tool_results)
    ):
        return TaskStatus.blocked
    return TaskStatus.needs_review


def non_completed_tool_result_summary(tool_result: ToolResult) -> str:
    status = (
        tool_result.status.value
        if isinstance(tool_result.status, TaskStatus)
        else str(tool_result.status)
    )
    error = tool_result.error or string_output_value(
        tool_result.output.get("blocked_reason")
    ) or string_output_value(tool_result.output.get("error"))
    if error:
        return f"{tool_result.tool_name} {status}: {error}"
    return f"{tool_result.tool_name} {status}"


def string_output_value(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def combine_model_usage(
    first: ModelUsage | None,
    second: ModelUsage | None,
) -> ModelUsage | None:
    if first is None:
        return second
    if second is None:
        return first
    return ModelUsage(
        provider_id=second.provider_id,
        model_id=second.model_id,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        total_cost=round(first.total_cost + second.total_cost, 8),
        currency=second.currency,
    )


def proposed_memory_candidates(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    agent_result: AgentResult,
) -> list[MemoryItem]:
    proposed_candidates: list[MemoryItem] = []
    seen_content: set[str] = set()
    for candidate in agent_result.memory_candidates:
        content_key = normalized_memory_content(candidate.content)
        if not content_key or content_key in seen_content:
            continue
        seen_content.add(content_key)
        proposed_candidates.append(
            candidate.model_copy(
                update={
                    "scope": f"project:{task.project_id}",
                    "agent_id": world_view.agent_id,
                    "project_id": task.project_id,
                    "status": MemoryStatus.proposed,
                }
            )
        )
    return proposed_candidates


def normalized_memory_content(content: str) -> str:
    return " ".join(content.split()).casefold()


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
        required_tools=draft.required_tools,
        required_tool_scopes=draft.required_tool_scopes,
        acceptance_criteria=draft.acceptance_criteria,
        parent_task_id=parent_task.id,
        sequence=sequence,
    )


def sub_task_draft_with_safe_agent(
    parent_task: TaskRecord,
    world_view: LocalWorldView,
    draft: TaskDraft,
) -> TaskDraft:
    if draft.assigned_agent_id in known_world_view_agent_ids(world_view):
        return draft
    return draft.model_copy(update={"assigned_agent_id": parent_task.assigned_agent_id})


def known_world_view_agent_ids(world_view: LocalWorldView) -> set[str]:
    agent_ids = {
        world_view.agent_id,
        *world_view.peer_agent_ids,
        *world_view.direct_report_agent_ids,
    }
    if world_view.manager_agent_id is not None:
        agent_ids.add(world_view.manager_agent_id)
    return agent_ids


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


def credential_access_request_id(task_id: str, tool_name: str) -> str:
    safe_tool_name = "".join(
        character if character.isalnum() else "_"
        for character in tool_name
    ).strip("_")
    return f"credential_access_{task_id}_{safe_tool_name}"


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


def inactive_agent_skip_reason_from_error(error: StateServiceRequestError) -> str | None:
    if error.status_code != 409:
        return None
    if not str(error.detail).startswith("Agent is not active:"):
        return None
    return "Task assigned agent is inactive."


def task_start_skip_record_from_error(
    task: TaskRecord,
    error: StateServiceRequestError,
) -> TaskSkipRecord:
    inactive_agent_skip_reason = inactive_agent_skip_reason_from_error(error)
    if inactive_agent_skip_reason is not None:
        return TaskSkipRecord(
            task_id=task.id,
            category="inactive_agent",
            reason=inactive_agent_skip_reason,
        )

    detail = str(error.detail)
    if detail.startswith("Task is already "):
        return TaskSkipRecord(
            task_id=task.id,
            category="claim_conflict",
            reason="Task was already claimed by another scheduler.",
        )
    if detail.startswith("Task dependencies are not completed:"):
        return TaskSkipRecord(
            task_id=task.id,
            category="dependency_not_ready",
            reason=detail,
        )
    if detail.startswith("Task retry backoff has not elapsed:"):
        return TaskSkipRecord(
            task_id=task.id,
            category="retry_backoff",
            reason=detail,
        )
    if detail == "Task reached max attempts":
        return TaskSkipRecord(
            task_id=task.id,
            category="max_attempts",
            reason=detail,
        )
    return TaskSkipRecord(
        task_id=task.id,
        category="start_rejected",
        reason=detail,
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
    currency: str,
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
        currency=currency,
    )


def estimated_tokens(*texts: str) -> int:
    return max(1, (sum(len(text) for text in texts) + 3) // 4)


def model_policy_id_from_world_view(world_view: LocalWorldView) -> str | None:
    prefix = "model_policy:"
    for policy in world_view.policies:
        if policy.startswith(prefix):
            return policy.removeprefix(prefix)
    return None


def selected_model_id_for_policy(configured_model_id: str, policy: ModelPolicy) -> str:
    if configured_model_id == LOCAL_RUNTIME_MODEL_ID:
        return policy.default_model_id
    return configured_model_id


def model_route_from_state(
    policy: ModelPolicy,
    model: ModelDefinition,
    provider: ModelProviderConfig,
) -> ModelRoute:
    return ModelRoute(
        provider_id=provider.id,
        model_id=model.id,
        input_cost_per_million_tokens=model.input_cost_per_million_tokens,
        output_cost_per_million_tokens=model.output_cost_per_million_tokens,
        currency=model.currency,
        model_policy_id=policy.id,
    )


def bridge_project_ids_for_run(
    state: StateClient,
    *,
    project_id: str,
) -> list[str]:
    bridge_project_ids: list[str] = []
    for workspace in state.list_project_workspaces(project_id=project_id, active=True):
        bridge_project_ids.extend(workspace.bridge_project_ids)
    return deduplicate(bridge_project_ids)


def memory_scopes_for_run(
    task: TaskRecord,
    world_view: LocalWorldView,
    *,
    bridge_project_ids: list[str] | None = None,
) -> list[str]:
    scopes = [
        "global",
        f"division:{world_view.division}",
        f"agent:{world_view.agent_id}",
        f"project:{task.project_id}",
    ]
    scopes.extend(f"project:{project_id}" for project_id in bridge_project_ids or [])
    return deduplicate(scopes)


def memory_query_text(task: TaskRecord, project: ProjectRecord | None) -> str:
    parts = [task.title, task.description]
    if project is not None:
        parts.extend([project.title, project.goal])
    parts.extend(task.acceptance_criteria)
    return "\n".join(part.strip() for part in parts if part.strip())


def memory_context_without_embeddings(context: MemoryContext) -> MemoryContext:
    return context.model_copy(
        update={
            "query_embedding": None,
            "items": [
                item.model_copy(update={"embedding": None})
                for item in context.items
            ],
        }
    )


def model_call_started_event(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    memory_context: MemoryContext,
    provider_id: str,
    model_id: str,
    model_policy_id: str | None,
    trace_id: str,
    memory_query_embedding_used: bool = False,
    memory_query_embedding_dimensions: int = 0,
) -> EventRecord:
    return EventRecord(
        type=EventType.model_call_started,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "provider_id": provider_id,
            "model_id": model_id,
            "model_policy_id": model_policy_id,
            "purpose": "task.run",
            "memory_item_count": len(memory_context.items),
            "memory_item_ids": [item.id for item in memory_context.items],
            "memory_tokens_used": memory_context.tokens_used,
            "memory_token_budget": memory_context.token_budget,
            "memory_allowed_scopes": memory_context.allowed_scopes,
            "memory_allowed_project_ids": memory_context.allowed_project_ids,
            "memory_max_related_items": memory_context.max_related_items,
            "memory_query_embedding_used": memory_query_embedding_used,
            "memory_query_embedding_dimensions": memory_query_embedding_dimensions,
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
    model_policy_id: str | None,
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
            "model_policy_id": model_policy_id,
            "cost_id": cost_record.id,
            "status": agent_result.status,
            "input_tokens": cost_record.input_tokens,
            "output_tokens": cost_record.output_tokens,
            "total_cost": cost_record.total_cost,
            "currency": cost_record.currency,
            "tool_result_count": len(agent_result.tool_results),
            "failed_tool_result_count": failed_tool_result_count(agent_result),
            "failed_tool_names": failed_tool_result_names(agent_result),
            "failed_tool_errors": failed_tool_result_errors(agent_result),
            "blocked_tool_result_count": blocked_tool_result_count(agent_result),
            "blocked_tool_names": blocked_tool_result_names(agent_result),
            "blocked_tool_errors": blocked_tool_result_errors(agent_result),
            "tool_names": tool_result_names(agent_result),
            "pending_tool_call_count": len(agent_result.tool_calls_requested),
            "pending_tool_names": pending_tool_names(agent_result),
        },
        trace_id=trace_id,
    )


def model_call_failed_event(
    *,
    task: TaskRecord,
    world_view: LocalWorldView,
    provider_id: str,
    model_id: str,
    model_policy_id: str | None,
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
            "model_policy_id": model_policy_id,
            "error": error,
        },
        trace_id=trace_id,
    )


def failed_tool_result_count(agent_result: AgentResult) -> int:
    return sum(
        1
        for tool_result in agent_result.tool_results
        if tool_result.status == TaskStatus.failed
    )


def failed_tool_result_names(agent_result: AgentResult) -> list[str]:
    return deduplicate(
        [
            tool_result.tool_name
            for tool_result in agent_result.tool_results
            if tool_result.status == TaskStatus.failed
        ]
    )


def failed_tool_result_errors(agent_result: AgentResult) -> list[dict[str, str]]:
    return tool_result_errors_by_status(agent_result, TaskStatus.failed)


def blocked_tool_result_count(agent_result: AgentResult) -> int:
    return tool_result_count_by_status(agent_result, TaskStatus.blocked)


def blocked_tool_result_names(agent_result: AgentResult) -> list[str]:
    return tool_result_names_by_status(agent_result, TaskStatus.blocked)


def blocked_tool_result_errors(agent_result: AgentResult) -> list[dict[str, str]]:
    return tool_result_errors_by_status(agent_result, TaskStatus.blocked)


def tool_result_count_by_status(agent_result: AgentResult, status: TaskStatus) -> int:
    return sum(1 for tool_result in agent_result.tool_results if tool_result.status == status)


def tool_result_names_by_status(
    agent_result: AgentResult,
    status: TaskStatus,
) -> list[str]:
    return deduplicate(
        [
            tool_result.tool_name
            for tool_result in agent_result.tool_results
            if tool_result.status == status
        ]
    )


def tool_result_errors_by_status(
    agent_result: AgentResult,
    status: TaskStatus,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tool_result in agent_result.tool_results:
        if tool_result.status != status:
            continue
        error = tool_result.error or ""
        key = (tool_result.tool_name, error)
        if key in seen:
            continue
        seen.add(key)
        errors.append({"tool_name": tool_result.tool_name, "error": error})
    return errors


def tool_result_names(agent_result: AgentResult) -> list[str]:
    return deduplicate(
        [tool_result.tool_name for tool_result in agent_result.tool_results]
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
            "embedding_dimensions": len(memory_item.embedding)
            if memory_item.embedding is not None
            else 0,
        },
        trace_id=trace_id,
    )


def task_run_skipped_event(
    *,
    task: TaskRecord,
    skipped_task: TaskSkipRecord,
    error: StateServiceRequestError,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.task_skipped,
        source_agent_id=task.assigned_agent_id,
        target=task.project_id,
        payload=task_run_skipped_payload(
            task=task,
            skipped_task=skipped_task,
            error=error,
        ),
        trace_id=trace_id,
    )


def task_run_skipped_audit(
    *,
    task: TaskRecord,
    skipped_task: TaskSkipRecord,
    error: StateServiceRequestError,
    trace_id: str,
    headers: dict[str, str],
) -> AuditLogRecord:
    return AuditLogRecord(
        actor_type=headers.get("x-synarch-actor-type", ActorType.service.value),
        actor_id=headers.get("x-synarch-actor-id", "gateway-task-runner"),
        action="task.run_skipped",
        target_type="task",
        target_id=task.id,
        payload=task_run_skipped_payload(
            task=task,
            skipped_task=skipped_task,
            error=error,
        ),
        trace_id=trace_id,
    )


def task_run_skipped_payload(
    *,
    task: TaskRecord,
    skipped_task: TaskSkipRecord,
    error: StateServiceRequestError,
) -> dict[str, object]:
    return {
        "task_id": task.id,
        "project_id": task.project_id,
        "assigned_agent_id": task.assigned_agent_id,
        "status_code": error.status_code,
        "detail": error.detail,
        "category": skipped_task.category,
        "reason": skipped_task.reason,
        "skipped_task_ids": [task.id],
        "skipped_tasks": [skipped_task.model_dump(mode="json")],
        "skipped_task_count": 1,
    }


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
        "skipped_tasks": [
            skipped_task.model_dump(mode="json")
            for skipped_task in batch_result.skipped_tasks
        ],
        "skipped_task_count": len(batch_result.skipped_task_ids),
        "credential_access_request_ids": [
            access_request.id
            for access_request in batch_result.credential_access_requests
        ],
        "credential_access_request_count": len(batch_result.credential_access_requests),
        "credential_resumed_task_ids": batch_result.credential_resumed_task_ids,
        "credential_resumed_task_count": len(batch_result.credential_resumed_task_ids),
        "lease_recovered_task_ids": lease_recovered_task_ids(batch_result.lease_recovery),
        "lease_failed_task_ids": lease_failed_task_ids(batch_result.lease_recovery),
        "created_sub_task_count": sum(
            len(run.created_sub_tasks) for run in batch_result.runs
        ),
        "tool_result_count": sum(len(run.tool_results) for run in batch_result.runs),
        "failed_tool_result_count": sum(
            1
            for run in batch_result.runs
            for tool_result in run.tool_results
            if tool_result.status == TaskStatus.failed
        ),
        "failed_tool_names": deduplicate(
            [
                tool_result.tool_name
                for run in batch_result.runs
                for tool_result in run.tool_results
                if tool_result.status == TaskStatus.failed
            ]
        ),
        "failed_tool_errors": scheduler_failed_tool_errors(batch_result),
        "blocked_tool_result_count": sum(
            1
            for run in batch_result.runs
            for tool_result in run.tool_results
            if tool_result.status == TaskStatus.blocked
        ),
        "blocked_tool_names": deduplicate(
            [
                tool_result.tool_name
                for run in batch_result.runs
                for tool_result in run.tool_results
                if tool_result.status == TaskStatus.blocked
            ]
        ),
        "blocked_tool_errors": scheduler_blocked_tool_errors(batch_result),
        "tool_names": deduplicate(
            [
                tool_result.tool_name
                for run in batch_result.runs
                for tool_result in run.tool_results
            ]
        ),
        "cost_ids": [
            cost_record.id
            for run in batch_result.runs
            for cost_record in run.cost_records
        ],
        "total_cost": round(
            sum(
                cost_record.total_cost
                for run in batch_result.runs
                for cost_record in run.cost_records
            ),
            8,
        ),
    }


def scheduler_failed_tool_errors(
    batch_result: TaskRunBatchResult,
) -> list[dict[str, str]]:
    return scheduler_tool_errors_by_status(batch_result, TaskStatus.failed)


def scheduler_blocked_tool_errors(
    batch_result: TaskRunBatchResult,
) -> list[dict[str, str]]:
    return scheduler_tool_errors_by_status(batch_result, TaskStatus.blocked)


def scheduler_tool_errors_by_status(
    batch_result: TaskRunBatchResult,
    status: TaskStatus,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for run in batch_result.runs:
        for tool_result in run.tool_results:
            if tool_result.status != status:
                continue
            error = tool_result.error or ""
            key = (tool_result.tool_name, error)
            if key in seen:
                continue
            seen.add(key)
            errors.append({"tool_name": tool_result.tool_name, "error": error})
    return errors


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
    original_assigned_agent_id: str | None = None,
) -> EventRecord:
    payload = {
        "task_id": task.id,
        "parent_task_id": parent_task.id,
        "assigned_agent_id": task.assigned_agent_id,
        "depends_on": task.depends_on,
        "acceptance_criteria": task.acceptance_criteria,
        "sequence": task.sequence,
    }
    if original_assigned_agent_id is not None:
        payload["original_assigned_agent_id"] = original_assigned_agent_id
        payload["assignment_fallback_reason"] = "unknown_agent"
    return EventRecord(
        type=EventType.task_created,
        source_agent_id=world_view.agent_id,
        target=task.project_id,
        payload=payload,
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
