import ipaddress
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal, Protocol
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic_settings import BaseSettings

from synarch_models import (
    ActorType,
    AgentProjectAssignment,
    AuditLogRecord,
    CostBudgetEvaluation,
    CostRecord,
    CostSummary,
    CostSummaryGroup,
    EventRecord,
    EventType,
    GoalEnvelope,
    GoalSubmissionResult,
    HealthResponse,
    LocalWorldView,
    MemoryItem,
    MemoryStatus,
    MemoryStatusUpdate,
    ProjectIntent,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectTimeline,
    ProjectWorkspace,
    RoutingDecision,
    TaskDraft,
    TaskRecord,
    TaskReviewDecision,
    TaskReviewResult,
    TaskRunBatchResult,
    TaskRunResult,
    TaskStatus,
    ToolCallRequest,
    ToolResult,
)

from .state_client import (
    HttpStateClient,
    StateClient,
    StateServiceRequestError,
    StateServiceUnavailable,
)
from .task_runner import (
    LOCAL_RUNTIME_INPUT_COST_PER_MILLION,
    LOCAL_RUNTIME_MODEL_ID,
    LOCAL_RUNTIME_OUTPUT_COST_PER_MILLION,
    LOCAL_RUNTIME_PROVIDER_ID,
    ControlPlaneClient,
    HttpAgentRuntimeClient,
    HttpControlPlaneClient,
    HttpMemoryClient,
    MemoryClient,
    NoReadyTask,
    TaskRunner,
    TaskRunnerRequestError,
    TaskRunnerUnavailable,
)

CostSummaryGroupBy = Literal["project", "agent", "model", "provider"]
ToolRiskLevel = Literal["low", "medium", "high"]
ToolCredentialState = Literal["not_required", "ready", "missing_scopes"]


