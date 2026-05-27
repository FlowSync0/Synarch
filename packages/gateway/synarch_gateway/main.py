import hashlib
import importlib
import importlib.util
import ipaddress
import json
import os
import socket
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from synarch_models import (
    ActorType,
    AgentProjectAssignment,
    ApprovalStatus,
    AuditLogRecord,
    ConnectorConnectionRecord,
    ConnectorConnectionRequest,
    ConnectorConnectionResult,
    ConnectorJobKind,
    ConnectorJobMutationResult,
    ConnectorJobRecord,
    ConnectorJobResumeRequest,
    ConnectorJobRunBatchResult,
    ConnectorJobRunRequest,
    ConnectorJobRunResult,
    ConnectorJobRunStatus,
    ConnectorJobStatus,
    ConnectorJobStopRequest,
    CostBudgetEvaluation,
    CostRecord,
    CostSummary,
    CostSummaryGroup,
    CredentialAccessDecision,
    CredentialAccessRequest,
    CredentialGrant,
    CredentialGrantApplication,
    CredentialGrantApplicationRequest,
    EventRecord,
    EventType,
    GoalEnvelope,
    GoalSubmissionResult,
    HealthResponse,
    HumanAssistanceKind,
    HumanAssistanceRequest,
    HumanAssistanceResolution,
    HumanAssistanceStatus,
    LocalWorldView,
    MemoryCompactionPlanRequest,
    MemoryCompactionPlanResult,
    MemoryCompactionPolicyRequest,
    MemoryCompactionPolicyResult,
    MemoryCompactionRequest,
    MemoryCompactionResult,
    MemoryEmbeddingBackfillRequest,
    MemoryEmbeddingBackfillResult,
    MemoryItem,
    MemoryRelationApplicationResult,
    MemoryRelationProposalRequest,
    MemoryRelationProposalResult,
    MemoryStatus,
    MemoryStatusUpdate,
    OperatorAction,
    Priority,
    ProjectBrief,
    ProjectBriefAction,
    ProjectIntent,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectTimeline,
    ProjectWorkspace,
    RoutingDecision,
    SecretReference,
    ServiceDefinition,
    ServiceHealthCheck,
    ServiceHealthReport,
    ServiceHealthStatus,
    SystemReadinessItem,
    SystemReadinessReport,
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
    CredentialReadinessBlocker,
    HttpAgentRuntimeClient,
    HttpControlPlaneClient,
    HttpMemoryClient,
    MemoryClient,
    NoReadyTask,
    OpenRouterQueryEmbeddingProvider,
    TaskRunner,
    TaskRunnerRequestError,
    TaskRunnerUnavailable,
)

CostSummaryGroupBy = Literal["project", "agent", "model", "provider"]
ToolRiskLevel = Literal["low", "medium", "high"]
ToolCredentialState = Literal["not_required", "ready", "missing_scopes"]
WebExtractionProvider = Literal["local_fetch", "local_playwright", "firecrawl", "browserless"]
ReadinessStatus = Literal["ready", "warning", "blocked"]


class ToolAdapter(Protocol):
    def __call__(
        self,
        tool_call: ToolCallRequest,
        *,
        state_client: StateClient,
        headers: dict[str, str],
        trace_id: str,
    ) -> dict[str, object]: ...


class SecretVault(Protocol):
    def store_connector_secret(
        self,
        *,
        service_id: str,
        secret_value: str,
        actor_id: str,
    ) -> SecretReference: ...


class LocalFileSecretVault:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def store_connector_secret(
        self,
        *,
        service_id: str,
        secret_value: str,
        actor_id: str,
    ) -> SecretReference:
        if not secret_value:
            raise HTTPException(status_code=400, detail="Secret value cannot be empty")
        fingerprint = hashlib.sha256(secret_value.encode("utf-8")).hexdigest()[:16]
        safe_service_id = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in service_id
        )
        directory = self.root / "connectors" / safe_service_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"{fingerprint}.json"
        payload = {
            "service_id": service_id,
            "secret_value": secret_value,
            "created_by": actor_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        path.chmod(0o600)
        return SecretReference(
            ref=f"local-file://connectors/{safe_service_id}/{fingerprint}",
            vault="local_file",
            fingerprint=fingerprint,
        )


class ConnectorConnectRequest(BaseModel):
    mode: Literal["no_key", "api_key", "oauth"] = "api_key"
    api_key: str | None = Field(default=None, repr=False)
    credential_scopes: list[str] = Field(default_factory=list)
    project_id: str | None = None
    agent_id: str | None = None
    rationale: str = "Connect service through Synarch connector setup."


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


@dataclass(frozen=True)
class WebProviderManifest:
    provider_id: str
    name: str
    category: str
    implemented: bool
    requires_api_key: bool
    api_key_env_var: str | None
    capabilities: tuple[str, ...]
    notes: str
    python_module: str | None = None
    risk_level: ToolRiskLevel = "low"
    requires_human_approval: bool = False

    def as_response(self) -> dict[str, object]:
        key_configured = (
            True
            if not self.requires_api_key or self.api_key_env_var is None
            else bool(os.getenv(self.api_key_env_var))
        )
        module_configured = (
            True if self.python_module is None else module_is_available(self.python_module)
        )
        configured = key_configured and module_configured
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "category": self.category,
            "implemented": self.implemented,
            "requires_api_key": self.requires_api_key,
            "api_key_env_var": self.api_key_env_var,
            "python_module": self.python_module,
            "configured": configured,
            "capabilities": list(self.capabilities),
            "risk_level": self.risk_level,
            "requires_human_approval": self.requires_human_approval,
            "notes": self.notes,
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
    task_runner_max_tool_rounds: int = 2
    task_runner_max_tool_calls_per_round: int = 1
    task_runner_embedding_provider_id: str = ""
    task_runner_embedding_model_id: str = ""
    task_runner_embedding_timeout_seconds: float = 20.0
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key_env_var: str = "OPENROUTER_API_KEY"
    web_fetch_timeout_seconds: float = 10.0
    web_fetch_max_bytes: int = 50_000
    web_fetch_max_redirects: int = 5
    web_extract_default_provider: str = "local_fetch"
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    firecrawl_api_key_env_var: str = "FIRECRAWL_API_KEY"
    firecrawl_timeout_seconds: float = 30.0
    browserless_base_url: str = "https://production-sfo.browserless.io"
    browserless_api_key_env_var: str = "BROWSERLESS_API_KEY"
    browserless_timeout_seconds: float = 30.0
    web_extract_playwright_timeout_seconds: float = 30.0
    web_extract_playwright_wait_until: str = "domcontentloaded"
    web_extract_review_evidence_max_bytes: int = 4_096
    service_health_timeout_seconds: float = 3.0
    secret_vault_dir: str = ".synarch/secrets"


settings = Settings()
app = FastAPI(title="Synarch Gateway", version="0.1.0")


def module_is_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


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


def get_secret_vault() -> SecretVault:
    return LocalFileSecretVault(settings.secret_vault_dir)


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
        max_tool_rounds=settings.task_runner_max_tool_rounds,
        max_tool_calls_per_round=settings.task_runner_max_tool_calls_per_round,
        tool_runner=GatewayToolRunner(),
        tool_readiness=GatewayToolReadinessChecker(),
        query_embedding_provider=get_query_embedding_provider(),
    )


