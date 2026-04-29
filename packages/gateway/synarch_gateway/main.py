from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic_settings import BaseSettings

from synarch_models import (
    ActorType,
    EventRecord,
    EventType,
    GoalEnvelope,
    GoalSubmissionResult,
    HealthResponse,
    ProjectIntent,
    ProjectRecord,
    RoutingDecision,
    TaskDraft,
    TaskRecord,
    TaskRunResult,
)

from .state_client import (
    HttpStateClient,
    StateClient,
    StateServiceRequestError,
    StateServiceUnavailable,
)
from .task_runner import (
    HttpAgentRuntimeClient,
    HttpControlPlaneClient,
    HttpMemoryClient,
    NoReadyTask,
    TaskRunner,
    TaskRunnerRequestError,
    TaskRunnerUnavailable,
)


class Settings(BaseSettings):
    control_plane_url: str = "http://localhost:8010"
    state_service_url: str = "http://localhost:8020"
    state_service_timeout_seconds: float = 5.0
    memory_service_url: str = "http://localhost:8030"
    event_service_url: str = "http://localhost:8040"
    agent_runtime_url: str = "http://localhost:8050"
    task_runner_memory_token_budget: int = 1200


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
            timeout_seconds=settings.state_service_timeout_seconds,
        ),
        memory_token_budget=settings.task_runner_memory_token_budget,
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

    return GoalSubmissionResult(
        trace_id=trace_id,
        routing_decision=routing_decision,
        project=project,
        tasks=tasks,
        events=events,
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