class ToolAdapter(Protocol):
    def __call__(
        self,
        tool_call: ToolCallRequest,
        *,
        state_client: StateClient,
        headers: dict[str, str],
        trace_id: str,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class ToolAdapterManifest:
    tool_name: str
    adapter: str
    required_arguments: tuple[str, ...] = ()
    optional_arguments: tuple[str, ...] = ()
    credential_scopes: tuple[str, ...] = ()
    risk_level: ToolRiskLevel = "low"
    requires_credentials: bool = False
    network_access: bool = False
    audit_required: bool = True

    def as_response(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "adapter": self.adapter,
            "required_arguments": list(self.required_arguments),
            "optional_arguments": list(self.optional_arguments),
            "credential_scopes": list(self.credential_scopes),
            "risk_level": self.risk_level,
            "requires_credentials": self.requires_credentials,
            "network_access": self.network_access,
            "audit_required": self.audit_required,
        }


@dataclass(frozen=True)
class ToolCredentialStatus:
    agent_id: str
    service_id: str
    tool_name: str
    status: ToolCredentialState
    required_scopes: tuple[str, ...] = ()
    available_scopes: tuple[str, ...] = ()
    missing_scopes: tuple[str, ...] = ()

    def as_response(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "service_id": self.service_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "required_scopes": list(self.required_scopes),
            "available_scopes": list(self.available_scopes),
            "missing_scopes": list(self.missing_scopes),
        }


class Settings(BaseSettings):
    control_plane_url: str = "http://localhost:8010"
    state_service_url: str = "http://localhost:8020"
    state_service_timeout_seconds: float = 5.0
    memory_service_url: str = "http://localhost:8030"
    event_service_url: str = "http://localhost:8040"
    agent_runtime_url: str = "http://localhost:8050"
    agent_runtime_timeout_seconds: float = 180.0
    task_runner_memory_token_budget: int = 1200
    task_runner_provider_id: str = LOCAL_RUNTIME_PROVIDER_ID
    task_runner_model_id: str = LOCAL_RUNTIME_MODEL_ID
    task_runner_input_cost_per_million_tokens: float = LOCAL_RUNTIME_INPUT_COST_PER_MILLION
    task_runner_output_cost_per_million_tokens: float = LOCAL_RUNTIME_OUTPUT_COST_PER_MILLION
    web_fetch_timeout_seconds: float = 10.0
    web_fetch_max_bytes: int = 50_000
    web_fetch_max_redirects: int = 5


settings = Settings()
app = FastAPI(title="Synarch Gateway", version="0.1.0")


def choose_agent(goal: str) -> tuple[str, str]:
    normalized = goal.casefold()
    if any(keyword in normalized for keyword in ["facture", "finance", "compta", "tva"]):
        return "agent-finance", "Finance keywords detected."
    if any(keyword in normalized for keyword in ["code", "bug", "api", "infra", "dev"]):
        return "agent-dev", "Technical delivery keywords detected."
    if any(keyword in normalized for keyword in ["fournisseur", "rfq", "usine", "sourcing"]):
        return "agent-ops-sourcing", "Ops and sourcing keywords detected."
    if any(keyword in normalized for keyword in ["doc", "mail", "procedure", "knowledge"]):
        return "agent-admin-knowledge", "Knowledge management keywords detected."
    return "agent-direction", "No specialist route detected; Direction keeps ownership."


def get_state_client() -> StateClient:
    return HttpStateClient(
        settings.state_service_url,
        timeout_seconds=settings.state_service_timeout_seconds,
    )


def get_task_runner() -> TaskRunner:
    return TaskRunner(
        state=get_state_client(),
        control_plane=HttpControlPlaneClient(
            settings.control_plane_url,
            timeout_seconds=settings.state_service_timeout_seconds,
        ),
        memory=HttpMemoryClient(
            settings.memory_service_url,
            timeout_seconds=settings.state_service_timeout_seconds,
        ),
        runtime=HttpAgentRuntimeClient(
            settings.agent_runtime_url,
            timeout_seconds=settings.agent_runtime_timeout_seconds,
        ),
        memory_token_budget=settings.task_runner_memory_token_budget,
        provider_id=settings.task_runner_provider_id,
        model_id=settings.task_runner_model_id,
        input_cost_per_million_tokens=settings.task_runner_input_cost_per_million_tokens,
        output_cost_per_million_tokens=settings.task_runner_output_cost_per_million_tokens,
        tool_runner=GatewayToolRunner(),
    )


def get_control_plane_client() -> ControlPlaneClient:
    return HttpControlPlaneClient(
        settings.control_plane_url,
        timeout_seconds=settings.state_service_timeout_seconds,
    )


def get_memory_client() -> MemoryClient:
    return HttpMemoryClient(
        settings.memory_service_url,
        timeout_seconds=settings.state_service_timeout_seconds,
    )


def plan_goal(envelope: GoalEnvelope) -> RoutingDecision:
    agent_id, rationale = choose_agent(envelope.goal)
    project_intent = ProjectIntent(
        title=envelope.goal[:80],
        goal=envelope.goal,
        priority=envelope.priority,
        owner_agent_id="agent-direction",
    )
    task_drafts = [
        TaskDraft(
            title="Clarify success criteria",
            description="Turn the raw objective into explicit success criteria and constraints.",
            assigned_agent_id="agent-direction",
            priority=envelope.priority,
            acceptance_criteria=[
                "The original goal is restated in operational terms.",
                "Unknowns, constraints, and stop conditions are listed.",
            ],
            sequence=1,
        ),
        TaskDraft(
            title="Prepare specialist action plan",
            description=f"Plan the first scoped work package for: {envelope.goal[:80]}",
            assigned_agent_id=agent_id,
            depends_on=["Clarify success criteria"],
            priority=envelope.priority,
            acceptance_criteria=[
                "The specialist scope is small enough to execute and debug independently.",
                "Expected inputs, outputs, tools, and blockers are identified.",
            ],
            sequence=2,
        ),
        TaskDraft(
            title=f"Execute first scoped work package: {envelope.goal[:50]}",
            description="Execute only the first validated unit of work, not the full project.",
            assigned_agent_id=agent_id,
            depends_on=["Prepare specialist action plan"],
            priority=envelope.priority,
            acceptance_criteria=[
                "One concrete work package is completed or explicitly blocked.",
                "Produced facts, artifacts, costs, and blockers are recorded.",
            ],
            sequence=3,
        ),
        TaskDraft(
            title="Review outcome and next split",
            description="Review the completed unit and decide the next smallest actionable slice.",
            assigned_agent_id="agent-direction",
            depends_on=[f"Execute first scoped work package: {envelope.goal[:50]}"],
            priority=envelope.priority,
            acceptance_criteria=[
                "The previous unit is accepted, rejected, or marked blocked with a reason.",
                "The next task or project split decision is explicit.",
            ],
            sequence=4,
        ),
    ]
    return RoutingDecision(
        project_intent=project_intent,
        task_drafts=task_drafts,
        target_agents=sorted({"agent-direction", agent_id}),
        rationale=rationale,
    )


def audit_headers(envelope: GoalEnvelope, trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.user.value,
        "x-synarch-actor-id": envelope.requester,
        "x-synarch-trace-id": trace_id,
    }


def service_headers(trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.service.value,
        "x-synarch-actor-id": "gateway-task-runner",
        "x-synarch-trace-id": trace_id,
    }


def goal_submission_service_headers(trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.service.value,
        "x-synarch-actor-id": "gateway-goal-submitter",
        "x-synarch-trace-id": trace_id,
    }


def project_split_applier_headers(trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.service.value,
        "x-synarch-actor-id": "gateway-project-split-applier",
        "x-synarch-trace-id": trace_id,
    }


def tool_gate_headers(trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.service.value,
        "x-synarch-actor-id": "gateway-tool-gate",
        "x-synarch-trace-id": trace_id,
    }


def memory_reviewer_headers(request: Request, trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": request.headers.get(
            "x-synarch-actor-type", ActorType.user.value
        ),
        "x-synarch-actor-id": request.headers.get("x-synarch-actor-id", "local-user"),
        "x-synarch-trace-id": trace_id,
    }


def task_reviewer_headers(request: Request, trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": request.headers.get(
            "x-synarch-actor-type", ActorType.user.value
        ),
        "x-synarch-actor-id": request.headers.get("x-synarch-actor-id", "local-user"),
        "x-synarch-trace-id": trace_id,
    }