def get_query_embedding_provider() -> OpenRouterQueryEmbeddingProvider | None:
    if settings.task_runner_embedding_provider_id != "provider-openrouter":
        return None
    if not settings.task_runner_embedding_model_id:
        return None
    api_key = os.getenv(settings.openrouter_api_key_env_var)
    if not api_key:
        return None
    return OpenRouterQueryEmbeddingProvider(
        api_key=api_key,
        model_id=settings.task_runner_embedding_model_id,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.task_runner_embedding_timeout_seconds,
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


def connector_job_executor_headers(trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.service.value,
        "x-synarch-actor-id": "gateway-connector-job-executor",
        "x-synarch-trace-id": trace_id,
    }


def connector_job_operator_headers(
    actor_type: ActorType | str,
    actor_id: str,
    trace_id: str,
) -> dict[str, str]:
    actor_type_value = actor_type.value if isinstance(actor_type, ActorType) else actor_type
    return {
        "x-synarch-actor-type": actor_type_value,
        "x-synarch-actor-id": actor_id,
        "x-synarch-trace-id": trace_id,
    }


def service_health_headers(trace_id: str) -> dict[str, str]:
    return {
        "x-synarch-actor-type": ActorType.service.value,
        "x-synarch-actor-id": "gateway-service-health",
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
                required_tools=draft.required_tools,
                required_tool_scopes=draft.required_tool_scopes,
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


@app.get("/readiness", response_model=SystemReadinessReport)
def system_readiness(
    state_client: StateClient = Depends(get_state_client),
) -> SystemReadinessReport:
    return build_system_readiness_report(state_client)


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


@app.get("/web/providers")
def list_web_providers() -> list[dict[str, object]]:
    return [
        manifest.as_response()
        for manifest in sorted(WEB_PROVIDER_MANIFESTS.values(), key=lambda item: item.provider_id)
    ]


@app.post(
    "/connector-jobs/{job_id}/execute",
    response_model=ConnectorJobRunResult,
    status_code=201,
)
def execute_connector_job(
    job_id: str,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
    control_plane: ControlPlaneClient = Depends(get_control_plane_client),
) -> ConnectorJobRunResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = connector_job_executor_headers(trace_id)
    try:
        job = state_client.get_connector_job(job_id)
        run_request = connector_job_execution_run_request(
            job,
            state_client=state_client,
            control_plane=control_plane,
            headers=headers,
            trace_id=trace_id,
        )
        return state_client.record_connector_job_run(
            job_id,
            run_request,
            headers=headers,
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Connector job execution dependency unavailable",
        ) from error


@app.post("/connector-jobs/{job_id}/stop", response_model=ConnectorJobMutationResult)
def stop_connector_job(
    job_id: str,
    stop_request: ConnectorJobStopRequest,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> ConnectorJobMutationResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = connector_job_operator_headers(
        stop_request.stopped_by_type,
        stop_request.stopped_by_id,
        trace_id,
    )
    try:
        return state_client.stop_connector_job(job_id, stop_request, headers=headers)
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(
            status_code=502,
            detail="Connector job stop dependency unavailable",
        ) from error


@app.post("/connector-jobs/{job_id}/resume", response_model=ConnectorJobMutationResult)
def resume_connector_job(
    job_id: str,
    resume_request: ConnectorJobResumeRequest,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> ConnectorJobMutationResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = connector_job_operator_headers(
        resume_request.resumed_by_type,
        resume_request.resumed_by_id,
        trace_id,
    )
    try:
        return state_client.resume_connector_job(job_id, resume_request, headers=headers)
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(
            status_code=502,
            detail="Connector job resume dependency unavailable",
        ) from error


@app.post("/connector-jobs/run-ready", response_model=ConnectorJobRunBatchResult)
def run_ready_connector_jobs(
    request: Request,
    max_jobs: int = Query(default=3, ge=1, le=20),
    kind: ConnectorJobKind = ConnectorJobKind.cron,
    service_id: str | None = None,
    project_id: str | None = None,
    owner_agent_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
    control_plane: ControlPlaneClient = Depends(get_control_plane_client),
) -> ConnectorJobRunBatchResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = connector_job_executor_headers(trace_id)
    try:
        jobs = state_client.list_connector_jobs(
            service_id=service_id,
            project_id=project_id,
            owner_agent_id=owner_agent_id,
            kind=kind,
            status=ConnectorJobStatus.active,
            due_before=datetime.now(UTC),
        )
        selected_jobs = jobs[:max_jobs]
        runs = [
            state_client.record_connector_job_run(
                job.id,
                connector_job_execution_run_request(
                    job,
                    state_client=state_client,
                    control_plane=control_plane,
                    headers=headers,
                    trace_id=trace_id,
                ),
                headers=headers,
            )
            for job in selected_jobs
        ]
        stop_reason = (
            "max_jobs_reached"
            if len(jobs) > len(selected_jobs)
            else "no_ready_connector_job"
        )
        batch_result = ConnectorJobRunBatchResult(
            trace_id=trace_id,
            max_jobs=max_jobs,
            kind=kind,
            service_id=service_id,
            project_id=project_id,
            owner_agent_id=owner_agent_id,
            stop_reason=stop_reason,
            runs=runs,
        )
        tick_event = state_client.create_event(
            connector_job_batch_tick_event(batch_result),
            headers=headers,
        )
        tick_audit_log = state_client.create_audit_log(
            connector_job_batch_tick_audit(batch_result),
            headers=headers,
        )
        return batch_result.model_copy(
            update={"tick_event": tick_event, "tick_audit_log": tick_audit_log}
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Connector job batch dependency unavailable",
        ) from error


@app.post("/webhooks/{webhook_path:path}", response_model=ConnectorJobRunBatchResult)
async def trigger_connector_jobs_webhook(
    webhook_path: str,
    request: Request,
    max_jobs: int = Query(default=5, ge=1, le=20),
    service_id: str | None = None,
    project_id: str | None = None,
    owner_agent_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
    control_plane: ControlPlaneClient = Depends(get_control_plane_client),
) -> ConnectorJobRunBatchResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = connector_job_executor_headers(trace_id)
    normalized_path = normalized_webhook_path(webhook_path)
    trigger_payload = await webhook_trigger_payload(request, normalized_path)
    try:
        jobs = state_client.list_connector_jobs(
            service_id=service_id,
            project_id=project_id,
            owner_agent_id=owner_agent_id,
            kind=ConnectorJobKind.webhook,
            status=ConnectorJobStatus.active,
            due_before=None,
        )
        matching_jobs = [job for job in jobs if job.webhook_path == normalized_path]
        selected_jobs = matching_jobs[:max_jobs]
        runs = [
            state_client.record_connector_job_run(
                job.id,
                connector_job_execution_run_request(
                    job,
                    state_client=state_client,
                    control_plane=control_plane,
                    headers=headers,
                    trace_id=trace_id,
                    trigger_payload=trigger_payload,
                ),
                headers=headers,
            )
            for job in selected_jobs
        ]
        if len(matching_jobs) > len(selected_jobs):
            stop_reason = "max_jobs_reached"
        elif selected_jobs:
            stop_reason = "all_matching_webhook_jobs_ran"
        else:
            stop_reason = "no_matching_webhook_job"
        batch_result = ConnectorJobRunBatchResult(
            trace_id=trace_id,
            max_jobs=max_jobs,
            kind=ConnectorJobKind.webhook,
            service_id=service_id,
            project_id=project_id,
            owner_agent_id=owner_agent_id,
            stop_reason=stop_reason,
            runs=runs,
        )
        tick_event = state_client.create_event(
            connector_job_batch_tick_event(batch_result),
            headers=headers,
        )
        tick_audit_log = state_client.create_audit_log(
            connector_job_batch_tick_audit(batch_result),
            headers=headers,
        )
        return batch_result.model_copy(
            update={"tick_event": tick_event, "tick_audit_log": tick_audit_log}
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Webhook connector job dependency unavailable",
        ) from error


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


@app.post("/services/health-checks", response_model=ServiceHealthReport)
def check_service_health(
    request: Request,
    agent_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
    control_plane: ControlPlaneClient = Depends(get_control_plane_client),
) -> ServiceHealthReport:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = service_health_headers(trace_id)
    try:
        services = state_client.list_services(enabled=True)
        if agent_id is not None:
            world_view = control_plane.get_world_view(agent_id)
            available_service_ids = set(world_view.available_services)
            services = [
                service for service in services if service.id in available_service_ids
            ]
        checks = [
            probe_service_health(
                service,
                timeout_seconds=settings.service_health_timeout_seconds,
            )
            for service in services
        ]
        report = ServiceHealthReport(
            trace_id=trace_id,
            agent_id=agent_id,
            checks=checks,
        )
        event = state_client.create_event(
            service_health_event(report),
            headers=headers,
        )
        audit_log = state_client.create_audit_log(
            service_health_audit(report),
            headers=headers,
        )
        return report.model_copy(update={"event": event, "audit_log": audit_log})
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Service health dependency unavailable",
        ) from error


@app.get("/credential-access-requests", response_model=list[CredentialAccessRequest])
def list_credential_access_requests(
    project_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    status: ApprovalStatus | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[CredentialAccessRequest]:
    try:
        return state_client.list_credential_access_requests(
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            status=status.value if status is not None else None,
        )
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.get("/human-assistance-requests", response_model=list[HumanAssistanceRequest])
def list_human_assistance_requests(
    project_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    kind: HumanAssistanceKind | None = None,
    status: HumanAssistanceStatus | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[HumanAssistanceRequest]:
    try:
        return state_client.list_human_assistance_requests(
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            kind=kind.value if kind is not None else None,
            status=status.value if status is not None else None,
        )
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post(
    "/human-assistance-requests/{request_id}/resolutions",
    response_model=HumanAssistanceResolution,
)
def resolve_human_assistance_request(
    request_id: str,
    resolution: HumanAssistanceResolution,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> HumanAssistanceResolution:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = task_reviewer_headers(request, trace_id)
    try:
        return state_client.resolve_human_assistance_request(
            request_id,
            resolution,
            headers=headers,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post(
    "/credential-access-requests/{request_id}/decisions",
    response_model=CredentialAccessDecision,
)
def decide_credential_access_request(
    request_id: str,
    decision: CredentialAccessDecision,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> CredentialAccessDecision:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = task_reviewer_headers(request, trace_id)
    try:
        return state_client.decide_credential_access_request(
            request_id,
            decision,
            headers=headers,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post(
    "/credential-access-requests/{request_id}/grant-applications",
    response_model=CredentialGrantApplication,
)
def apply_credential_access_grant(
    request_id: str,
    application: CredentialGrantApplicationRequest,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
) -> CredentialGrantApplication:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = task_reviewer_headers(request, trace_id)
    try:
        return state_client.apply_credential_access_grant(
            request_id,
            application,
            headers=headers,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.get("/credential-grants", response_model=list[CredentialGrant])
def list_credential_grants(
    request_id: str | None = None,
    service_id: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    active: bool | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[CredentialGrant]:
    try:
        return state_client.list_credential_grants(
            request_id=request_id,
            service_id=service_id,
            agent_id=agent_id,
            project_id=project_id,
            active=active,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.post("/connectors/{service_id}/connections", response_model=ConnectorConnectionResult)
def connect_service(
    service_id: str,
    connection: ConnectorConnectRequest,
    request: Request,
    state_client: StateClient = Depends(get_state_client),
    secret_vault: SecretVault = Depends(get_secret_vault),
) -> ConnectorConnectionResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    actor_type = request.headers.get("x-synarch-actor-type", ActorType.user.value)
    actor_id = request.headers.get("x-synarch-actor-id", "local-user")
    try:
        service = service_definition_by_id(state_client, service_id)
        secret_ref: SecretReference | None = None
        if connection.mode == "api_key":
            if not connection.api_key:
                raise HTTPException(
                    status_code=400,
                    detail="api_key is required for api_key connector connections",
                )
            secret_ref = secret_vault.store_connector_secret(
                service_id=service_id,
                secret_value=connection.api_key,
                actor_id=actor_id,
            )
        request_payload = ConnectorConnectionRequest(
            service_id=service_id,
            mode=connection.mode,
            credential_scopes=connection.credential_scopes or service.credential_scopes,
            secret_ref=secret_ref.ref if secret_ref else None,
            secret_fingerprint=secret_ref.fingerprint if secret_ref else None,
            connected_by_type=ActorType(actor_type),
            connected_by_id=actor_id,
            project_id=connection.project_id,
            agent_id=connection.agent_id,
            rationale=connection.rationale,
        )
        return state_client.create_connector_connection(
            request_payload,
            headers=service_headers(trace_id),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Unknown actor type: {actor_type}") from error
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


@app.get("/connector-connections", response_model=list[ConnectorConnectionRecord])
def list_connector_connections(
    service_id: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
    agent_id: str | None = None,
    state_client: StateClient = Depends(get_state_client),
) -> list[ConnectorConnectionRecord]:
    try:
        return state_client.list_connector_connections(
            service_id=service_id,
            status=status,
            project_id=project_id,
            agent_id=agent_id,
        )
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


def service_definition_by_id(state_client: StateClient, service_id: str) -> ServiceDefinition:
    for service in state_client.list_services():
        if service.id == service_id:
            return service
    raise StateServiceRequestError(404, f"Unknown service: {service_id}")


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


class GatewayToolReadinessChecker:
    def credential_blockers(
        self,
        task: TaskRecord,
        world_view: LocalWorldView,
    ) -> list[CredentialReadinessBlocker]:
        statuses = tool_credential_statuses_for_world_view(
            world_view,
            required_scopes_by_tool=task.required_tool_scopes,
        )
        blockers: list[CredentialReadinessBlocker] = []
        for required_tool in task.required_tools:
            task_required_scopes = tuple(task.required_tool_scopes.get(required_tool, []))
            matching_statuses = [
                status for status in statuses if status.tool_name == required_tool
            ]
            candidate_service_ids = candidate_service_ids_for_tool(world_view, required_tool)
            if not matching_statuses:
                manifest = TOOL_ADAPTER_MANIFESTS.get(required_tool)
                blockers.append(
                    CredentialReadinessBlocker(
                        tool_name=required_tool,
                        reason=(
                            "No credential-ready service for required tool: "
                            f"{required_tool}"
                        ),
                        requested_scopes=task_required_scopes
                        or (manifest.credential_scopes if manifest is not None else ()),
                        candidate_service_ids=tuple(candidate_service_ids),
                    )
                )
                continue
            if all(status.status == "missing_scopes" for status in matching_statuses):
                missing_scopes = tuple(
                    dict.fromkeys(
                        scope
                        for status in matching_statuses
                        for scope in status.missing_scopes
                    )
                )
                blockers.append(
                    CredentialReadinessBlocker(
                        tool_name=required_tool,
                        reason=(
                            "Credential scopes missing for required tool: "
                            f"{required_tool}"
                        ),
                        requested_scopes=missing_scopes,
                        candidate_service_ids=tuple(
                            status.service_id for status in matching_statuses
                        ),
                    )
                )
        return blockers


def tool_result_status_from_execution_output(
    execution_output: dict[str, object],
) -> TaskStatus:
    raw_status = execution_output.get("tool_status")
    if not isinstance(raw_status, str):
        return TaskStatus.completed
    try:
        return TaskStatus(raw_status)
    except ValueError:
        return TaskStatus.completed


def tool_result_error_from_execution_output(
    execution_output: dict[str, object],
    status: TaskStatus,
) -> str | None:
    if status == TaskStatus.completed:
        return None
    for key in ("error", "blocked_reason", "review_reason"):
        value = execution_output.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Tool returned non-completed status: {status.value}"


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
    if error is None:
        error = task_tool_credential_scope_error(
            tool_call,
            world_view,
            state_client,
        )
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
    except StateServiceRequestError as error:
        detail = str(error.detail)
        state_client.create_event(
            tool_call_event(tool_call, EventType.tool_failed, trace_id, error=detail),
            headers=headers,
        )
        state_client.create_audit_log(
            tool_call_audit(tool_call, "tool.failed", trace_id, error=detail),
            headers=headers,
        )
        if raise_on_failure:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error
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

    tool_status = tool_result_status_from_execution_output(execution_output)
    if tool_status != TaskStatus.completed:
        execution_output = attach_human_assistance_request_if_needed(
            execution_output,
            tool_call=tool_call,
            state_client=state_client,
            headers=headers,
            trace_id=trace_id,
        )
    tool_error = tool_result_error_from_execution_output(execution_output, tool_status)
    if tool_status != TaskStatus.completed:
        log_payload = tool_result_log_payload(execution_output)
        state_client.create_event(
            tool_call_event(
                tool_call,
                EventType.tool_failed,
                trace_id,
                error=tool_error,
                extra_payload=log_payload,
            ),
            headers=headers,
        )
        state_client.create_audit_log(
            tool_call_audit(
                tool_call,
                f"tool.{tool_status.value}",
                trace_id,
                error=tool_error,
                extra_payload=log_payload,
            ),
            headers=headers,
        )

    return ToolResult(
        tool_name=tool_call.tool_name,
        status=tool_status,
        output={
            "authorized": True,
            "trace_id": trace_id,
            "event_id": event.id,
            "audit_id": audit.id,
            "service_id": tool_call.service_id,
            **execution_output,
        },
        error=tool_error,
    )


def tool_result_log_payload(execution_output: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in (
        "tool_status",
        "blocked_reason",
        "requires_human_review",
        "block_signals",
        "recommended_action",
        "human_assistance_request_id",
        "provider_escalation_options",
        "review_evidence",
    ):
        value = execution_output.get(key)
        if value is not None:
            payload[key] = value
    return payload


def attach_human_assistance_request_if_needed(
    execution_output: dict[str, object],
    *,
    tool_call: ToolCallRequest,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    if tool_call.tool_name == "human.assistance.request":
        return execution_output
    if execution_output.get("requires_human_review") is not True:
        return execution_output
    if execution_output.get("human_assistance_request_id") is not None:
        return execution_output

    project_id = tool_call.project_id or string_payload_value(
        execution_output.get("project_id")
    )
    if project_id is None:
        return {
            **execution_output,
            "human_assistance_request_error": "missing_project_id",
        }

    blocked_reason = (
        string_payload_value(execution_output.get("blocked_reason"))
        or string_payload_value(execution_output.get("error"))
        or "requires_human_review"
    )
    assistance_request = HumanAssistanceRequest(
        id=automatic_human_assistance_request_id(
            tool_call,
            blocked_reason=blocked_reason,
        ),
        project_id=project_id,
        task_id=tool_call.task_id,
        agent_id=tool_call.agent_id,
        kind=automatic_human_assistance_kind(blocked_reason),
        title=automatic_human_assistance_title(tool_call, blocked_reason),
        description=automatic_human_assistance_description(tool_call, blocked_reason),
        urgency=automatic_human_assistance_urgency(blocked_reason),
        evidence=automatic_human_assistance_evidence(
            tool_call,
            execution_output,
            trace_id,
            blocked_reason,
        ),
        requested_by_type=ActorType.agent,
        requested_by_id=tool_call.agent_id,
    )
    try:
        record = state_client.create_human_assistance_request(
            assistance_request,
            headers=headers,
        )
    except StateServiceRequestError as error:
        if error.status_code != 409:
            return {
                **execution_output,
                "human_assistance_request_error": str(error.detail),
            }
        record = state_client.get_human_assistance_request(assistance_request.id)
    except StateServiceUnavailable:
        return {
            **execution_output,
            "human_assistance_request_error": "state_service_unavailable",
        }

    return {
        **execution_output,
        "human_assistance_request": record.model_dump(mode="json"),
        "human_assistance_request_id": record.id,
        "recommended_action": (
            "Answer the human assistance request, then retry or update the task."
        ),
    }


def automatic_human_assistance_request_id(
    tool_call: ToolCallRequest,
    *,
    blocked_reason: str,
) -> str:
    url = string_payload_value(tool_call.arguments.get("url"))
    raw = json.dumps(
        {
            "agent_id": tool_call.agent_id,
            "project_id": tool_call.project_id,
            "task_id": tool_call.task_id,
            "tool_name": tool_call.tool_name,
            "service_id": tool_call.service_id,
            "blocked_reason": blocked_reason,
            "url": url,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    scope = safe_identifier_fragment(
        tool_call.task_id or tool_call.project_id or tool_call.tool_name,
        max_length=48,
    )
    return f"human_assistance_auto_{scope}_{digest}"


def automatic_human_assistance_kind(blocked_reason: str) -> HumanAssistanceKind:
    if "captcha" in blocked_reason or "human_verification" in blocked_reason:
        return HumanAssistanceKind.captcha
    if "authentication" in blocked_reason or "login" in blocked_reason:
        return HumanAssistanceKind.manual_action
    return HumanAssistanceKind.error_resolution


def automatic_human_assistance_title(
    tool_call: ToolCallRequest,
    blocked_reason: str,
) -> str:
    if automatic_human_assistance_kind(blocked_reason) == HumanAssistanceKind.captcha:
        return "CAPTCHA or human verification required"
    if automatic_human_assistance_kind(blocked_reason) == HumanAssistanceKind.manual_action:
        return "Manual account action required"
    return f"Human review required for {tool_call.tool_name}"


def automatic_human_assistance_description(
    tool_call: ToolCallRequest,
    blocked_reason: str,
) -> str:
    return (
        f"{tool_call.tool_name} returned {blocked_reason} and needs human review "
        f"before the task can continue. Tool reason: {tool_call.reason}"
    )


def automatic_human_assistance_urgency(blocked_reason: str) -> str:
    if automatic_human_assistance_kind(blocked_reason) in {
        HumanAssistanceKind.captcha,
        HumanAssistanceKind.manual_action,
    }:
        return "high"
    return "medium"


def automatic_human_assistance_evidence(
    tool_call: ToolCallRequest,
    execution_output: dict[str, object],
    trace_id: str,
    blocked_reason: str,
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "source_trace_id": trace_id,
        "tool_name": tool_call.tool_name,
        "tool_reason": tool_call.reason,
        "service_id": tool_call.service_id,
        "blocked_reason": blocked_reason,
        "argument_keys": sorted(tool_call.arguments.keys()),
    }
    for key in ("url", "provider", "final_url", "status_code", "title", "block_signals"):
        value = execution_output.get(key)
        if value is None and key == "url":
            value = string_payload_value(tool_call.arguments.get("url"))
        if value is not None:
            evidence[key] = value
    review_evidence = execution_output.get("review_evidence")
    if isinstance(review_evidence, dict):
        evidence["review_evidence"] = review_evidence
    provider_options = execution_output.get("provider_escalation_options")
    if isinstance(provider_options, list):
        evidence["provider_escalation_options"] = provider_options
    return evidence


def safe_identifier_fragment(value: str, *, max_length: int) -> str:
    safe = "".join(character if character.isalnum() else "_" for character in value)
    safe = safe.strip("_")
    return (safe[:max_length].strip("_") or uuid4().hex[:12])


def connector_job_execution_run_request(
    job: ConnectorJobRecord,
    *,
    state_client: StateClient,
    control_plane: ControlPlaneClient,
    headers: dict[str, str],
    trace_id: str,
    trigger_payload: dict[str, object] | None = None,
) -> ConnectorJobRunRequest:
    tool_call_result = connector_job_tool_call(
        job,
        trace_id,
        trigger_payload=trigger_payload,
    )
    if isinstance(tool_call_result, ConnectorJobRunRequest):
        return tool_call_result

    tool_result = execute_tool_call_through_gate(
        tool_call_result,
        state_client=state_client,
        control_plane=control_plane,
        headers=headers,
        trace_id=trace_id,
        raise_on_failure=False,
    )
    run_status = connector_job_run_status_from_tool_result(tool_result)
    return ConnectorJobRunRequest(
        status=run_status,
        triggered_by_type=ActorType.service,
        triggered_by_id="gateway-connector-job-executor",
        output={
            "execution_mode": "tool_gate",
            "tool_name": tool_result.tool_name,
            "service_id": job.service_id,
            "tool_result": tool_result.model_dump(mode="json"),
        },
        error=tool_result.error
        if run_status in {ConnectorJobRunStatus.failed, ConnectorJobRunStatus.blocked}
        else None,
    )


def connector_job_run_status_from_tool_result(tool_result: ToolResult) -> ConnectorJobRunStatus:
    if tool_result.status == TaskStatus.completed:
        return ConnectorJobRunStatus.completed
    if tool_result.status == TaskStatus.blocked:
        return ConnectorJobRunStatus.blocked
    return ConnectorJobRunStatus.failed


def connector_job_tool_call(
    job: ConnectorJobRecord,
    trace_id: str,
    *,
    trigger_payload: dict[str, object] | None = None,
) -> ToolCallRequest | ConnectorJobRunRequest:
    raw_tool_name = job.metadata.get("tool_name")
    if not isinstance(raw_tool_name, str) or not raw_tool_name.strip():
        return ConnectorJobRunRequest(
            status=ConnectorJobRunStatus.skipped,
            triggered_by_type=ActorType.service,
            triggered_by_id="gateway-connector-job-executor",
            output={
                "executed": False,
                "reason": "connector job metadata missing tool_name",
                "metadata_keys": sorted(job.metadata),
            },
        )

    raw_arguments = job.metadata.get("arguments", {})
    if not isinstance(raw_arguments, dict):
        return ConnectorJobRunRequest(
            status=ConnectorJobRunStatus.failed,
            triggered_by_type=ActorType.service,
            triggered_by_id="gateway-connector-job-executor",
            output={
                "executed": False,
                "tool_name": raw_tool_name,
                "reason": "connector job metadata arguments must be an object",
            },
            error="Connector job metadata arguments must be an object",
        )

    raw_reason = job.metadata.get("reason")
    reason = raw_reason if isinstance(raw_reason, str) and raw_reason.strip() else job.purpose
    arguments = {str(key): value for key, value in raw_arguments.items()}
    if trigger_payload is not None:
        arguments = connector_job_arguments_with_trigger_payload(
            raw_tool_name.strip(),
            arguments,
            trigger_payload,
        )
    return ToolCallRequest(
        agent_id=job.owner_agent_id,
        tool_name=raw_tool_name.strip(),
        service_id=job.service_id,
        project_id=job.project_id,
        task_id=job.task_id,
        trace_id=trace_id,
        reason=reason,
        arguments=arguments,
    )


def connector_job_arguments_with_trigger_payload(
    tool_name: str,
    arguments: dict[str, object],
    trigger_payload: dict[str, object],
) -> dict[str, object]:
    if tool_name != "event.emit":
        return {**arguments, "webhook": trigger_payload}

    raw_payload = arguments.get("payload", {})
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    return {
        **arguments,
        "payload": {
            **payload,
            "webhook": trigger_payload,
        },
    }


def normalized_webhook_path(webhook_path: str) -> str:
    normalized = webhook_path.strip("/")
    return f"/webhooks/{normalized}" if normalized else "/webhooks"


async def webhook_trigger_payload(
    request: Request,
    webhook_path: str,
) -> dict[str, object]:
    try:
        body: object = await request.json()
    except ValueError:
        raw_body = await request.body()
        body = raw_body.decode("utf-8", errors="replace")
    return {
        "webhook_path": webhook_path,
        "body": body,
        "content_type": request.headers.get("content-type"),
    }


def connector_job_batch_tick_payload(
    batch_result: ConnectorJobRunBatchResult,
) -> dict[str, object]:
    run_statuses = [run_result.run.status for run_result in batch_result.runs]
    return {
        "max_jobs": batch_result.max_jobs,
        "kind": batch_result.kind,
        "service_id": batch_result.service_id,
        "project_id": batch_result.project_id,
        "owner_agent_id": batch_result.owner_agent_id,
        "stop_reason": batch_result.stop_reason,
        "run_count": len(batch_result.runs),
        "connector_job_ids": [run_result.run.job_id for run_result in batch_result.runs],
        "connector_job_run_ids": [run_result.run.id for run_result in batch_result.runs],
        "run_statuses": run_statuses,
        "completed_run_count": run_statuses.count(ConnectorJobRunStatus.completed),
        "failed_run_count": run_statuses.count(ConnectorJobRunStatus.failed),
        "blocked_run_count": run_statuses.count(ConnectorJobRunStatus.blocked),
        "skipped_run_count": run_statuses.count(ConnectorJobRunStatus.skipped),
        "executor": "gateway-connector-job-executor",
    }


def connector_job_batch_tick_event(
    batch_result: ConnectorJobRunBatchResult,
) -> EventRecord:
    return EventRecord(
        type=EventType.connector_job_tick,
        target=(
            batch_result.project_id
            or batch_result.service_id
            or "gateway-connector-job-executor"
        ),
        payload=connector_job_batch_tick_payload(batch_result),
        trace_id=batch_result.trace_id,
    )


def connector_job_batch_tick_audit(
    batch_result: ConnectorJobRunBatchResult,
) -> AuditLogRecord:
    if batch_result.project_id is not None:
        target_type = "project"
        target_id = batch_result.project_id
    elif batch_result.service_id is not None:
        target_type = "service"
        target_id = batch_result.service_id
    else:
        target_type = "connector_job_executor"
        target_id = "gateway-connector-job-executor"

    return AuditLogRecord(
        actor_type=ActorType.service,
        actor_id="gateway-connector-job-executor",
        action="connector_job.tick",
        target_type=target_type,
        target_id=target_id,
        payload=connector_job_batch_tick_payload(batch_result),
        trace_id=batch_result.trace_id,
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
        connector_job_error = connector_job_run_tool_access_error(
            tool_call,
            world_view,
            service_capabilities,
        )
        if connector_job_error is not None:
            return connector_job_error
    credential_error = tool_credential_scope_error(tool_call, world_view)
    if credential_error is not None:
        return credential_error
    return None


def connector_job_run_tool_access_error(
    tool_call: ToolCallRequest,
    world_view: LocalWorldView,
    service_capabilities: list[str],
) -> str | None:
    if tool_call.tool_name != "connector.job.create":
        return None
    raw_run_tool_name = tool_call.arguments.get("run_tool_name")
    if not isinstance(raw_run_tool_name, str) or not raw_run_tool_name.strip():
        return None
    run_tool_name = raw_run_tool_name.strip()
    if run_tool_name not in world_view.permissions.allowed_tools:
        return f"Connector job run tool not allowed for agent: {run_tool_name}"
    if run_tool_name not in service_capabilities:
        return (
            f"Connector job run tool not exposed by service: {run_tool_name} "
            f"via {tool_call.service_id}"
        )
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


def task_tool_credential_scope_error(
    tool_call: ToolCallRequest,
    world_view: LocalWorldView,
    state_client: StateClient,
) -> str | None:
    if tool_call.task_id is None:
        return None
    try:
        task = state_client.get_task(tool_call.task_id)
    except (StateServiceRequestError, ValueError, KeyError):
        return None

    required_scopes = task.required_tool_scopes.get(tool_call.tool_name, [])
    if not required_scopes:
        return None
    if tool_call.service_id is None:
        return f"Missing service for credential-scoped tool: {tool_call.tool_name}"

    service_scopes = world_view.available_service_credential_scopes.get(
        tool_call.service_id, []
    )
    missing_scopes = [scope for scope in required_scopes if scope not in service_scopes]
    if not missing_scopes:
        return None
    return (
        f"Missing task credential scopes for service {tool_call.service_id}: "
        f"{', '.join(missing_scopes)}"
    )


def tool_credential_statuses_for_world_view(
    world_view: LocalWorldView,
    *,
    required_scopes_by_tool: dict[str, list[str]] | None = None,
) -> list[ToolCredentialStatus]:
    statuses: list[ToolCredentialStatus] = []
    task_required_scopes = required_scopes_by_tool or {}
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
            if manifest is None and tool_name not in task_required_scopes:
                continue
            required_scopes = tuple(
                task_required_scopes.get(
                    tool_name,
                    list(manifest.credential_scopes) if manifest is not None else [],
                )
            )
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


def candidate_service_ids_for_tool(
    world_view: LocalWorldView,
    tool_name: str,
) -> list[str]:
    available_services = set(world_view.available_services)
    return [
        service_id
        for service_id in sorted(world_view.available_service_capabilities)
        if service_id in available_services
        and tool_name in world_view.available_service_capabilities[service_id]
    ]


def probe_service_health(
    service: ServiceDefinition,
    *,
    timeout_seconds: float,
) -> ServiceHealthCheck:
    if not service.enabled:
        return service_health_check(
            service,
            status=ServiceHealthStatus.unknown,
            error="Service is disabled.",
        )
    if service.base_url is None or service.health_endpoint is None:
        return service_health_check(
            service,
            status=ServiceHealthStatus.unknown,
            error="No health endpoint configured.",
        )

    url = service_health_url(service)
    started_at = time.monotonic()
    try:
        response = httpx.get(url, timeout=timeout_seconds)
    except httpx.HTTPError:
        response_time_ms = elapsed_ms(started_at)
        return service_health_check(
            service,
            status=ServiceHealthStatus.unhealthy,
            response_time_ms=response_time_ms,
            error="Health request failed.",
        )

    response_time_ms = elapsed_ms(started_at)
    if 200 <= response.status_code < 300:
        return service_health_check(
            service,
            status=ServiceHealthStatus.healthy,
            status_code=response.status_code,
            response_time_ms=response_time_ms,
        )
    return service_health_check(
        service,
        status=ServiceHealthStatus.unhealthy,
        status_code=response.status_code,
        response_time_ms=response_time_ms,
        error=f"Health endpoint returned HTTP {response.status_code}.",
    )


def service_health_url(service: ServiceDefinition) -> str:
    base_url = (service.base_url or "").rstrip("/")
    endpoint = (service.health_endpoint or "").lstrip("/")
    return urljoin(f"{base_url}/", endpoint)


def elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def service_health_check(
    service: ServiceDefinition,
    *,
    status: ServiceHealthStatus,
    status_code: int | None = None,
    response_time_ms: int | None = None,
    error: str | None = None,
) -> ServiceHealthCheck:
    return ServiceHealthCheck(
        service_id=service.id,
        name=service.name,
        kind=service.kind,
        enabled=service.enabled,
        status=status,
        base_url=service.base_url,
        health_endpoint=service.health_endpoint,
        status_code=status_code,
        response_time_ms=response_time_ms,
        error=error,
        capabilities=service.capabilities,
        credential_scopes=service.credential_scopes,
    )


def service_health_counts(checks: list[ServiceHealthCheck]) -> dict[str, int]:
    return {
        status.value: sum(1 for check in checks if check.status == status)
        for status in ServiceHealthStatus
    }


def service_health_payload(report: ServiceHealthReport) -> dict[str, object]:
    return {
        "agent_id": report.agent_id,
        "service_count": len(report.checks),
        "service_ids": [check.service_id for check in report.checks],
        "status_counts": service_health_counts(report.checks),
        "statuses": {
            check.service_id: check.status for check in report.checks
        },
    }


def service_health_event(report: ServiceHealthReport) -> EventRecord:
    return EventRecord(
        type=EventType.service_health_checked,
        target=report.agent_id or "services",
        payload=service_health_payload(report),
        trace_id=report.trace_id,
    )


def service_health_audit(report: ServiceHealthReport) -> AuditLogRecord:
    return AuditLogRecord(
        actor_type=ActorType.service,
        actor_id="gateway-service-health",
        action="services.health_checked",
        target_type="agent" if report.agent_id is not None else "services",
        target_id=report.agent_id or "services",
        payload=service_health_payload(report),
        trace_id=report.trace_id,
    )


def build_system_readiness_report(state_client: StateClient) -> SystemReadinessReport:
    try:
        services = state_client.list_services(enabled=True)
        projects = state_client.list_projects()
        review_tasks = state_client.list_task_review_queue()
        credential_requests = state_client.list_credential_access_requests(
            status=ApprovalStatus.requested.value,
        )
        human_requests = state_client.list_human_assistance_requests(
            status=HumanAssistanceStatus.requested.value,
        )
        blocked_connector_jobs = state_client.list_connector_jobs(
            last_run_status=ConnectorJobRunStatus.blocked.value,
        )
        scheduler_ticks = state_client.list_events(event_type=EventType.scheduler_tick.value)
        connector_ticks = state_client.list_events(event_type=EventType.connector_job_tick.value)
    except StateServiceRequestError as error:
        return readiness_report(
            [
                readiness_item(
                    "state_service",
                    "core",
                    "State service API",
                    "blocked",
                    f"State service returned {error.status_code}: {error.detail}",
                    "Inspect state-service logs, run migrations, then retry /readiness.",
                )
            ]
        )
    except StateServiceUnavailable:
        return readiness_report(
            [
                readiness_item(
                    "state_service",
                    "core",
                    "State service API",
                    "blocked",
                    "Gateway cannot reach the state-service.",
                    "Start the backend stack with make dev-backend or docker compose up.",
                    {"state_service_url": settings.state_service_url},
                )
            ]
        )

    items = [
        readiness_item(
            "state_service",
            "core",
            "State service API",
            "ready",
            (
                f"State is reachable with {len(projects)} project(s) and "
                f"{len(services)} enabled service(s)."
            ),
            evidence={
                "state_service_url": settings.state_service_url,
                "project_count": len(projects),
                "enabled_service_count": len(services),
            },
        ),
        seed_services_readiness_item(services),
        ai_runtime_readiness_item(state_client),
        web_provider_readiness_item(),
        worker_readiness_item(
            scheduler_tick_count=len(scheduler_ticks),
            connector_tick_count=len(connector_ticks),
        ),
        operator_action_readiness_item(
            review_task_count=len(review_tasks),
            credential_request_count=len(credential_requests),
            human_request_count=len(human_requests),
            blocked_connector_job_count=len(blocked_connector_jobs),
        ),
    ]
    return readiness_report(items)


def readiness_report(items: list[SystemReadinessItem]) -> SystemReadinessReport:
    status: ReadinessStatus = "ready"
    if any(item.status == "blocked" for item in items):
        status = "blocked"
    elif any(item.status == "warning" for item in items):
        status = "warning"
    return SystemReadinessReport(status=status, items=items)


def readiness_item(
    item_id: str,
    category: str,
    title: str,
    status: ReadinessStatus,
    detail: str,
    manual_action: str | None = None,
    evidence: Mapping[str, object] | None = None,
) -> SystemReadinessItem:
    return SystemReadinessItem(
        id=item_id,
        category=category,
        title=title,
        status=status,
        detail=detail,
        manual_action=manual_action,
        evidence=dict(evidence or {}),
    )


def seed_services_readiness_item(services: list[ServiceDefinition]) -> SystemReadinessItem:
    service_ids = {service.id for service in services}
    required_service_ids = {
        "service-event-log",
        "connector-supplier-web",
        "connector-web-local",
    }
    missing_service_ids = sorted(required_service_ids - service_ids)
    if missing_service_ids:
        return readiness_item(
            "seed_services",
            "core",
            "Seeded services",
            "blocked",
            f"Missing required seeded service(s): {', '.join(missing_service_ids)}.",
            "Run make seed-state against the configured DATABASE_URL.",
            {
                "missing_service_ids": missing_service_ids,
                "present_service_ids": sorted(service_ids),
            },
        )
    return readiness_item(
        "seed_services",
        "core",
        "Seeded services",
        "ready",
        "Required internal and web service definitions are present.",
        evidence={"required_service_ids": sorted(required_service_ids)},
    )


def ai_runtime_readiness_item(state_client: StateClient) -> SystemReadinessItem:
    provider_id = settings.task_runner_provider_id
    model_id = settings.task_runner_model_id
    try:
        provider = state_client.get_model_provider(provider_id)
        model = state_client.get_model_definition(model_id)
    except StateServiceRequestError as error:
        return readiness_item(
            "ai_runtime",
            "runtime",
            "AI runtime route",
            "blocked",
            f"Configured provider/model is not seeded in state: {error.detail}",
            (
                "Run make seed-state, then configure TASK_RUNNER_PROVIDER_ID and "
                "TASK_RUNNER_MODEL_ID to existing state records."
            ),
            {"provider_id": provider_id, "model_id": model_id},
        )

    api_key_env_var = provider.api_key_env_var
    api_key_configured = bool(api_key_env_var and os.getenv(api_key_env_var))
    evidence = {
        "provider_id": provider.id,
        "model_id": model.id,
        "provider_type": provider.provider_type,
        "api_key_env_var": api_key_env_var,
        "api_key_configured": api_key_configured if api_key_env_var else None,
        "agent_runtime_url": settings.agent_runtime_url,
    }
    if provider_id == LOCAL_RUNTIME_PROVIDER_ID or model_id == LOCAL_RUNTIME_MODEL_ID:
        return readiness_item(
            "ai_runtime",
            "runtime",
            "AI runtime route",
            "warning",
            "Task runner is using the deterministic local stub route.",
            (
                "For real AI employees, set AGENT_RUNTIME_MODE=model_gateway, "
                "MODEL_GATEWAY_MODE=openrouter, "
                "TASK_RUNNER_PROVIDER_ID=provider-openrouter, "
                "TASK_RUNNER_MODEL_ID=deepseek/deepseek-v4-flash, and "
                "OPENROUTER_API_KEY."
            ),
            evidence,
        )
    if api_key_env_var and not api_key_configured:
        return readiness_item(
            "ai_runtime",
            "runtime",
            "AI runtime route",
            "blocked",
            f"{api_key_env_var} is required for provider {provider_id}.",
            f"Set {api_key_env_var} in the backend environment and restart the affected services.",
            evidence,
        )
    return readiness_item(
        "ai_runtime",
        "runtime",
        "AI runtime route",
        "ready",
        f"Task runner is configured for {provider_id} / {model_id}.",
        evidence=evidence,
    )


def web_provider_readiness_item() -> SystemReadinessItem:
    default_provider = settings.web_extract_default_provider
    supported_provider_ids = {"local_fetch", "local_playwright", "firecrawl", "browserless"}
    if default_provider not in supported_provider_ids:
        return readiness_item(
            "web_providers",
            "tools",
            "Web extraction providers",
            "blocked",
            f"WEB_EXTRACT_DEFAULT_PROVIDER={default_provider} is not executable by web.extract.",
            (
                "Set WEB_EXTRACT_DEFAULT_PROVIDER to local_fetch, local_playwright, "
                "firecrawl, or browserless."
            ),
            {
                "default_provider": default_provider,
                "supported_provider_ids": sorted(supported_provider_ids),
            },
        )
    default_manifest = WEB_PROVIDER_MANIFESTS[default_provider]
    default_provider_status = default_manifest.as_response()
    configured_provider_ids: list[str] = []
    for manifest in WEB_PROVIDER_MANIFESTS.values():
        provider = manifest.as_response()
        provider_id = provider["provider_id"]
        if (
            isinstance(provider_id, str)
            and provider["implemented"] is True
            and provider["configured"] is True
        ):
            configured_provider_ids.append(provider_id)
    evidence = {
        "default_provider": default_provider,
        "configured_provider_ids": sorted(configured_provider_ids),
    }
    if not default_provider_status["configured"]:
        return readiness_item(
            "web_providers",
            "tools",
            "Web extraction providers",
            "blocked",
            f"Default web.extract provider {default_provider} is not fully configured.",
            (
                "Use WEB_EXTRACT_DEFAULT_PROVIDER=local_fetch or configure the "
                "required provider key/dependency."
            ),
            evidence,
        )
    paid_provider_configured = any(
        provider_id in configured_provider_ids
        for provider_id in {"firecrawl", "browserless"}
    )
    local_browser_configured = "local_playwright" in configured_provider_ids
    if not paid_provider_configured and not local_browser_configured:
        return readiness_item(
            "web_providers",
            "tools",
            "Web extraction providers",
            "warning",
            (
                "Only the no-key HTTP extractor is ready; JavaScript, CAPTCHA, "
                "and anti-bot pages may need human escalation."
            ),
            (
                "Install Playwright browsers or configure "
                "FIRECRAWL_API_KEY/BROWSERLESS_API_KEY when those flows become necessary."
            ),
            evidence,
        )
    return readiness_item(
        "web_providers",
        "tools",
        "Web extraction providers",
        "ready",
        (
            f"Default provider {default_provider} is configured with at least one "
            "browser/cloud fallback."
        ),
        evidence=evidence,
    )


def worker_readiness_item(
    *,
    scheduler_tick_count: int,
    connector_tick_count: int,
) -> SystemReadinessItem:
    if scheduler_tick_count > 0 and connector_tick_count > 0:
        return readiness_item(
            "worker_loops",
            "automation",
            "Background workers",
            "ready",
            "Scheduler and connector workers have recorded ticks.",
            evidence={
                "scheduler_tick_count": scheduler_tick_count,
                "connector_tick_count": connector_tick_count,
            },
        )
    return readiness_item(
        "worker_loops",
        "automation",
        "Background workers",
        "warning",
        "No scheduler and connector worker tick pair is visible yet.",
        (
            "For 24/7 autonomous operation, start Docker with the worker profile: "
            "docker compose --profile worker up -d."
        ),
        {
            "scheduler_tick_count": scheduler_tick_count,
            "connector_tick_count": connector_tick_count,
        },
    )


def operator_action_readiness_item(
    *,
    review_task_count: int,
    credential_request_count: int,
    human_request_count: int,
    blocked_connector_job_count: int,
) -> SystemReadinessItem:
    evidence = {
        "review_task_count": review_task_count,
        "credential_request_count": credential_request_count,
        "human_request_count": human_request_count,
        "blocked_connector_job_count": blocked_connector_job_count,
    }
    open_action_count = sum(evidence.values())
    if open_action_count > 0:
        return readiness_item(
            "operator_actions",
            "operations",
            "Manual operator actions",
            "warning",
            f"{open_action_count} human/operator action(s) are currently open.",
            (
                "Use the dashboard review, credential, connector, and "
                "human-assistance queues to clear blockers before expecting "
                "unattended progress."
            ),
            evidence,
        )
    return readiness_item(
        "operator_actions",
        "operations",
        "Manual operator actions",
        "ready",
        "No open review, credential, human-assistance, or blocked connector action is waiting.",
        evidence=evidence,
    )


@app.get("/operator-actions", response_model=list[OperatorAction])
def list_operator_actions(
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    state_client: StateClient = Depends(get_state_client),
) -> list[OperatorAction]:
    try:
        return sorted_operator_actions(
            build_operator_actions(state_client, project_id=project_id),
        )[:limit]
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(status_code=502, detail="State service unavailable") from error


def build_operator_actions(
    state_client: StateClient,
    *,
    project_id: str | None = None,
) -> list[OperatorAction]:
    actions: list[OperatorAction] = []
    actions.extend(
        task_review_operator_action(task)
        for task in state_client.list_task_review_queue(project_id=project_id)
    )
    actions.extend(
        credential_access_operator_action(request)
        for request in state_client.list_credential_access_requests(
            project_id=project_id,
            status=ApprovalStatus.requested.value,
        )
    )
    actions.extend(
        human_assistance_operator_action(request)
        for request in state_client.list_human_assistance_requests(
            project_id=project_id,
            status=HumanAssistanceStatus.requested.value,
        )
    )
    actions.extend(
        connector_job_operator_action(job)
        for job in state_client.list_connector_jobs(
            project_id=project_id,
            last_run_status=ConnectorJobRunStatus.blocked.value,
        )
    )
    return actions


def task_review_operator_action(task: TaskRecord) -> OperatorAction:
    priority = Priority.high if task.status == TaskStatus.blocked else Priority.medium
    reason = task.dead_letter_reason or task_review_operator_reason(task)
    return OperatorAction(
        id=f"operator_action_task_review_{task.id}",
        kind="task_review",
        title=task.title,
        reason=reason,
        recommended_action="Retry, cancel, or update the task from the review queue.",
        priority=priority,
        status=str(task.status),
        target_id=task.id,
        project_id=task.project_id,
        task_id=task.id,
        agent_id=task.assigned_agent_id,
        created_at=task.dead_lettered_at or task.created_at,
        evidence={
            "attempt_count": task.attempt_count,
            "max_attempts": task.max_attempts,
            "required_tools": task.required_tools,
            "retry_after_at": task.retry_after_at,
        },
    )


def task_review_operator_reason(task: TaskRecord) -> str:
    if task.result and isinstance(task.result.get("error"), str):
        return str(task.result["error"])
    return f"Task is {task.status}; a human or manager decision is required."


def credential_access_operator_action(
    request: CredentialAccessRequest,
) -> OperatorAction:
    return OperatorAction(
        id=f"operator_action_credential_access_{request.id}",
        kind="credential_access",
        title=f"{request.tool_name} credential access",
        reason=request.reason,
        recommended_action="Approve or reject the credential request; apply a grant if approved.",
        priority=Priority.high,
        status=str(request.status),
        target_id=request.id,
        project_id=request.project_id,
        task_id=request.task_id,
        agent_id=request.agent_id,
        service_id=request.candidate_service_ids[0] if request.candidate_service_ids else None,
        created_at=request.created_at,
        evidence={
            "tool_name": request.tool_name,
            "requested_scopes": request.requested_scopes,
            "candidate_service_ids": request.candidate_service_ids,
        },
    )


def human_assistance_operator_action(
    request: HumanAssistanceRequest,
) -> OperatorAction:
    return OperatorAction(
        id=f"operator_action_human_assistance_{request.id}",
        kind="human_assistance",
        title=request.title,
        reason=request.description or f"{request.kind} input is required.",
        recommended_action=(
            "Answer or dismiss the human assistance request, then continue the task."
        ),
        priority=request.urgency,
        status=str(request.status),
        target_id=request.id,
        project_id=request.project_id,
        task_id=request.task_id,
        agent_id=request.agent_id,
        created_at=request.created_at,
        evidence={
            "kind": request.kind,
            "urgency": request.urgency,
            "request_evidence": request.evidence,
        },
    )


def connector_job_operator_action(job: ConnectorJobRecord) -> OperatorAction:
    return OperatorAction(
        id=f"operator_action_connector_job_{job.id}",
        kind="connector_job_review",
        title=job.purpose,
        reason="Latest connector job run is blocked and needs human review.",
        recommended_action=(
            "Inspect the blocked run, resolve the blocker, then resume or stop the job."
        ),
        priority=Priority.high,
        status=ConnectorJobRunStatus.blocked.value,
        target_id=job.id,
        project_id=job.project_id,
        task_id=job.task_id,
        agent_id=job.owner_agent_id,
        service_id=job.service_id,
        created_at=job.updated_at,
        evidence={
            "job_status": job.status,
            "kind": job.kind,
            "next_run_at": job.next_run_at,
            "metadata": job.metadata,
        },
    )


def sorted_operator_actions(actions: list[OperatorAction]) -> list[OperatorAction]:
    priority_rank = {
        Priority.critical: 0,
        Priority.high: 1,
        Priority.medium: 2,
        Priority.low: 3,
    }
    return sorted(
        actions,
        key=lambda action: (
            priority_rank.get(Priority(action.priority), 4),
            action.created_at,
            action.kind,
            action.id,
        ),
    )


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


def execute_web_extract_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_web_extract_tool(tool_call, state_client=state_client)


def execute_connector_job_create_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_connector_job_create_tool(
        tool_call,
        state_client=state_client,
        trace_id=trace_id,
    )


def execute_connector_job_stop_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_connector_job_stop_tool(
        tool_call,
        state_client=state_client,
        trace_id=trace_id,
    )


def execute_connector_job_list_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_connector_job_list_tool(
        tool_call,
        state_client=state_client,
    )


def execute_human_assistance_request_adapter(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    return execute_human_assistance_request_tool(
        tool_call,
        state_client=state_client,
        headers=headers,
        trace_id=trace_id,
    )


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


def execute_web_extract_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
) -> dict[str, object]:
    url = web_fetch_url_argument(tool_call)
    max_bytes = web_fetch_max_bytes_argument(tool_call)
    provider = web_extract_provider_argument(tool_call, state_client)
    if provider == "local_fetch":
        return extract_with_local_fetch(url, max_bytes=max_bytes)
    if provider == "local_playwright":
        return extract_with_local_playwright(url, max_bytes=max_bytes)
    if provider == "firecrawl":
        return extract_with_firecrawl(url, max_bytes=max_bytes)
    if provider == "browserless":
        return extract_with_browserless(url, max_bytes=max_bytes)
    raise HTTPException(status_code=400, detail=f"Unsupported web.extract provider: {provider}")


def extract_with_local_fetch(url: str, *, max_bytes: int) -> dict[str, object]:
    fetch_result = fetch_http_url(url, max_bytes=max_bytes)
    return {
        "executed": True,
        "adapter": "web.extract",
        "provider": "local_fetch",
        "url": fetch_result["url"],
        "final_url": fetch_result["final_url"],
        "status_code": fetch_result["status_code"],
        "content_type": fetch_result["content_type"],
        "bytes_read": fetch_result["bytes_read"],
        "truncated": fetch_result["truncated"],
        "title": fetch_result["title"],
        "markdown": fetch_result["text_excerpt"],
        "metadata": {"source_adapter": "web.fetch"},
    }


def extract_with_local_playwright(url: str, *, max_bytes: int) -> dict[str, object]:
    page_result = fetch_with_local_playwright(url)
    html = string_payload_value(page_result.get("html")) or ""
    title, excerpt = summarize_fetched_text(html)
    markdown, truncated = truncate_text_bytes(excerpt, max_bytes=max_bytes)
    status_code = integer_payload_value(page_result.get("status_code"), default=0)
    output = {
        "executed": True,
        "adapter": "web.extract",
        "provider": "local_playwright",
        "url": url,
        "final_url": string_payload_value(page_result.get("final_url")) or url,
        "status_code": status_code,
        "content_type": "text/html",
        "bytes_read": len(markdown.encode("utf-8")),
        "truncated": truncated,
        "title": string_payload_value(page_result.get("title")) or title,
        "markdown": markdown,
        "metadata": {
            "browser": "chromium",
            "wait_until": settings.web_extract_playwright_wait_until,
        },
    }
    return apply_web_extraction_blocker(
        output,
        provider="local_playwright",
        url=url,
        status_code=status_code,
        title=string_payload_value(output.get("title")) or "",
        markdown=markdown,
        html=html,
    )


def apply_web_extraction_blocker(
    output: dict[str, object],
    *,
    provider: WebExtractionProvider,
    url: str,
    status_code: int,
    title: str,
    markdown: str,
    html: str,
) -> dict[str, object]:
    blocked = web_extraction_blocker(
        status_code=status_code,
        title=title,
        markdown=markdown,
    )
    if blocked is not None:
        output.update(blocked)
        output["provider_escalation_options"] = web_provider_escalation_options(
            current_provider=provider,
            blocked_reason=string_payload_value(blocked.get("blocked_reason")) or "blocked",
        )
        output["review_evidence"] = web_blocked_review_evidence(
            provider=provider,
            url=url,
            final_url=string_payload_value(output.get("final_url")) or url,
            status_code=status_code,
            title=title,
            markdown=markdown,
            html=html,
            block_signals=blocked["block_signals"],
        )
        metadata = output["metadata"]
        if isinstance(metadata, dict):
            metadata["requires_human_review"] = True
            metadata["block_signals"] = blocked["block_signals"]
    return output


def web_extraction_blocker(
    *,
    status_code: int,
    title: str,
    markdown: str,
) -> dict[str, object] | None:
    if status_code in {401, 403}:
        return web_blocked_result("http_access_denied", ("http_status",))
    if status_code == 429:
        return web_blocked_result("rate_limited_or_bot_check", ("http_status",))

    normalized_title = title.casefold()
    normalized_text = f"{title}\n{markdown}".casefold()
    signal_sets: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "captcha_or_human_verification",
            (
                "captcha",
                "verify you are human",
                "verify you're human",
                "checking your browser",
                "cloudflare ray id",
                "are you a robot",
            ),
        ),
        (
            "authentication_required",
            (
                "sign in to continue",
                "log in to continue",
                "login required",
                "please sign in",
                "please log in",
            ),
        ),
    )
    for reason, phrases in signal_sets:
        matches = tuple(
            phrase
            for phrase in phrases
            if phrase in normalized_text or phrase in normalized_title
        )
        if matches:
            return web_blocked_result(reason, matches)
    return None


def web_blocked_result(reason: str, signals: tuple[str, ...]) -> dict[str, object]:
    return {
        "tool_status": TaskStatus.blocked,
        "blocked_reason": reason,
        "requires_human_review": True,
        "block_signals": list(signals),
        "recommended_action": "review_provider_escalation",
    }


def web_provider_escalation_options(
    *,
    current_provider: str,
    blocked_reason: str,
) -> list[dict[str, object]]:
    provider_ids = (
        "firecrawl",
        "browserbase",
        "browserless",
        "brightdata_web_unlocker",
        "brightdata_browser_api",
        "scrapingbee",
        "zyte",
        "apify",
    )
    return [
        web_provider_escalation_option(
            manifest,
            current_provider=current_provider,
            blocked_reason=blocked_reason,
        )
        for provider_id in provider_ids
        if (manifest := WEB_PROVIDER_MANIFESTS.get(provider_id)) is not None
    ]


def web_provider_escalation_option(
    manifest: WebProviderManifest,
    *,
    current_provider: str,
    blocked_reason: str,
) -> dict[str, object]:
    response = manifest.as_response()
    configured = bool(response["configured"])
    action_required: list[str] = []
    if not manifest.implemented:
        action_required.append("provider_adapter_not_implemented")
    if manifest.requires_api_key and not configured:
        action_required.append("configure_api_key")
    if manifest.requires_human_approval:
        action_required.append("human_approval_required")
    return {
        "provider_id": manifest.provider_id,
        "name": manifest.name,
        "category": manifest.category,
        "implemented": manifest.implemented,
        "configured": configured,
        "requires_api_key": manifest.requires_api_key,
        "api_key_env_var": manifest.api_key_env_var,
        "risk_level": manifest.risk_level,
        "requires_human_approval": manifest.requires_human_approval,
        "action_required": action_required,
        "reason": web_provider_escalation_reason(
            manifest,
            current_provider=current_provider,
            blocked_reason=blocked_reason,
        ),
    }


def web_provider_escalation_reason(
    manifest: WebProviderManifest,
    *,
    current_provider: str,
    blocked_reason: str,
) -> str:
    if manifest.provider_id == "firecrawl":
        return "Try managed markdown extraction when local browser output is blocked."
    if manifest.provider_id in {"browserbase", "browserless"}:
        return "Use a cloud browser session when local browser execution is insufficient."
    if manifest.provider_id.startswith("brightdata"):
        return "Use only with explicit approval for high-risk anti-bot or proxy-heavy pages."
    return (
        f"Candidate escalation from {current_provider} after {blocked_reason}; "
        "requires provider-specific review before use."
    )


def web_blocked_review_evidence(
    *,
    provider: str,
    url: str,
    final_url: str,
    status_code: int,
    title: str,
    markdown: str,
    html: str,
    block_signals: object,
) -> dict[str, object]:
    markdown_excerpt, markdown_truncated = truncate_text_bytes(
        markdown,
        max_bytes=settings.web_extract_review_evidence_max_bytes,
    )
    html_excerpt, html_truncated = truncate_text_bytes(
        html,
        max_bytes=settings.web_extract_review_evidence_max_bytes,
    )
    signals = block_signals if isinstance(block_signals, list) else []
    return {
        "kind": "web_extract_block",
        "provider": provider,
        "url": url,
        "final_url": final_url,
        "status_code": status_code,
        "title": title,
        "content_type": "text/html",
        "block_signals": signals,
        "markdown_excerpt": markdown_excerpt,
        "html_excerpt": html_excerpt,
        "truncated": markdown_truncated or html_truncated,
        "max_bytes": settings.web_extract_review_evidence_max_bytes,
    }


def fetch_with_local_playwright(url: str) -> dict[str, object]:
    try:
        playwright_sync_api = importlib.import_module("playwright.sync_api")
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="Playwright is not installed for local_playwright",
        ) from error
    sync_playwright = playwright_sync_api.sync_playwright
    playwright_error = playwright_sync_api.Error
    playwright_timeout_error = playwright_sync_api.TimeoutError

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent="Synarch/0.1 web.extract")
                response = page.goto(
                    url,
                    wait_until=settings.web_extract_playwright_wait_until,
                    timeout=settings.web_extract_playwright_timeout_seconds * 1000,
                )
                html = page.content()
                return {
                    "final_url": page.url,
                    "status_code": response.status if response is not None else None,
                    "title": page.title() or None,
                    "html": html,
                }
            finally:
                browser.close()
    except playwright_timeout_error as error:
        raise HTTPException(status_code=504, detail="local_playwright timed out") from error
    except playwright_error as error:
        raise HTTPException(status_code=502, detail="local_playwright request failed") from error


def extract_with_firecrawl(url: str, *, max_bytes: int) -> dict[str, object]:
    api_key = os.getenv(settings.firecrawl_api_key_env_var)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"{settings.firecrawl_api_key_env_var} is not configured",
        )

    try:
        response = httpx.post(
            f"{settings.firecrawl_base_url.rstrip('/')}/v2/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": ["markdown"]},
            timeout=settings.firecrawl_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="firecrawl request failed") from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "provider_status": response.status_code,
                "error": web_response_detail(response),
            },
        )

    body = response.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="firecrawl returned an invalid response")
    data = body.get("data", body)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="firecrawl returned an invalid data payload")
    markdown = string_payload_value(data.get("markdown")) or string_payload_value(
        data.get("content")
    )
    markdown, truncated = truncate_text_bytes(markdown or "", max_bytes=max_bytes)
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    title = string_payload_value(metadata.get("title")) or string_payload_value(data.get("title"))
    return {
        "executed": True,
        "adapter": "web.extract",
        "provider": "firecrawl",
        "url": url,
        "final_url": string_payload_value(metadata.get("sourceURL")) or url,
        "status_code": integer_payload_value(data.get("statusCode"), default=response.status_code),
        "content_type": "text/markdown",
        "bytes_read": len(markdown.encode("utf-8")),
        "truncated": truncated,
        "title": title,
        "markdown": markdown,
        "metadata": metadata,
    }


def extract_with_browserless(url: str, *, max_bytes: int) -> dict[str, object]:
    api_key = os.getenv(settings.browserless_api_key_env_var)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"{settings.browserless_api_key_env_var} is not configured",
        )

    try:
        response = httpx.post(
            f"{settings.browserless_base_url.rstrip('/')}/content",
            params={"token": api_key},
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
            },
            json={"url": url},
            timeout=settings.browserless_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="browserless request failed") from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "provider_status": response.status_code,
                "error": web_response_detail(response),
            },
        )

    html = response.text
    parsed_title, excerpt = summarize_fetched_text(html)
    title = parsed_title or ""
    markdown, truncated = truncate_text_bytes(excerpt, max_bytes=max_bytes)
    status_code = response.status_code
    output = {
        "executed": True,
        "adapter": "web.extract",
        "provider": "browserless",
        "url": url,
        "final_url": url,
        "status_code": status_code,
        "content_type": response.headers.get("content-type", "text/html"),
        "bytes_read": len(markdown.encode("utf-8")),
        "truncated": truncated,
        "title": title,
        "markdown": markdown,
        "metadata": {"source_adapter": "browserless.content"},
    }
    return apply_web_extraction_blocker(
        output,
        provider="browserless",
        url=url,
        status_code=status_code,
        title=title,
        markdown=markdown,
        html=html,
    )


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


def web_extract_provider_argument(
    tool_call: ToolCallRequest,
    state_client: StateClient,
) -> WebExtractionProvider:
    raw_provider = string_argument(tool_call, "provider")
    service_provider = web_provider_from_service(tool_call.service_id, state_client)
    provider = raw_provider or service_provider or settings.web_extract_default_provider
    if (
        raw_provider is not None
        and service_provider is not None
        and raw_provider != service_provider
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "web.extract provider does not match selected service: "
                f"{raw_provider} via {tool_call.service_id}"
            ),
        )
    if provider == "local_fetch":
        return "local_fetch"
    if provider == "local_playwright":
        return "local_playwright"
    if provider == "firecrawl":
        return "firecrawl"
    if provider == "browserless":
        return "browserless"
    raise HTTPException(
        status_code=400,
        detail=(
            "web.extract provider must be one of: local_fetch, local_playwright, "
            "firecrawl, browserless"
        ),
    )


def web_provider_from_service(
    service_id: str | None,
    state_client: StateClient,
) -> str | None:
    if service_id is None:
        return None
    for service in state_client.list_services(enabled=True):
        if service.id != service_id:
            continue
        provider = service.metadata.get("web_provider")
        return provider if isinstance(provider, str) and provider.strip() else None
    return None


def string_payload_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def integer_payload_value(value: object, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def truncate_text_bytes(text: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def web_response_detail(response: httpx.Response) -> object:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict):
        return body.get("error", body)
    return body


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


def execute_connector_job_create_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    trace_id: str,
) -> dict[str, object]:
    service_id = tool_call.service_id
    if service_id is None:
        raise HTTPException(
            status_code=400,
            detail="connector.job.create requires selected service_id",
        )

    kind = connector_job_kind_argument(tool_call)
    job = ConnectorJobRecord(
        id=string_argument(tool_call, "id") or f"connector-job-{uuid4().hex[:12]}",
        service_id=service_id,
        project_id=tool_call.project_id,
        task_id=tool_call.task_id,
        owner_agent_id=tool_call.agent_id,
        kind=kind,
        schedule=string_argument(tool_call, "schedule"),
        webhook_path=string_argument(tool_call, "webhook_path"),
        purpose=required_string_argument(tool_call, "purpose", "connector.job.create"),
        created_by_type=ActorType.agent,
        created_by_id=tool_call.agent_id,
        metadata=connector_job_metadata_argument(tool_call, trace_id),
    )
    result = state_client.create_connector_job(
        job,
        headers=connector_job_operator_headers(ActorType.agent, tool_call.agent_id, trace_id),
    )
    return {
        "executed": True,
        "adapter": "connector.job.create",
        "connector_job_id": result.job.id,
        "service_id": result.job.service_id,
        "kind": result.job.kind,
        "status": result.job.status,
        "connector_job_event_id": result.event.id,
        "connector_job_audit_id": result.audit_log.id if result.audit_log is not None else None,
        "run_tool_name": result.job.metadata.get("tool_name"),
    }


def execute_connector_job_stop_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    trace_id: str,
) -> dict[str, object]:
    job_id = required_string_argument(tool_call, "job_id", "connector.job.stop")
    reason = required_string_argument(tool_call, "reason", "connector.job.stop")
    job = state_client.get_connector_job(job_id)
    if job.owner_agent_id != tool_call.agent_id:
        raise HTTPException(
            status_code=403,
            detail="Connector job is not owned by requesting agent",
        )
    if tool_call.service_id is not None and job.service_id != tool_call.service_id:
        raise HTTPException(
            status_code=403,
            detail="Connector job does not belong to selected service",
        )

    result = state_client.stop_connector_job(
        job.id,
        ConnectorJobStopRequest(
            stopped_by_type=ActorType.agent,
            stopped_by_id=tool_call.agent_id,
            reason=reason,
        ),
        headers=connector_job_operator_headers(ActorType.agent, tool_call.agent_id, trace_id),
    )
    return {
        "executed": True,
        "adapter": "connector.job.stop",
        "connector_job_id": result.job.id,
        "service_id": result.job.service_id,
        "status": result.job.status,
        "connector_job_event_id": result.event.id,
        "connector_job_audit_id": result.audit_log.id if result.audit_log is not None else None,
    }


def execute_connector_job_list_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
) -> dict[str, object]:
    if tool_call.service_id is None:
        raise HTTPException(
            status_code=400,
            detail="connector.job.list requires selected service_id",
        )

    raw_kind = string_argument(tool_call, "kind")
    kind = connector_job_optional_kind_argument(
        tool_call,
        "connector.job.list",
        strict=False,
    )
    ignored_filters: dict[str, str] = {}
    if raw_kind is not None and kind is None:
        ignored_filters["kind"] = raw_kind

    jobs = state_client.list_connector_jobs(
        service_id=tool_call.service_id,
        project_id=string_argument(tool_call, "project_id") or tool_call.project_id,
        task_id=string_argument(tool_call, "task_id"),
        owner_agent_id=tool_call.agent_id,
        kind=kind,
        status=connector_job_optional_status_argument(tool_call, "connector.job.list"),
    )
    limit = connector_job_list_limit_argument(tool_call)
    limited_jobs = jobs[:limit]
    return {
        "executed": True,
        "adapter": "connector.job.list",
        "service_id": tool_call.service_id,
        "owner_agent_id": tool_call.agent_id,
        "count": len(limited_jobs),
        "total_count": len(jobs),
        "ignored_filters": ignored_filters,
        "connector_jobs": [
            job.model_dump(mode="json")
            for job in limited_jobs
        ],
    }


def execute_human_assistance_request_tool(
    tool_call: ToolCallRequest,
    *,
    state_client: StateClient,
    headers: dict[str, str],
    trace_id: str,
) -> dict[str, object]:
    project_id = tool_call.project_id or string_argument(tool_call, "project_id")
    if project_id is None:
        raise HTTPException(
            status_code=400,
            detail="human.assistance.request requires project_id",
        )
    assistance_request = HumanAssistanceRequest(
        id=string_argument(tool_call, "id") or human_assistance_request_id(tool_call),
        project_id=project_id,
        task_id=tool_call.task_id or string_argument(tool_call, "task_id"),
        agent_id=tool_call.agent_id,
        kind=human_assistance_kind_argument(tool_call),
        title=required_string_argument(tool_call, "title", "human.assistance.request"),
        description=required_string_argument(
            tool_call,
            "description",
            "human.assistance.request",
        ),
        urgency=human_assistance_urgency_argument(tool_call),
        evidence=human_assistance_evidence_argument(tool_call, trace_id),
        requested_by_type=ActorType.agent,
        requested_by_id=tool_call.agent_id,
    )
    try:
        record = state_client.create_human_assistance_request(
            assistance_request,
            headers=headers,
        )
    except StateServiceRequestError as error:
        if error.status_code != 409:
            raise
        record = state_client.get_human_assistance_request(assistance_request.id)
    return {
        "executed": True,
        "adapter": "human.assistance.request",
        "tool_status": TaskStatus.blocked,
        "blocked_reason": "human_assistance_requested",
        "requires_human_review": True,
        "recommended_action": "Answer the human assistance request, then retry or update the task.",
        "human_assistance_request": record.model_dump(mode="json"),
        "human_assistance_request_id": record.id,
        "kind": record.kind,
        "status": record.status,
    }


def human_assistance_request_id(tool_call: ToolCallRequest) -> str:
    task_or_project = tool_call.task_id or tool_call.project_id or "project"
    kind = string_argument(tool_call, "kind") or HumanAssistanceKind.other.value
    title = string_argument(tool_call, "title") or "request"
    raw = f"{task_or_project}-{kind}-{title}"
    return f"human_assistance_{safe_identifier_fragment(raw, max_length=96)}"


def human_assistance_kind_argument(tool_call: ToolCallRequest) -> HumanAssistanceKind:
    raw_kind = string_argument(tool_call, "kind") or HumanAssistanceKind.other.value
    try:
        return HumanAssistanceKind(raw_kind)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=(
                "human.assistance.request kind must be one of: "
                f"{', '.join(HumanAssistanceKind)}"
            ),
        ) from error


