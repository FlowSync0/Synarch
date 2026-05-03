from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
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
    TaskRunResult,
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


class Settings(BaseSettings):
    control_plane_url: str = "http://localhost:8010"
    state_service_url: str = "http://localhost:8020"
    state_service_timeout_seconds: float = 5.0
    memory_service_url: str = "http://localhost:8030"
    event_service_url: str = "http://localhost:8040"
    agent_runtime_url: str = "http://localhost:8050"
    agent_runtime_timeout_seconds: float = 60.0
    task_runner_memory_token_budget: int = 1200
    task_runner_provider_id: str = LOCAL_RUNTIME_PROVIDER_ID
    task_runner_model_id: str = LOCAL_RUNTIME_MODEL_ID
    task_runner_input_cost_per_million_tokens: float = LOCAL_RUNTIME_INPUT_COST_PER_MILLION
    task_runner_output_cost_per_million_tokens: float = LOCAL_RUNTIME_OUTPUT_COST_PER_MILLION


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
            raise HTTPException(status_code=403, detail=error)

        event = state_client.create_event(
            tool_call_event(tool_call, EventType.tool_called, trace_id),
            headers=headers,
        )
        audit = state_client.create_audit_log(
            tool_call_audit(tool_call, "tool.allowed", trace_id),
            headers=headers,
        )
        return ToolResult(
            tool_name=tool_call.tool_name,
            output={
                "authorized": True,
                "executed": False,
                "trace_id": trace_id,
                "event_id": event.id,
                "audit_id": audit.id,
                "service_id": tool_call.service_id,
            },
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(status_code=502, detail="Tool gate dependency unavailable") from error


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
    return None


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