def persist_goal_submission(
    envelope: GoalEnvelope,
    routing_decision: RoutingDecision,
    trace_id: str,
    state_client: StateClient,
) -> GoalSubmissionResult:
    headers = audit_headers(envelope, trace_id)
    project = state_client.create_project(
        ProjectRecord(
            title=routing_decision.project_intent.title,
            goal=routing_decision.project_intent.goal,
            priority=routing_decision.project_intent.priority,
            owner_agent_id=routing_decision.project_intent.owner_agent_id,
        ),
        headers=headers,
    )
    workspace = state_client.create_project_workspace(
        ProjectWorkspace(
            project_id=project.id,
            name=project.title,
            summary=project.goal,
            memory_scope=f"project:{project.id}",
            allowed_agent_ids=routing_decision.target_agents,
        ),
        headers=headers,
    )
    assignments = [
        state_client.create_agent_project_assignment(
            AgentProjectAssignment(
                project_id=project.id,
                workspace_id=workspace.id,
                agent_id=agent_id,
                assignment_role="owner" if agent_id == project.owner_agent_id else "contributor",
            ),
            headers=headers,
        )
        for agent_id in routing_decision.target_agents
    ]

    tasks: list[TaskRecord] = []
    task_ids_by_draft_title: dict[str, str] = {}
    for draft in routing_decision.task_drafts:
        task = state_client.create_task(
            TaskRecord(
                project_id=project.id,
                title=draft.title,
                description=draft.description,
                assigned_agent_id=draft.assigned_agent_id,
                depends_on=[
                    task_ids_by_draft_title.get(dependency, dependency)
                    for dependency in draft.depends_on
                ],
                acceptance_criteria=draft.acceptance_criteria,
                sequence=draft.sequence,
            ),
            headers=headers,
        )
        tasks.append(task)
        task_ids_by_draft_title[draft.title] = task.id

    events = [
        state_client.create_event(event, headers=headers)
        for event in goal_submission_events(envelope, routing_decision, project, tasks, trace_id)
    ]
    complexity_assessment = state_client.assess_project_complexity(
        project.id,
        headers=goal_submission_service_headers(trace_id),
    )

    return GoalSubmissionResult(
        trace_id=trace_id,
        routing_decision=routing_decision,
        project=project,
        workspace=workspace,
        assignments=assignments,
        tasks=tasks,
        events=events,
        complexity_assessment=complexity_assessment,
    )


def goal_submission_events(
    envelope: GoalEnvelope,
    routing_decision: RoutingDecision,
    project: ProjectRecord,
    tasks: list[TaskRecord],
    trace_id: str,
) -> list[EventRecord]:
    return [
        EventRecord(
            type=EventType.goal_received,
            target=project.id,
            payload={
                "goal": envelope.goal,
                "priority": envelope.priority,
                "requester": envelope.requester,
                "constraints": envelope.constraints,
            },
            trace_id=trace_id,
        ),
        EventRecord(
            type=EventType.routing_decided,
            target=project.id,
            payload={
                "target_agents": routing_decision.target_agents,
                "rationale": routing_decision.rationale,
            },
            trace_id=trace_id,
        ),
        EventRecord(
            type=EventType.project_created,
            target=project.id,
            payload={"project_id": project.id, "title": project.title},
            trace_id=trace_id,
        ),
        *[
            EventRecord(
                type=EventType.task_created,
                target=project.id,
                payload={
                    "task_id": task.id,
                    "assigned_agent_id": task.assigned_agent_id,
                    "depends_on": task.depends_on,
                    "acceptance_criteria": task.acceptance_criteria,
                    "sequence": task.sequence,
                },
                trace_id=trace_id,
            )
            for task in tasks
        ],
    ]


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="gateway")


@app.get("/")
def read_root() -> dict[str, object]:
    return {
        "name": "Synarch Gateway",
        "services": {
            "control_plane": settings.control_plane_url,
            "state": settings.state_service_url,
            "memory": settings.memory_service_url,
            "events": settings.event_service_url,
            "agent_runtime": settings.agent_runtime_url,
        },
    }


@app.post("/goals", response_model=RoutingDecision)
def submit_goal(envelope: GoalEnvelope) -> RoutingDecision:
    return plan_goal(envelope)