def human_assistance_urgency_argument(tool_call: ToolCallRequest) -> str:
    raw_urgency = string_argument(tool_call, "urgency")
    if raw_urgency is None:
        return "medium"
    if raw_urgency not in {"low", "medium", "high", "critical"}:
        raise HTTPException(
            status_code=400,
            detail="human.assistance.request urgency must be low, medium, high, or critical",
        )
    return raw_urgency


def human_assistance_evidence_argument(
    tool_call: ToolCallRequest,
    trace_id: str,
) -> dict[str, object]:
    raw_evidence = tool_call.arguments.get("evidence", {})
    if not isinstance(raw_evidence, dict):
        raise HTTPException(
            status_code=400,
            detail="human.assistance.request evidence must be an object",
        )
    return {
        **raw_evidence,
        "source_trace_id": trace_id,
        "tool_reason": tool_call.reason,
        "service_id": tool_call.service_id,
    }


def connector_job_kind_argument(tool_call: ToolCallRequest) -> ConnectorJobKind:
    raw_kind = required_string_argument(tool_call, "kind", "connector.job.create")
    try:
        return ConnectorJobKind(raw_kind)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"connector.job.create kind must be one of: {', '.join(ConnectorJobKind)}",
        ) from error


def connector_job_optional_kind_argument(
    tool_call: ToolCallRequest,
    adapter: str,
    *,
    strict: bool = True,
) -> ConnectorJobKind | None:
    raw_kind = string_argument(tool_call, "kind")
    if raw_kind is None:
        return None
    try:
        return ConnectorJobKind(raw_kind)
    except ValueError as error:
        if not strict:
            return None
        raise HTTPException(
            status_code=400,
            detail=f"{adapter} kind must be one of: {', '.join(ConnectorJobKind)}",
        ) from error


def connector_job_optional_status_argument(
    tool_call: ToolCallRequest,
    adapter: str,
) -> ConnectorJobStatus | None:
    raw_status = string_argument(tool_call, "status")
    if raw_status is None:
        return None
    try:
        return ConnectorJobStatus(raw_status)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"{adapter} status must be one of: {', '.join(ConnectorJobStatus)}",
        ) from error


def connector_job_list_limit_argument(tool_call: ToolCallRequest) -> int:
    raw_limit = tool_call.arguments.get("limit", 20)
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
        raise HTTPException(
            status_code=400,
            detail="connector.job.list limit must be an integer",
        )
    if raw_limit < 1 or raw_limit > 50:
        raise HTTPException(
            status_code=400,
            detail="connector.job.list limit must be between 1 and 50",
        )
    return int(raw_limit)


def connector_job_metadata_argument(
    tool_call: ToolCallRequest,
    trace_id: str,
) -> dict[str, object]:
    raw_metadata = tool_call.arguments.get("metadata", {})
    if not isinstance(raw_metadata, dict):
        raise HTTPException(
            status_code=400,
            detail="connector.job.create metadata must be an object",
        )
    raw_run_arguments = tool_call.arguments.get("run_arguments", {})
    if not isinstance(raw_run_arguments, dict):
        raise HTTPException(
            status_code=400,
            detail="connector.job.create run_arguments must be an object",
        )

    return {
        **raw_metadata,
        "tool_name": required_string_argument(
            tool_call,
            "run_tool_name",
            "connector.job.create",
        ),
        "arguments": raw_run_arguments,
        "reason": string_argument(tool_call, "run_reason") or tool_call.reason,
        "created_by_tool_call": "connector.job.create",
        "source_trace_id": trace_id,
    }