@app.post("/goals/submit", response_model=GoalSubmissionResult, status_code=201)
def submit_goal_to_state(
    envelope: GoalEnvelope,
    state_client: StateClient = Depends(get_state_client),
) -> GoalSubmissionResult:
    trace_id = f"trace_{uuid4().hex[:12]}"
    routing_decision = plan_goal(envelope)
    try:
        return persist_goal_submission(envelope, routing_decision, trace_id, state_client)
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post(
    "/project-split-requests/{split_request_id}/apply",
    response_model=ProjectSplitApplication,
    status_code=201,
)
def apply_project_split_request(
    split_request_id: str,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> ProjectSplitApplication:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    try:
        return state_client.apply_project_split(
            split_request_id,
            headers=project_split_applier_headers(trace_id),
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post("/tasks/run-next", response_model=TaskRunResult)
def run_next_task(
    request: Request,
    runner: TaskRunner = Depends(get_task_runner),
) -> TaskRunResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    try:
        return runner.run_next(trace_id=trace_id, headers=service_headers(trace_id))
    except NoReadyTask as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(status_code=502, detail="Task runner dependency unavailable") from error


@app.post("/tasks/{task_id}/run", response_model=TaskRunResult)
def run_task_by_id(
    task_id: str,
    request: Request,
    runner: TaskRunner = Depends(get_task_runner),
) -> TaskRunResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    try:
        return runner.run_task(task_id, trace_id=trace_id, headers=service_headers(trace_id))
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(status_code=502, detail="Task runner dependency unavailable") from error


@app.post("/tasks/run-ready", response_model=TaskRunBatchResult)
def run_ready_tasks(
    request: Request,
    max_tasks: int = Query(default=3, ge=1, le=20),
    project_id: str | None = None,
    runner: TaskRunner = Depends(get_task_runner),
) -> TaskRunBatchResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    try:
        return runner.run_ready(
            max_tasks=max_tasks,
            trace_id=trace_id,
            headers=service_headers(trace_id),
            project_id=project_id,
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(status_code=502, detail="Task runner dependency unavailable") from error


@app.get("/tasks/review-queue", response_model=list[TaskRecord])
def list_task_review_queue(
    project_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[TaskRecord]:
    try:
        return state_client.list_task_review_queue(project_id=project_id)
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post("/tasks/{task_id}/review-decisions", response_model=TaskReviewResult)
def apply_task_review_decision(
    task_id: str,
    decision: TaskReviewDecision,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> TaskReviewResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    try:
        return state_client.apply_task_review_decision(
            task_id,
            decision,
            headers=task_reviewer_headers(request, trace_id),
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post("/tools/call", response_model=ToolResult)
def call_tool(
    tool_call: ToolCallRequest,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
    control_plane: ControlPlaneClient = Depends(get_control_plane_client),
) -> ToolResult:
    trace_id = tool_call.trace_id or request.headers.get(
        "x-synarch-trace-id",
        f"trace_{uuid4().hex[:12]}",
    )
    headers = tool_gate_headers(trace_id)
    try:
        return execute_tool_call_through_gate(
            tool_call,
            state_client=state_client,
            control_plane=control_plane,
            headers=headers,
            trace_id=trace_id,
            raise_on_failure=True,
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(status_code=502, detail="Tool gate dependency unavailable") from error


@app.get("/tools/registry")
def list_tool_registry() -> dict[str, object]:
    return {"tools": registered_tool_manifests()}


@app.get("/tools/credential-status")
def list_tool_credential_status(
    agent_id: str,
    control_plane: ControlPlaneClient = Depends(get_control_plane_client),
) -> dict[str, object]:
    try:
        world_view = control_plane.get_world_view(agent_id)
    except TaskRunnerRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except TaskRunnerUnavailable as error:
        raise HTTPException(status_code=502, detail="Control plane unavailable") from error
    return {
        "agent_id": agent_id,
        "credential_statuses": [
            status.as_response()
            for status in tool_credential_statuses_for_world_view(world_view)
        ],
    }


class GatewayToolRunner:
    def call_tool(
        self,
        tool_call: ToolCallRequest,
        *,
        state_client: StateClient,
        control_plane: ControlPlaneClient,
        headers: dict[str, str],
        trace_id: str,
    ) -> ToolResult:
        return execute_tool_call_through_gate(
            tool_call,
            state_client=state_client,
            control_plane=control_plane,
            headers=headers,
            trace_id=trace_id,
            raise_on_failure=False,
        )


def execute_tool_call_through_gate(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    control_plane: ControlPlaneClient,
    headers: dict[str, str],
    trace_id: str,
    raise_on_failure: bool,
) -> ToolResult:
    world_view = control_plane.get_world_view(tool_call.agent_id)
    error = tool_access_error(tool_call, world_view)
    if error is not None:
        state_client.create_event(
            tool_call_event(tool_call, EventType.tool_failed, trace_id, error=error),
            headers=headers,
        )
        state_client.create_audit_log(
            tool_call_audit(tool_call, "tool.denied", trace_id, error=error),
            headers=headers,
        )
        if raise_on_failure:
            raise HTTPException(status_code=403, detail=error)
        return ToolResult(
            tool_name=tool_call.tool_name,
            status=TaskStatus.failed,
            output={
                "authorized": False,
                "trace_id": trace_id,
                "service_id": tool_call.service_id,
            },
            error=error,
        )

    event = state_client.create_event(
        tool_call_event(tool_call, EventType.tool_called, trace_id),
        headers=headers,
    )
    audit = state_client.create_audit_log(
        tool_call_audit(tool_call, "tool.allowed", trace_id),
        headers=headers,
    )
    try:
        execution_output = execute_authorized_tool(
            tool_call,
            state_client=state_client,
            headers=headers,
            trace_id=trace_id,
        )
    except HTTPException as error:
        detail = str(getattr(error, "detail", error))
        state_client.create_event(
            tool_call_event(tool_call, EventType.tool_failed, trace_id, error=detail),
            headers=headers,
        )
        state_client.create_audit_log(
            tool_call_audit(tool_call, "tool.failed", trace_id, error=detail),
            headers=headers,
        )
        if raise_on_failure:
            raise
        return ToolResult(
            tool_name=tool_call.tool_name,
            status=TaskStatus.failed,
            output={
                "authorized": True,
                "trace_id": trace_id,
                "event_id": event.id,
                "audit_id": audit.id,
                "service_id": tool_call.service_id,
            },
            error=detail,
        )

    return ToolResult(
        tool_name=tool_call.tool_name,
        output={
            "authorized": True,
            "trace_id": trace_id,
            "event_id": event.id,
            "audit_id": audit.id,
            "service_id": tool_call.service_id,
            **execution_output,
        },
    )


def tool_access_error(tool_call: ToolCallRequest, world_view: LocalWorldView) -> str | None:
    if tool_call.tool_name in world_view.permissions.denied_tools:
        return f"Tool denied for agent: {tool_call.tool_name}"
    if tool_call.tool_name not in world_view.permissions.allowed_tools:
        return f"Tool not allowed for agent: {tool_call.tool_name}"
    if (
        tool_call.service_id is not None
        and tool_call.service_id not in world_view.available_services
    ):
        return f"Service not available for agent: {tool_call.service_id}"
    if tool_call.service_id is not None:
        service_capabilities = world_view.available_service_capabilities.get(
            tool_call.service_id
        )
        if service_capabilities is None:
            return f"Service capabilities unavailable for agent: {tool_call.service_id}"
        if tool_call.tool_name not in service_capabilities:
            return (
                f"Tool not exposed by service: {tool_call.tool_name} "
                f"via {tool_call.service_id}"
            )
    credential_error = tool_credential_scope_error(tool_call, world_view)
    if credential_error is not None:
        return credential_error
    return None


def tool_credential_scope_error(
    tool_call: ToolCallRequest,
    world_view: LocalWorldView,
) -> str | None:
    if tool_call.service_id is None:
        return None
    manifest = TOOL_ADAPTER_MANIFESTS.get(tool_call.tool_name)
    if manifest is None or not manifest.credential_scopes:
        return None
    service_scopes = world_view.available_service_credential_scopes.get(
        tool_call.service_id, []
    )
    missing_scopes = [
        scope for scope in manifest.credential_scopes if scope not in service_scopes
    ]
    if not missing_scopes:
        return None
    return (
        f"Missing credential scopes for service {tool_call.service_id}: "
        f"{', '.join(missing_scopes)}"
    )


def tool_credential_statuses_for_world_view(
    world_view: LocalWorldView,
) -> list[ToolCredentialStatus]:
    statuses: list[ToolCredentialStatus] = []
    available_services = set(world_view.available_services)
    for service_id in sorted(world_view.available_service_capabilities):
        if service_id not in available_services:
            continue
        service_tools = world_view.available_service_capabilities[service_id]
        available_scopes = tuple(
            world_view.available_service_credential_scopes.get(service_id, [])
        )
        for tool_name in sorted(service_tools):
            manifest = TOOL_ADAPTER_MANIFESTS.get(tool_name)
            if manifest is None:
                continue
            required_scopes = manifest.credential_scopes
            missing_scopes = tuple(
                scope for scope in required_scopes if scope not in available_scopes
            )
            if not required_scopes:
                state: ToolCredentialState = "not_required"
            elif missing_scopes:
                state = "missing_scopes"
            else:
                state = "ready"
            statuses.append(
                ToolCredentialStatus(
                    agent_id=world_view.agent_id,
                    service_id=service_id,
                    tool_name=tool_name,
                    status=state,
                    required_scopes=required_scopes,
                    available_scopes=available_scopes,
                    missing_scopes=missing_scopes,
                )
            )
    return statuses


def execute_authorized_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    adapter = TOOL_ADAPTERS.get(tool_call.tool_name)
    if adapter is None:
        return {"executed": False, "adapter": None}
    return adapter(
        tool_call,
        state_client=state_client,
        headers=headers,
        trace_id=trace_id,
    )


def registered_tool_names() -> list[str]:
    return sorted(TOOL_ADAPTERS)


def registered_tool_manifests() -> list[dict[str, object]]:
    return [
        TOOL_ADAPTER_MANIFESTS[tool_name].as_response()
        for tool_name in sorted(TOOL_ADAPTER_MANIFESTS)
    ]


def tool_adapter_registry_errors() -> list[str]:
    adapter_names = set(TOOL_ADAPTERS)
    manifest_names = set(TOOL_ADAPTER_MANIFESTS)
    errors: list[str] = []
    for tool_name in sorted(adapter_names - manifest_names):
        errors.append(f"Missing manifest for adapter: {tool_name}")
    for tool_name in sorted(manifest_names - adapter_names):
        errors.append(f"Manifest without adapter: {tool_name}")
    for tool_name, manifest in TOOL_ADAPTER_MANIFESTS.items():
        if manifest.tool_name != tool_name:
            errors.append(f"Manifest key mismatch: {tool_name}")
    return errors


def execute_event_emit_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_event_emit_tool(
        tool_call,
        state_client=state_client,
        headers=headers,
        trace_id=trace_id,
    )


def execute_web_fetch_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_web_fetch_tool(tool_call)


class HtmlSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.ignored_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
        if tag in {"script", "style", "noscript"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in {"script", "style", "noscript"} and self.ignored_depth > 0:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
            return
        if self.ignored_depth == 0:
            self.text_parts.append(text)


def execute_web_fetch_tool(tool_call: ToolCallRequest) -> dict[str, object]:
    url = web_fetch_url_argument(tool_call)
    max_bytes = web_fetch_max_bytes_argument(tool_call)
    fetch_result = fetch_http_url(url, max_bytes=max_bytes)
    return {
        "executed": True,
        "adapter": "web.fetch",
        **fetch_result,
    }


def web_fetch_url_argument(tool_call: ToolCallRequest) -> str:
    raw_url = tool_call.arguments.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise HTTPException(status_code=400, detail="web.fetch requires string argument: url")

    return validate_public_http_url(raw_url)


def validate_public_http_url(url: str) -> str:
    normalized_url = url.strip()
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise HTTPException(status_code=400, detail="web.fetch only supports HTTP(S) URLs")
    ensure_public_http_host(parsed.hostname)
    return normalized_url


def web_fetch_max_bytes_argument(tool_call: ToolCallRequest) -> int:
    raw_max_bytes = tool_call.arguments.get("max_bytes", 12_000)
    if isinstance(raw_max_bytes, bool) or not isinstance(raw_max_bytes, int):
        raise HTTPException(status_code=400, detail="web.fetch max_bytes must be an integer")
    if raw_max_bytes < 1 or raw_max_bytes > settings.web_fetch_max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"web.fetch max_bytes must be between 1 and {settings.web_fetch_max_bytes}",
        )
    return int(raw_max_bytes)


def ensure_public_http_host(hostname: str) -> None:
    normalized = hostname.casefold()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".local"):
        raise HTTPException(status_code=400, detail="web.fetch cannot target local hosts")

    try:
        addresses = socket.getaddrinfo(normalized, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise HTTPException(
            status_code=400,
            detail=f"web.fetch cannot resolve host: {hostname}",
        ) from error

    for address in addresses:
        ip_address = ipaddress.ip_address(address[4][0])
        if (
            ip_address.is_private
            or ip_address.is_loopback
            or ip_address.is_link_local
            or ip_address.is_multicast
            or ip_address.is_reserved
            or ip_address.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="web.fetch cannot target private hosts")


def fetch_http_url(url: str, *, max_bytes: int) -> dict[str, object]:
    try:
        with httpx.Client(
            timeout=settings.web_fetch_timeout_seconds,
            headers={"User-Agent": "Synarch/0.1 web.fetch"},
        ) as client:
            response = fetch_http_response(client, url)
            content, truncated = read_response_content(response, max_bytes=max_bytes)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="web.fetch request failed") from error

    content_type = response.headers.get("content-type", "")
    encoding = response.encoding or "utf-8"
    text = content.decode(encoding, errors="replace")
    title, excerpt = summarize_fetched_text(text)
    return {
        "url": url,
        "final_url": str(response.url),
        "status_code": response.status_code,
        "content_type": content_type,
        "bytes_read": len(content),
        "truncated": truncated,
        "title": title,
        "text_excerpt": excerpt,
    }


def fetch_http_response(client: httpx.Client, url: str) -> httpx.Response:
    current_url = url
    for _ in range(settings.web_fetch_max_redirects + 1):
        request = client.build_request("GET", current_url)
        streamed_response = client.send(request, stream=True, follow_redirects=False)
        if not streamed_response.is_redirect:
            return streamed_response

        location = streamed_response.headers.get("location")
        if not location:
            return streamed_response
        streamed_response.close()
        current_url = validate_public_http_url(urljoin(current_url, location))

    raise HTTPException(status_code=502, detail="web.fetch exceeded redirect limit")


def read_response_content(response: httpx.Response, *, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    bytes_read = 0
    truncated = False
    try:
        for chunk in response.iter_bytes():
            remaining = max_bytes - bytes_read
            if remaining <= 0:
                truncated = True
                break
            if len(chunk) > remaining:
                chunks.append(chunk[:remaining])
                bytes_read += remaining
                truncated = True
                break
            chunks.append(chunk)
            bytes_read += len(chunk)
    finally:
        response.close()
    return b"".join(chunks), truncated


def summarize_fetched_text(text: str) -> tuple[str | None, str]:
    parser = HtmlSummaryParser()
    parser.feed(text)
    title = collapse_whitespace(" ".join(parser.title_parts)) or None
    body_text = " ".join(parser.text_parts) if parser.text_parts else text
    return title, collapse_whitespace(body_text)[:1200]


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def execute_event_emit_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    event_type = event_type_argument(tool_call)
    payload = payload_argument(tool_call)
    target = string_argument(tool_call, "target") or tool_call.task_id or tool_call.project_id
    emitted_event = state_client.create_event(
        EventRecord(
            type=event_type,
            source_agent_id=tool_call.agent_id,
            target=target,
            payload=payload,
            trace_id=trace_id,
        ),
        headers=headers,
    )
    return {
        "executed": True,
        "adapter": "event.emit",
        "emitted_event_id": emitted_event.id,
        "emitted_event_type": emitted_event.type,
    }


TOOL_ADAPTERS: dict[str, ToolAdapter] = {
    "event.emit": execute_event_emit_adapter,
    "web.fetch": execute_web_fetch_adapter,
}

TOOL_ADAPTER_MANIFESTS: dict[str, ToolAdapterManifest] = {
    "event.emit": ToolAdapterManifest(
        tool_name="event.emit",
        adapter="event.emit",
        required_arguments=("type",),
        optional_arguments=("target", "payload"),
        risk_level="low",
    ),
    "web.fetch": ToolAdapterManifest(
        tool_name="web.fetch",
        adapter="web.fetch",
        required_arguments=("url",),
        optional_arguments=("max_bytes",),
        risk_level="medium",
        network_access=True,
    ),
}


def event_type_argument(tool_call: ToolCallRequest) -> EventType:
    raw_event_type = tool_call.arguments.get("type")
    if not isinstance(raw_event_type, str):
        raise HTTPException(status_code=400, detail="event.emit requires string argument: type")
    try:
        return EventType(raw_event_type)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event type for event.emit: {raw_event_type}",
        ) from error


def payload_argument(tool_call: ToolCallRequest) -> dict[str, object]:
    raw_payload = tool_call.arguments.get("payload", {})
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=400, detail="event.emit payload must be an object")
    return raw_payload


def string_argument(tool_call: ToolCallRequest, key: str) -> str | None:
    raw_value = tool_call.arguments.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise HTTPException(status_code=400, detail=f"event.emit {key} must be a string")
    return raw_value


def tool_call_event(
    tool_call: ToolCallRequest,
    event_type: EventType,
    trace_id: str,
    *,
    error: str | None = None,
) -> EventRecord:
    payload = tool_call_payload(tool_call)
    if error is not None:
        payload["error"] = error
    return EventRecord(
        type=event_type,
        source_agent_id=tool_call.agent_id,
        target=tool_call.task_id or tool_call.project_id or tool_call.tool_name,
        payload=payload,
        trace_id=trace_id,
    )


def tool_call_audit(
    tool_call: ToolCallRequest,
    action: str,
    trace_id: str,
    *,
    error: str | None = None,
) -> AuditLogRecord:
    payload = tool_call_payload(tool_call)
    if error is not None:
        payload["error"] = error
    return AuditLogRecord(
        actor_type=ActorType.agent,
        actor_id=tool_call.agent_id,
        action=action,
        target_type="tool",
        target_id=tool_call.tool_name,
        payload=payload,
        trace_id=trace_id,
    )


def tool_call_payload(tool_call: ToolCallRequest) -> dict[str, object]:
    return {
        "agent_id": tool_call.agent_id,
        "tool_name": tool_call.tool_name,
        "service_id": tool_call.service_id,
        "project_id": tool_call.project_id,
        "task_id": tool_call.task_id,
        "reason": tool_call.reason,
        "argument_keys": sorted(tool_call.arguments.keys()),
    }


@app.get("/memory-items", response_model=list[MemoryItem])
def list_memory_items(
    scope: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    status: MemoryStatus | None = None,
    memory_client: MemoryClient = Depends(get_memory_client),
) -> list[MemoryItem]:
    try:
        return memory_client.list_memory_items(
            scope=scope,
            agent_id=agent_id,
            project_id=project_id,
            status=status,
        )
    except TaskRunnerRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except TaskRunnerUnavailable as error:
        raise HTTPException(status_code=502, detail="Memory service unavailable") from error


@app.get("/events", response_model=list[EventRecord])
def list_events(
    event_type: EventType | None = None,
    trace_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[EventRecord]:
    try:
        return state_client.list_events(
            event_type=event_type.value if event_type is not None else None,
            trace_id=trace_id,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.get("/cost-records", response_model=list[CostRecord])
def list_cost_records(
    project_id: str | None = None,
    agent_id: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    trace_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[CostRecord]:
    try:
        return state_client.list_cost_records(
            project_id=project_id,
            agent_id=agent_id,
            provider_id=provider_id,
            model_id=model_id,
            trace_id=trace_id,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.get("/cost-records/summary", response_model=CostSummary)
def summarize_cost_records(
    group_by: CostSummaryGroupBy = "project",
    project_id: str | None = None,
    agent_id: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    trace_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> CostSummary:
    try:
        cost_records = state_client.list_cost_records(
            project_id=project_id,
            agent_id=agent_id,
            provider_id=provider_id,
            model_id=model_id,
            trace_id=trace_id,
        )
        return build_cost_summary(cost_records, group_by)
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


def build_cost_summary(
    cost_records: list[CostRecord],
    group_by: CostSummaryGroupBy,
) -> CostSummary:
    groups_by_key: dict[str, list[CostRecord]] = {}
    for cost in cost_records:
        group_key = cost_summary_group_key(cost, group_by)
        groups_by_key.setdefault(group_key, []).append(cost)

    groups = [
        CostSummaryGroup(
            group_key=group_key,
            record_count=len(group_costs),
            input_tokens=sum(cost.input_tokens for cost in group_costs),
            output_tokens=sum(cost.output_tokens for cost in group_costs),
            total_cost=sum(cost.total_cost for cost in group_costs),
            currency=cost_summary_currency(group_costs),
        )
        for group_key, group_costs in sorted(groups_by_key.items())
    ]
    return CostSummary(
        group_by=group_by,
        groups=groups,
        record_count=len(cost_records),
        input_tokens=sum(cost.input_tokens for cost in cost_records),
        output_tokens=sum(cost.output_tokens for cost in cost_records),
        total_cost=sum(cost.total_cost for cost in cost_records),
        currency=cost_summary_currency(cost_records),
    )


def cost_summary_group_key(cost: CostRecord, group_by: CostSummaryGroupBy) -> str:
    match group_by:
        case "project":
            return cost.project_id or "unassigned"
        case "agent":
            return cost.agent_id or "unassigned"
        case "model":
            return cost.model_id
        case "provider":
            return cost.provider_id


def cost_summary_currency(cost_records: list[CostRecord]) -> str:
    currencies = {cost.currency for cost in cost_records}
    if not currencies:
        return "USD"
    if len(currencies) == 1:
        return next(iter(currencies))
    return "mixed"


@app.get("/cost-records/budget", response_model=CostBudgetEvaluation)
def evaluate_cost_budget(
    budget: float,
    project_id: str | None = None,
    agent_id: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    trace_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> CostBudgetEvaluation:
    if budget < 0:
        raise HTTPException(status_code=400, detail="Budget must be greater than or equal to 0")
    try:
        cost_records = state_client.list_cost_records(
            project_id=project_id,
            agent_id=agent_id,
            provider_id=provider_id,
            model_id=model_id,
            trace_id=trace_id,
        )
        return build_cost_budget_evaluation(cost_records, budget)
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


def build_cost_budget_evaluation(
    cost_records: list[CostRecord],
    budget: float,
) -> CostBudgetEvaluation:
    spent = round(sum(cost.total_cost for cost in cost_records), 12)
    remaining = round(budget - spent, 12)
    usage_ratio = round(spent / budget, 12) if budget > 0 else 0.0
    return CostBudgetEvaluation(
        budget=budget,
        spent=spent,
        remaining=remaining,
        usage_ratio=usage_ratio,
        budget_exceeded=spent > budget,
        record_count=len(cost_records),
        input_tokens=sum(cost.input_tokens for cost in cost_records),
        output_tokens=sum(cost.output_tokens for cost in cost_records),
        currency=cost_summary_currency(cost_records),
    )


@app.get("/audit-logs", response_model=list[AuditLogRecord])
def list_audit_logs(
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    trace_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[AuditLogRecord]:
    try:
        return state_client.list_audit_logs(
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            trace_id=trace_id,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.get("/projects/{project_id}/timeline", response_model=ProjectTimeline)
def get_project_timeline(
    project_id: str,
    state_client: StateClient = Depends(get_state_client),
    memory_client: MemoryClient = Depends(get_memory_client),
) -> ProjectTimeline:
    try:
        project = state_client.get_project(project_id)
        tasks = state_client.list_tasks(project_id=project_id)
        task_ids = {task.id for task in tasks}
        events = [
            event
            for event in state_client.list_events()
            if event_belongs_to_project(event, project_id, task_ids)
        ]
        cost_records = state_client.list_cost_records(project_id=project_id)
        trace_ids = {event.trace_id for event in events if event.trace_id is not None}
        trace_ids.update(
            cost.trace_id for cost in cost_records if cost.trace_id is not None
        )
        audit_logs = [
            audit
            for audit in state_client.list_audit_logs()
            if audit_belongs_to_project(audit, project_id, task_ids, trace_ids)
        ]
        memory_items = memory_client.list_memory_items(project_id=project_id)
        return ProjectTimeline(
            project_id=project_id,
            project=project,
            tasks=tasks,
            events=events,
            cost_records=cost_records,
            audit_logs=audit_logs,
            memory_items=memory_items,
            total_cost=sum(cost.total_cost for cost in cost_records),
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Project timeline dependency unavailable",
        ) from error


def event_belongs_to_project(
    event: EventRecord,
    project_id: str,
    task_ids: set[str],
) -> bool:
    return (
        event.target == project_id
        or event.target in task_ids
        or event.payload.get("project_id") == project_id
        or event.payload.get("task_id") in task_ids
    )


def audit_belongs_to_project(
    audit: AuditLogRecord,
    project_id: str,
    task_ids: set[str],
    trace_ids: set[str],
) -> bool:
    return (
        audit.target_id == project_id
        or audit.target_id in task_ids
        or audit.payload.get("project_id") == project_id
        or audit.trace_id in trace_ids
    )


@app.patch("/memory-items/{item_id}/status", response_model=MemoryItem)
def update_memory_item_status(
    item_id: str,
    update: MemoryStatusUpdate,
    request: Request,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
) -> MemoryItem:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = memory_reviewer_headers(request, trace_id)
    try:
        memory_item = memory_client.update_memory_status(item_id, update)
        state_client.create_event(
            memory_status_updated_event(memory_item, trace_id),
            headers=headers,
        )
        return memory_item
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory review dependency unavailable",
        ) from error


def memory_status_updated_event(memory_item: MemoryItem, trace_id: str) -> EventRecord:
    return EventRecord(
        type=EventType.memory_status_updated,
        target=memory_item.project_id or memory_item.scope,
        payload={
            "memory_id": memory_item.id,
            "scope": memory_item.scope,
            "status": memory_item.status,
            "project_id": memory_item.project_id,
            "agent_id": memory_item.agent_id,
        },
        trace_id=trace_id,
    )