TOOL_ADAPTERS: dict[str, ToolAdapter] = {
    "connector.job.create": execute_connector_job_create_adapter,
    "connector.job.list": execute_connector_job_list_adapter,
    "connector.job.stop": execute_connector_job_stop_adapter,
    "event.emit": execute_event_emit_adapter,
    "human.assistance.request": execute_human_assistance_request_adapter,
    "web.extract": execute_web_extract_adapter,
    "web.fetch": execute_web_fetch_adapter,
}

WEB_PROVIDER_MANIFESTS: dict[str, WebProviderManifest] = {
    "apify": WebProviderManifest(
        provider_id="apify",
        name="Apify",
        category="scraping_platform",
        implemented=False,
        requires_api_key=True,
        api_key_env_var="APIFY_TOKEN",
        capabilities=("actors", "browser", "crawler", "proxy"),
        notes="Candidate for marketplace actors and heavier scraping workflows.",
        risk_level="medium",
        requires_human_approval=True,
    ),
    "brightdata_browser_api": WebProviderManifest(
        provider_id="brightdata_browser_api",
        name="Bright Data Browser API",
        category="unblocking_api",
        implemented=False,
        requires_api_key=True,
        api_key_env_var="BRIGHTDATA_API_KEY",
        capabilities=("browser", "playwright", "proxy", "captcha"),
        notes="Candidate for paid browser automation on anti-bot-heavy sites.",
        risk_level="high",
        requires_human_approval=True,
    ),
    "brightdata_web_unlocker": WebProviderManifest(
        provider_id="brightdata_web_unlocker",
        name="Bright Data Web Unlocker",
        category="unblocking_api",
        implemented=False,
        requires_api_key=True,
        api_key_env_var="BRIGHTDATA_API_KEY",
        capabilities=("unblock", "proxy", "captcha", "html"),
        notes="Candidate for paid unblocking when normal HTTP/browser extraction is blocked.",
        risk_level="high",
        requires_human_approval=True,
    ),
    "browserbase": WebProviderManifest(
        provider_id="browserbase",
        name="Browserbase",
        category="cloud_browser",
        implemented=False,
        requires_api_key=True,
        api_key_env_var="BROWSERBASE_API_KEY",
        capabilities=("playwright", "sessions", "screenshots"),
        notes="Candidate cloud Playwright provider for persistent browser sessions.",
        risk_level="medium",
        requires_human_approval=True,
    ),
    "browserless": WebProviderManifest(
        provider_id="browserless",
        name="Browserless",
        category="cloud_browser",
        implemented=True,
        requires_api_key=True,
        api_key_env_var="BROWSERLESS_API_KEY",
        capabilities=("content", "playwright", "puppeteer", "sessions", "captcha"),
        notes=(
            "Implemented for web.extract through Browserless /content when "
            "BROWSERLESS_API_KEY is configured."
        ),
        risk_level="high",
        requires_human_approval=True,
    ),
    "crawl4ai": WebProviderManifest(
        provider_id="crawl4ai",
        name="Crawl4AI",
        category="local_extraction",
        implemented=False,
        requires_api_key=False,
        api_key_env_var=None,
        capabilities=("crawl", "markdown", "llm_context"),
        notes="Candidate open source extractor once local crawler dependencies are added.",
    ),
    "firecrawl": WebProviderManifest(
        provider_id="firecrawl",
        name="Firecrawl",
        category="extraction_api",
        implemented=True,
        requires_api_key=True,
        api_key_env_var=settings.firecrawl_api_key_env_var,
        capabilities=("scrape", "markdown"),
        notes="Implemented for web.extract through FIRECRAWL_API_KEY.",
        risk_level="medium",
    ),
    "local_fetch": WebProviderManifest(
        provider_id="local_fetch",
        name="Local HTTP fetch",
        category="local_fetch",
        implemented=True,
        requires_api_key=False,
        api_key_env_var=None,
        capabilities=("http", "html_summary"),
        notes="Implemented no-key fallback. It does not execute JavaScript.",
    ),
    "local_playwright": WebProviderManifest(
        provider_id="local_playwright",
        name="Local Playwright",
        category="local_browser",
        implemented=True,
        requires_api_key=False,
        api_key_env_var=None,
        capabilities=("browser", "javascript", "screenshots", "forms"),
        notes="Implemented for no-key Chromium extraction when Playwright browsers are installed.",
        python_module="playwright",
        risk_level="medium",
    ),
    "scrapingbee": WebProviderManifest(
        provider_id="scrapingbee",
        name="ScrapingBee",
        category="scraping_api",
        implemented=False,
        requires_api_key=True,
        api_key_env_var="SCRAPINGBEE_API_KEY",
        capabilities=("javascript", "proxy", "screenshots"),
        notes="Candidate for paid scraping API workflows.",
        risk_level="medium",
        requires_human_approval=True,
    ),
    "zyte": WebProviderManifest(
        provider_id="zyte",
        name="Zyte API",
        category="scraping_api",
        implemented=False,
        requires_api_key=True,
        api_key_env_var="ZYTE_API_KEY",
        capabilities=("browser", "extraction", "proxy"),
        notes="Candidate for paid browser/rendering and extraction workflows.",
        risk_level="medium",
        requires_human_approval=True,
    ),
}

TOOL_ADAPTER_MANIFESTS: dict[str, ToolAdapterManifest] = {
    "connector.job.create": ToolAdapterManifest(
        tool_name="connector.job.create",
        adapter="connector.job.create",
        required_arguments=("kind", "purpose", "run_tool_name"),
        optional_arguments=(
            "id",
            "schedule",
            "webhook_path",
            "run_arguments",
            "run_reason",
            "metadata",
        ),
        risk_level="medium",
        audit_required=True,
    ),
    "connector.job.list": ToolAdapterManifest(
        tool_name="connector.job.list",
        adapter="connector.job.list",
        optional_arguments=("project_id", "task_id", "kind", "status", "limit"),
        risk_level="low",
        audit_required=True,
    ),
    "connector.job.stop": ToolAdapterManifest(
        tool_name="connector.job.stop",
        adapter="connector.job.stop",
        required_arguments=("job_id", "reason"),
        risk_level="medium",
        audit_required=True,
    ),
    "event.emit": ToolAdapterManifest(
        tool_name="event.emit",
        adapter="event.emit",
        required_arguments=("type",),
        optional_arguments=("target", "payload"),
        risk_level="low",
    ),
    "human.assistance.request": ToolAdapterManifest(
        tool_name="human.assistance.request",
        adapter="human.assistance.request",
        required_arguments=("kind", "title", "description"),
        optional_arguments=("id", "project_id", "task_id", "urgency", "evidence"),
        risk_level="medium",
        audit_required=True,
    ),
    "web.fetch": ToolAdapterManifest(
        tool_name="web.fetch",
        adapter="web.fetch",
        required_arguments=("url",),
        optional_arguments=("max_bytes",),
        risk_level="medium",
        network_access=True,
    ),
    "web.extract": ToolAdapterManifest(
        tool_name="web.extract",
        adapter="web.extract",
        required_arguments=("url",),
        optional_arguments=("provider", "max_bytes"),
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
        raise HTTPException(status_code=400, detail=f"Tool argument {key} must be a string")
    return raw_value.strip() or None


def required_string_argument(
    tool_call: ToolCallRequest,
    key: str,
    adapter: str,
) -> str:
    value = string_argument(tool_call, key)
    if value is None:
        raise HTTPException(
            status_code=400,
            detail=f"{adapter} requires string argument: {key}",
        )
    return value


def tool_call_event(
    tool_call: ToolCallRequest,
    event_type: EventType,
    trace_id: str,
    *,
    error: str | None = None,
    extra_payload: dict[str, object] | None = None,
) -> EventRecord:
    payload = tool_call_payload(tool_call)
    if error is not None:
        payload["error"] = error
    if extra_payload is not None:
        payload.update(extra_payload)
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
    extra_payload: dict[str, object] | None = None,
) -> AuditLogRecord:
    payload = tool_call_payload(tool_call)
    if error is not None:
        payload["error"] = error
    if extra_payload is not None:
        payload.update(extra_payload)
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


@app.get("/projects/briefs", response_model=list[ProjectBrief])
def list_project_briefs(
    project_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    state_client: StateClient = Depends(get_state_client),
) -> list[ProjectBrief]:
    try:
        projects = (
            [state_client.get_project(project_id)]
            if project_id is not None
            else state_client.list_projects()
        )
        events = state_client.list_events()
        briefs: list[ProjectBrief] = []
        for project in projects[:limit]:
            tasks = state_client.list_tasks(project_id=project.id)
            task_ids = {task.id for task in tasks}
            project_events = project_latest_events(events, project.id, task_ids)
            blocked_connector_jobs = sorted_connector_jobs(
                state_client.list_connector_jobs(
                    project_id=project.id,
                    last_run_status=ConnectorJobRunStatus.blocked,
                )
            )
            human_assistance_requests = sorted_human_assistance_requests(
                state_client.list_human_assistance_requests(
                    project_id=project.id,
                    status=HumanAssistanceStatus.requested,
                )
            )
            briefs.append(
                build_project_brief(
                    project=project,
                    tasks=tasks,
                    blocked_connector_jobs=blocked_connector_jobs,
                    human_assistance_requests=human_assistance_requests,
                    events=project_events,
                )
            )
        return briefs
    except StateServiceRequestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except StateServiceUnavailable as error:
        raise HTTPException(
            status_code=502,
            detail="Project brief dependency unavailable",
        ) from error


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


def build_project_brief(
    *,
    project: ProjectRecord,
    tasks: list[TaskRecord],
    blocked_connector_jobs: list[ConnectorJobRecord],
    human_assistance_requests: list[HumanAssistanceRequest],
    events: list[EventRecord],
) -> ProjectBrief:
    review_tasks = sorted_review_tasks(tasks)
    next_tasks = sorted_next_tasks(tasks)
    return ProjectBrief(
        project_id=project.id,
        project=project,
        task_counts=task_counts_by_status(tasks),
        next_tasks=next_tasks[:3],
        review_tasks=review_tasks[:3],
        blocked_connector_jobs=blocked_connector_jobs[:3],
        human_assistance_requests=human_assistance_requests[:3],
        latest_events=events[:5],
        reminders=project_brief_reminders(
            next_tasks=next_tasks,
            review_task_count=len(review_tasks),
            blocked_connector_job_count=len(blocked_connector_jobs),
            human_assistance_request_count=len(human_assistance_requests),
        ),
        next_action=project_brief_next_action(
            review_tasks=review_tasks,
            human_assistance_requests=human_assistance_requests,
            blocked_connector_jobs=blocked_connector_jobs,
            next_tasks=next_tasks,
            project=project,
        ),
    )


def task_counts_by_status(tasks: list[TaskRecord]) -> dict[str, int]:
    counts = {status.value: 0 for status in TaskStatus}
    for task in tasks:
        counts[str(task.status)] = counts.get(str(task.status), 0) + 1
    return counts


def sorted_next_tasks(tasks: list[TaskRecord]) -> list[TaskRecord]:
    return sorted(
        [
            task
            for task in tasks
            if task.status in {TaskStatus.running, TaskStatus.queued}
        ],
        key=lambda task: (
            0 if task.status == TaskStatus.running else 1,
            task.sequence,
            task.created_at,
            task.id,
        ),
    )


def sorted_review_tasks(tasks: list[TaskRecord]) -> list[TaskRecord]:
    return sorted(
        [
            task
            for task in tasks
            if task.status in {TaskStatus.blocked, TaskStatus.needs_review}
        ],
        key=lambda task: (
            0 if task.status == TaskStatus.blocked else 1,
            task.sequence,
            task.created_at,
            task.id,
        ),
    )


def sorted_connector_jobs(jobs: list[ConnectorJobRecord]) -> list[ConnectorJobRecord]:
    return sorted(
        jobs,
        key=lambda job: (job.stopped_at or job.updated_at or job.created_at, job.id),
        reverse=True,
    )


def sorted_human_assistance_requests(
    assistance_requests: list[HumanAssistanceRequest],
) -> list[HumanAssistanceRequest]:
    return sorted(
        assistance_requests,
        key=lambda assistance_request: (
            assistance_request.urgency != "critical",
            assistance_request.urgency != "high",
            assistance_request.created_at,
            assistance_request.id,
        ),
    )


def project_latest_events(
    events: list[EventRecord],
    project_id: str,
    task_ids: set[str],
) -> list[EventRecord]:
    return sorted(
        [
            event
            for event in events
            if event_belongs_to_project(event, project_id, task_ids)
        ],
        key=lambda event: (event.timestamp, event.id),
        reverse=True,
    )


def project_brief_reminders(
    *,
    next_tasks: list[TaskRecord],
    review_task_count: int,
    blocked_connector_job_count: int,
    human_assistance_request_count: int,
) -> list[str]:
    reminders: list[str] = []
    if human_assistance_request_count > 0:
        reminders.append(f"Answer {human_assistance_request_count} human assistance request(s).")
    if review_task_count > 0:
        reminders.append(f"Review {review_task_count} blocked or pending task(s).")
    if blocked_connector_job_count > 0:
        reminders.append(f"Review {blocked_connector_job_count} blocked connector job(s).")
    if next_tasks:
        reminders.append(f"Next task: {next_tasks[0].title}.")
    elif (
        review_task_count == 0
        and blocked_connector_job_count == 0
        and human_assistance_request_count == 0
    ):
        reminders.append("No queued next task; split the project into concrete work.")
    return reminders


def project_brief_next_action(
    *,
    review_tasks: list[TaskRecord],
    human_assistance_requests: list[HumanAssistanceRequest],
    blocked_connector_jobs: list[ConnectorJobRecord],
    next_tasks: list[TaskRecord],
    project: ProjectRecord,
) -> ProjectBriefAction:
    if human_assistance_requests:
        assistance_request = human_assistance_requests[0]
        return ProjectBriefAction(
            kind="human_assistance",
            target_id=assistance_request.id,
            title=assistance_request.title,
            reason=(
                f"{assistance_request.kind} request from "
                f"{assistance_request.agent_id}; human input is required."
            ),
        )
    if review_tasks:
        task = review_tasks[0]
        return ProjectBriefAction(
            kind="task_review",
            target_id=task.id,
            title=task.title,
            reason=f"Task is {task.status}; it needs a human or manager decision.",
        )
    if blocked_connector_jobs:
        job = blocked_connector_jobs[0]
        return ProjectBriefAction(
            kind="connector_job_review",
            target_id=job.id,
            title=job.purpose,
            reason="Latest connector job run is blocked and needs review.",
        )
    if next_tasks:
        task = next_tasks[0]
        return ProjectBriefAction(
            kind="task_next",
            target_id=task.id,
            title=task.title,
            reason=f"Task is {task.status} and is the next executable work item.",
        )
    return ProjectBriefAction(
        kind="project_planning",
        target_id=project.id,
        title=project.title,
        reason="Project has no queued work; define or split the next concrete task.",
    )


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


@app.post("/memory-items/compact", response_model=MemoryCompactionResult, status_code=201)
def compact_memory_items(
    compaction_request: MemoryCompactionRequest,
    request: Request,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
) -> MemoryCompactionResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = memory_reviewer_headers(request, trace_id)
    try:
        result = memory_client.compact_memory_items(compaction_request)
        state_client.create_event(
            memory_compacted_event(result, trace_id),
            headers=headers,
        )
        return result
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory compaction dependency unavailable",
        ) from error


@app.post("/memory-items/compact-if-needed", response_model=MemoryCompactionPolicyResult)
def compact_memory_items_if_needed(
    compaction_request: MemoryCompactionPolicyRequest,
    request: Request,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
) -> MemoryCompactionPolicyResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = memory_reviewer_headers(request, trace_id)
    try:
        result = memory_client.compact_memory_items_if_needed(compaction_request)
        if result.compaction is not None:
            state_client.create_event(
                memory_compacted_event(result.compaction, trace_id),
                headers=headers,
            )
        return result
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory compaction policy dependency unavailable",
        ) from error


@app.post("/memory-items/compaction-plan", response_model=MemoryCompactionPlanResult)
def plan_memory_compaction(
    compaction_request: MemoryCompactionPlanRequest,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
) -> MemoryCompactionPlanResult:
    try:
        request_with_active_scopes = compaction_request
        if compaction_request.scopes is None:
            request_with_active_scopes = compaction_request.model_copy(
                update={
                    "scopes": active_project_memory_scopes(
                        state_client,
                        project_id=compaction_request.project_id,
                    )
                }
            )
        return memory_client.plan_memory_compaction(request_with_active_scopes)
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory compaction plan dependency unavailable",
        ) from error


def active_project_memory_scopes(
    state_client: StateClient,
    *,
    project_id: str | None = None,
) -> list[str]:
    seen: set[str] = set()
    scopes: list[str] = []
    for workspace in state_client.list_project_workspaces(project_id=project_id, active=True):
        if workspace.memory_scope in seen:
            continue
        seen.add(workspace.memory_scope)
        scopes.append(workspace.memory_scope)
    return scopes


def memory_compacted_event(
    result: MemoryCompactionResult,
    trace_id: str,
) -> EventRecord:
    compacted_item = result.compacted_item
    return EventRecord(
        type=EventType.memory_compacted,
        target=compacted_item.project_id or compacted_item.scope,
        payload={
            "memory_id": compacted_item.id,
            "scope": compacted_item.scope,
            "status": compacted_item.status,
            "project_id": compacted_item.project_id,
            "agent_id": compacted_item.agent_id,
            "source_memory_ids": result.source_memory_ids,
            "source_count": result.source_count,
            "source_tokens": result.source_tokens,
        },
        trace_id=trace_id,
    )


@app.post("/memory-items/embedding-backfill", response_model=MemoryEmbeddingBackfillResult)
def backfill_memory_embeddings(
    backfill_request: MemoryEmbeddingBackfillRequest,
    request: Request,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
    embedding_provider: OpenRouterQueryEmbeddingProvider | None = Depends(
        get_query_embedding_provider
    ),
) -> MemoryEmbeddingBackfillResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = memory_reviewer_headers(request, trace_id)
    if embedding_provider is None:
        raise HTTPException(
            status_code=503,
            detail="Memory embedding provider unavailable",
        )
    try:
        memory_items = memory_client.list_memory_items(
            scope=backfill_request.scope,
            agent_id=backfill_request.agent_id,
            project_id=backfill_request.project_id,
            status=MemoryStatus(backfill_request.status),
        )
        backfilled_items: list[MemoryItem] = []
        for memory_item in memory_items:
            if len(backfilled_items) >= backfill_request.max_items:
                break
            if memory_item.embedding is not None or not memory_item.content.strip():
                continue
            embedding = embedding_provider.embed_text(memory_item.content)
            updated_item = memory_client.create_memory_item(
                memory_item.model_copy(update={"embedding": embedding})
            )
            backfilled_items.append(updated_item)
            state_client.create_event(
                memory_embedding_backfilled_event(
                    updated_item,
                    trace_id,
                    provider_id=embedding_provider.provider_id,
                    model_id=embedding_provider.model_id,
                ),
                headers=headers,
            )
        return MemoryEmbeddingBackfillResult(
            inspected_count=len(memory_items),
            backfilled_count=len(backfilled_items),
            skipped_count=len(memory_items) - len(backfilled_items),
            memory_ids=[item.id for item in backfilled_items],
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory embedding backfill dependency unavailable",
        ) from error


def memory_embedding_backfilled_event(
    memory_item: MemoryItem,
    trace_id: str,
    *,
    provider_id: str,
    model_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.memory_embedding_backfilled,
        target=memory_item.project_id or memory_item.scope,
        payload={
            "memory_id": memory_item.id,
            "scope": memory_item.scope,
            "status": memory_item.status,
            "project_id": memory_item.project_id,
            "agent_id": memory_item.agent_id,
            "embedding_dimensions": len(memory_item.embedding or []),
            "embedding_provider_id": provider_id,
            "embedding_model_id": model_id,
        },
        trace_id=trace_id,
    )


@app.post(
    "/memory-items/relation-proposals",
    response_model=MemoryRelationProposalResult,
    status_code=201,
)
def propose_memory_relation(
    relation_request: MemoryRelationProposalRequest,
    request: Request,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
) -> MemoryRelationProposalResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = memory_reviewer_headers(request, trace_id)
    try:
        memory_items = memory_items_by_id(memory_client)
        source_memory = required_memory_item(
            memory_items,
            relation_request.source_memory_id,
            label="Source memory",
        )
        related_memories = [
            required_memory_item(memory_items, memory_id, label="Related memory")
            for memory_id in deduplicate_strings(relation_request.related_memory_ids)
        ]
        validate_memory_relation(source_memory, related_memories, state_client)
        related_memory_ids = [memory.id for memory in related_memories]
        proposal_memory = memory_client.create_memory_item(
            MemoryItem(
                scope=source_memory.scope,
                content=memory_relation_proposal_content(
                    source_memory.id,
                    related_memory_ids,
                    relation_request.reason,
                ),
                status=MemoryStatus.proposed,
                agent_id=source_memory.agent_id,
                project_id=source_memory.project_id,
                metadata={
                    "kind": "memory_relation_proposal",
                    "source_memory_id": source_memory.id,
                    "related_memory_ids": related_memory_ids,
                    "reason": relation_request.reason,
                },
            )
        )
        event = state_client.create_event(
            memory_relation_proposed_event(proposal_memory, trace_id),
            headers=headers,
        )
        return MemoryRelationProposalResult(
            proposal_memory=proposal_memory,
            event=event,
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory relation proposal dependency unavailable",
        ) from error


@app.post(
    "/memory-items/relation-proposals/{proposal_id}/apply",
    response_model=MemoryRelationApplicationResult,
)
def apply_memory_relation_proposal(
    proposal_id: str,
    request: Request,
    memory_client: MemoryClient = Depends(get_memory_client),
    state_client: StateClient = Depends(get_state_client),
) -> MemoryRelationApplicationResult:
    trace_id = request.headers.get("x-synarch-trace-id", f"trace_{uuid4().hex[:12]}")
    headers = memory_reviewer_headers(request, trace_id)
    try:
        memory_items = memory_items_by_id(memory_client)
        proposal_memory = required_memory_item(
            memory_items,
            proposal_id,
            label="Relation proposal",
        )
        validate_memory_relation_proposal(proposal_memory)
        source_memory = required_memory_item(
            memory_items,
            str(proposal_memory.metadata["source_memory_id"]),
            label="Source memory",
        )
        related_memories = [
            required_memory_item(memory_items, memory_id, label="Related memory")
            for memory_id in relation_proposal_related_memory_ids(proposal_memory)
        ]
        validate_memory_relation(source_memory, related_memories, state_client)
        related_memory_ids = [memory.id for memory in related_memories]
        updated_source_memory = memory_client.create_memory_item(
            source_memory.model_copy(
                update={
                    "metadata": source_memory_metadata_with_relations(
                        source_memory,
                        related_memory_ids,
                    )
                }
            )
        )
        updated_proposal_memory = memory_client.create_memory_item(
            proposal_memory.model_copy(
                update={
                    "metadata": {
                        **proposal_memory.metadata,
                        "applied": True,
                        "applied_related_memory_ids": related_memory_ids,
                    }
                }
            )
        )
        event = state_client.create_event(
            memory_relation_applied_event(
                updated_proposal_memory,
                updated_source_memory,
                related_memory_ids,
                trace_id,
            ),
            headers=headers,
        )
        return MemoryRelationApplicationResult(
            proposal_memory=updated_proposal_memory,
            source_memory=updated_source_memory,
            applied_related_memory_ids=related_memory_ids,
            event=event,
        )
    except (StateServiceRequestError, TaskRunnerRequestError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except (StateServiceUnavailable, TaskRunnerUnavailable) as error:
        raise HTTPException(
            status_code=502,
            detail="Memory relation application dependency unavailable",
        ) from error


def memory_items_by_id(memory_client: MemoryClient) -> dict[str, MemoryItem]:
    return {item.id: item for item in memory_client.list_memory_items()}


def required_memory_item(
    memory_items: dict[str, MemoryItem],
    memory_id: str,
    *,
    label: str,
) -> MemoryItem:
    item = memory_items.get(memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def validate_memory_relation(
    source_memory: MemoryItem,
    related_memories: list[MemoryItem],
    state_client: StateClient,
) -> None:
    if source_memory.status != MemoryStatus.approved:
        raise HTTPException(status_code=400, detail="Source memory must be approved")
    allowed_project_ids = memory_relation_allowed_project_ids(source_memory, state_client)
    for related_memory in related_memories:
        if related_memory.status != MemoryStatus.approved:
            raise HTTPException(status_code=400, detail="Related memory must be approved")
        if related_memory.id == source_memory.id:
            raise HTTPException(status_code=400, detail="Memory cannot relate to itself")
        if (
            related_memory.project_id is not None
            and related_memory.project_id not in allowed_project_ids
        ):
            raise HTTPException(
                status_code=400,
                detail="Related memory project is not authorized by an active bridge",
            )


def memory_relation_allowed_project_ids(
    source_memory: MemoryItem,
    state_client: StateClient,
) -> set[str]:
    if source_memory.project_id is None:
        return set()
    project_ids = {source_memory.project_id}
    for workspace in state_client.list_project_workspaces(
        project_id=source_memory.project_id,
        active=True,
    ):
        project_ids.update(workspace.bridge_project_ids)
    return project_ids


def validate_memory_relation_proposal(proposal_memory: MemoryItem) -> None:
    if proposal_memory.metadata.get("kind") != "memory_relation_proposal":
        raise HTTPException(status_code=400, detail="Memory item is not a relation proposal")
    if proposal_memory.status != MemoryStatus.approved:
        raise HTTPException(status_code=409, detail="Relation proposal must be approved first")
    if not isinstance(proposal_memory.metadata.get("source_memory_id"), str):
        raise HTTPException(status_code=400, detail="Relation proposal missing source memory")
    if not relation_proposal_related_memory_ids(proposal_memory):
        raise HTTPException(status_code=400, detail="Relation proposal missing related memories")


def relation_proposal_related_memory_ids(proposal_memory: MemoryItem) -> list[str]:
    value = proposal_memory.metadata.get("related_memory_ids", [])
    if not isinstance(value, list):
        return []
    return [
        memory_id
        for memory_id in value
        if isinstance(memory_id, str) and memory_id
    ]


def source_memory_metadata_with_relations(
    source_memory: MemoryItem,
    related_memory_ids: list[str],
) -> dict[str, object]:
    return {
        **source_memory.metadata,
        "related_memory_ids": deduplicate_strings(
            [
                *relation_metadata_memory_ids(source_memory),
                *related_memory_ids,
            ]
        ),
    }


def relation_metadata_memory_ids(memory_item: MemoryItem) -> list[str]:
    value = memory_item.metadata.get("related_memory_ids")
    if not isinstance(value, list):
        return []
    return [memory_id for memory_id in value if isinstance(memory_id, str) and memory_id]


def memory_relation_proposal_content(
    source_memory_id: str,
    related_memory_ids: list[str],
    reason: str,
) -> str:
    related_ids = ", ".join(related_memory_ids)
    return (
        f"Proposed memory relation from {source_memory_id} to {related_ids}. "
        f"Reason: {reason}"
    )


def memory_relation_proposed_event(
    proposal_memory: MemoryItem,
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.memory_relation_proposed,
        target=proposal_memory.project_id or proposal_memory.scope,
        payload={
            "proposal_memory_id": proposal_memory.id,
            "source_memory_id": proposal_memory.metadata.get("source_memory_id"),
            "related_memory_ids": relation_proposal_related_memory_ids(proposal_memory),
            "project_id": proposal_memory.project_id,
            "agent_id": proposal_memory.agent_id,
            "status": proposal_memory.status,
        },
        trace_id=trace_id,
    )


def memory_relation_applied_event(
    proposal_memory: MemoryItem,
    source_memory: MemoryItem,
    related_memory_ids: list[str],
    trace_id: str,
) -> EventRecord:
    return EventRecord(
        type=EventType.memory_relation_applied,
        target=source_memory.project_id or source_memory.scope,
        payload={
            "proposal_memory_id": proposal_memory.id,
            "source_memory_id": source_memory.id,
            "related_memory_ids": related_memory_ids,
            "project_id": source_memory.project_id,
            "agent_id": source_memory.agent_id,
        },
        trace_id=trace_id,
    )


def deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
