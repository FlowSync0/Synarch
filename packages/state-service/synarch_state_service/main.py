import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request

from synarch_models import (
    ActorType,
    AgentDefinition,
    AgentLifecycleDecision,
    AgentLifecycleRequest,
    AgentModelPolicyUpdate,
    AgentProjectAssignment,
    AgentResult,
    AgentSoul,
    AgentStatus,
    ApprovalStatus,
    AuditLogRecord,
    ConnectorJobKind,
    ConnectorJobMutationResult,
    ConnectorJobRecord,
    ConnectorJobResumeRequest,
    ConnectorJobRunBatchResult,
    ConnectorJobRunRecord,
    ConnectorJobRunRequest,
    ConnectorJobRunResult,
    ConnectorJobRunStatus,
    ConnectorJobStatus,
    ConnectorJobStopRequest,
    CostRecord,
    CredentialAccessDecision,
    CredentialAccessRequest,
    CredentialGrant,
    CredentialGrantApplication,
    CredentialGrantApplicationRequest,
    DivisionRecord,
    EventRecord,
    EventType,
    HealthResponse,
    HumanAssistanceKind,
    HumanAssistanceRequest,
    HumanAssistanceResolution,
    HumanAssistanceStatus,
    LifecycleAction,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ProjectComplexityAssessment,
    ProjectComplexityReport,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectSplitDecision,
    ProjectSplitRequest,
    ProjectWorkspace,
    ServiceDefinition,
    SkillDefinition,
    TaskLeaseRecoveryResult,
    TaskRecord,
    TaskReviewAction,
    TaskReviewDecision,
    TaskReviewResult,
    TaskStatus,
)
from synarch_state_service.repositories import RecordRepository, StateRepositories

app = FastAPI(title="Synarch State Service", version="0.1.0")


def default_repositories() -> StateRepositories:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return StateRepositories.postgres(database_url)
    return StateRepositories.in_memory()


REPOSITORIES = default_repositories()

PROJECT_COMPLEXITY_SPLIT_THRESHOLD = 10
CLOSED_TASK_STATUSES = {TaskStatus.completed, TaskStatus.failed}
DEFAULT_TASK_LEASE_SECONDS = 300
MAX_TASK_LEASE_SECONDS = 86_400
DEFAULT_TASK_RETRY_BACKOFF_SECONDS = 60
MAX_TASK_RETRY_BACKOFF_SECONDS = 86_400
MAX_CONNECTOR_JOB_TICK_JOBS = 20
DEFAULT_CONNECTOR_JOB_COOLDOWN_SECONDS = 300
MAX_CONNECTOR_JOB_COOLDOWN_SECONDS = 86_400
MAX_CONNECTOR_JOB_RUN_LIMIT = 10_000
CONNECTOR_JOB_RUNNER_ID = "connector-job-runner"
CONNECTOR_JOB_ADAPTER_NOT_WIRED_REASON = "connector adapter execution is not wired yet"


@dataclass(frozen=True)
class AuditContext:
    actor_type: ActorType
    actor_id: str
    trace_id: str | None = None


def reset_repositories(repositories: StateRepositories | None = None) -> None:
    global REPOSITORIES
    REPOSITORIES = repositories or StateRepositories.in_memory()


def create_record[RecordT](
    repository: RecordRepository[RecordT],
    record_id: str,
    record: RecordT,
) -> RecordT:
    if repository.exists(record_id):
        raise HTTPException(status_code=409, detail=f"Record already exists: {record_id}")
    return repository.create(record_id, record)


def read_record[RecordT](
    repository: RecordRepository[RecordT],
    record_id: str,
    label: str,
) -> RecordT:
    record = repository.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown {label}: {record_id}")
    return record


def update_record[RecordT](
    repository: RecordRepository[RecordT],
    record_id: str,
    record: RecordT,
    label: str,
) -> RecordT:
    if not repository.exists(record_id):
        raise HTTPException(status_code=404, detail=f"Unknown {label}: {record_id}")
    return repository.update(record_id, record)


def update_record_if[RecordT](
    repository: RecordRepository[RecordT],
    record_id: str,
    record: RecordT,
    expected: dict[str, object],
) -> RecordT | None:
    return repository.update_if(record_id, record, expected)


def audit_context_from_request(request: Request) -> AuditContext | None:
    actor_id = request.headers.get("x-synarch-actor-id")
    if actor_id is None:
        return None

    actor_type_value = request.headers.get("x-synarch-actor-type", ActorType.user.value)
    try:
        actor_type = ActorType(actor_type_value)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown actor type: {actor_type_value}",
        ) from error

    return AuditContext(
        actor_type=actor_type,
        actor_id=actor_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def decision_audit_context(decision: AgentLifecycleDecision, request: Request) -> AuditContext:
    return AuditContext(
        actor_type=decision.decided_by_type,
        actor_id=decision.decided_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def split_decision_audit_context(decision: ProjectSplitDecision, request: Request) -> AuditContext:
    return AuditContext(
        actor_type=decision.decided_by_type,
        actor_id=decision.decided_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def credential_decision_audit_context(
    decision: CredentialAccessDecision,
    request: Request,
) -> AuditContext:
    return AuditContext(
        actor_type=decision.decided_by_type,
        actor_id=decision.decided_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def credential_grant_application_audit_context(
    application: CredentialGrantApplicationRequest,
    request: Request,
) -> AuditContext:
    return AuditContext(
        actor_type=application.applied_by_type,
        actor_id=application.applied_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def connector_job_run_audit_context(
    run_request: ConnectorJobRunRequest,
    request: Request,
) -> AuditContext:
    return AuditContext(
        actor_type=run_request.triggered_by_type,
        actor_id=run_request.triggered_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def connector_job_stop_audit_context(
    stop_request: ConnectorJobStopRequest,
    request: Request,
) -> AuditContext:
    return AuditContext(
        actor_type=stop_request.stopped_by_type,
        actor_id=stop_request.stopped_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def connector_job_resume_audit_context(
    resume_request: ConnectorJobResumeRequest,
    request: Request,
) -> AuditContext:
    return AuditContext(
        actor_type=resume_request.resumed_by_type,
        actor_id=resume_request.resumed_by_id,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )


def connector_job_runner_audit_context(
    request: Request,
    trace_id: str | None = None,
) -> AuditContext:
    return AuditContext(
        actor_type=ActorType.service,
        actor_id=CONNECTOR_JOB_RUNNER_ID,
        trace_id=trace_id or request.headers.get("x-synarch-trace-id"),
    )


def write_audit_log(
    context: AuditContext | None,
    *,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any] | None = None,
) -> AuditLogRecord | None:
    if context is None:
        return None

    audit = AuditLogRecord(
        actor_type=context.actor_type,
        actor_id=context.actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        trace_id=context.trace_id,
        payload=payload or {},
    )
    return create_record(REPOSITORIES.audit_logs, audit.id, audit)


def create_domain_event(event: EventRecord) -> EventRecord:
    return create_record(REPOSITORIES.events, event.id, event)


def task_lease_duration_from_request(request: Request) -> timedelta:
    raw_value = request.headers.get("x-synarch-task-lease-seconds")
    if raw_value is None:
        seconds = int(os.getenv("TASK_LEASE_SECONDS", str(DEFAULT_TASK_LEASE_SECONDS)))
    else:
        try:
            seconds = int(raw_value)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="X-Synarch-Task-Lease-Seconds must be an integer",
            ) from error

    if seconds < 1 or seconds > MAX_TASK_LEASE_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"Task lease seconds must be between 1 and {MAX_TASK_LEASE_SECONDS}",
        )
    return timedelta(seconds=seconds)


def task_retry_backoff_from_request(request: Request) -> timedelta:
    raw_value = request.headers.get("x-synarch-task-retry-backoff-seconds")
    if raw_value is None:
        seconds = int(
            os.getenv(
                "TASK_RETRY_BACKOFF_SECONDS",
                str(DEFAULT_TASK_RETRY_BACKOFF_SECONDS),
            )
        )
    else:
        try:
            seconds = int(raw_value)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="X-Synarch-Task-Retry-Backoff-Seconds must be an integer",
            ) from error

    if seconds < 0 or seconds > MAX_TASK_RETRY_BACKOFF_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Task retry backoff seconds must be between "
                f"0 and {MAX_TASK_RETRY_BACKOFF_SECONDS}"
            ),
        )
    return timedelta(seconds=seconds)


def task_retry_delay(task: TaskRecord, base_delay: timedelta) -> timedelta:
    multiplier = 2 ** max(task.attempt_count - 1, 0)
    seconds = min(
        base_delay.total_seconds() * multiplier,
        MAX_TASK_RETRY_BACKOFF_SECONDS,
    )
    return timedelta(seconds=seconds)


def agent_event_source(actor_type: ActorType, actor_id: str) -> str | None:
    if actor_type == ActorType.agent:
        return actor_id
    return None


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="state-service")


def validate_agent_model_policy(agent: AgentDefinition) -> None:
    if agent.model_policy_id is not None and not REPOSITORIES.model_policies.exists(
        agent.model_policy_id
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model policy: {agent.model_policy_id}",
        )


def validate_agent_access_references(
    *,
    owner_agent_id: str | None,
    allowed_agent_ids: list[str],
) -> None:
    candidate_ids = [agent_id for agent_id in [owner_agent_id, *allowed_agent_ids] if agent_id]
    unknown_agent_ids = [
        agent_id for agent_id in candidate_ids if not REPOSITORIES.agents.exists(agent_id)
    ]
    if unknown_agent_ids:
        raise HTTPException(status_code=400, detail=f"Unknown access agents: {unknown_agent_ids}")


def inactive_known_agent_ids(agent_ids: list[str]) -> list[str]:
    inactive_agent_ids: list[str] = []
    for agent_id in agent_ids:
        agent = REPOSITORIES.agents.get(agent_id)
        if agent is not None and agent.status != AgentStatus.active:
            inactive_agent_ids.append(agent_id)
    return inactive_agent_ids


def validate_service_definition(service: ServiceDefinition) -> None:
    validate_agent_access_references(
        owner_agent_id=service.owner_agent_id,
        allowed_agent_ids=service.allowed_agent_ids,
    )


def validate_skill_definition(skill: SkillDefinition) -> None:
    validate_agent_access_references(
        owner_agent_id=skill.owner_agent_id,
        allowed_agent_ids=skill.allowed_agent_ids,
    )


def validate_task_breakdown(task: TaskRecord) -> None:
    if not task.acceptance_criteria:
        raise HTTPException(
            status_code=400,
            detail="Task requires at least one acceptance criterion",
        )
    unknown_scope_tools = sorted(set(task.required_tool_scopes) - set(task.required_tools))
    if unknown_scope_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Credential scopes reference non-required tools: {unknown_scope_tools}",
        )
    missing_dependencies = [
        dependency_id
        for dependency_id in task.depends_on
        if not REPOSITORIES.tasks.exists(dependency_id)
    ]
    if missing_dependencies:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task dependencies: {missing_dependencies}",
        )
    if task.parent_task_id is not None and not REPOSITORIES.tasks.exists(task.parent_task_id):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown parent task: {task.parent_task_id}",
        )


def validate_task_assigned_agent_active(task: TaskRecord, *, status_code: int) -> None:
    assigned_agent = REPOSITORIES.agents.get(task.assigned_agent_id)
    if assigned_agent is not None and assigned_agent.status != AgentStatus.active:
        raise HTTPException(
            status_code=status_code,
            detail=f"Agent is not active: {task.assigned_agent_id}",
        )


def validate_credential_access_request(access_request: CredentialAccessRequest) -> None:
    if not REPOSITORIES.projects.exists(access_request.project_id):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown project: {access_request.project_id}",
        )
    task = REPOSITORIES.tasks.get(access_request.task_id)
    if task is None:
        raise HTTPException(status_code=400, detail=f"Unknown task: {access_request.task_id}")
    if task.project_id != access_request.project_id:
        raise HTTPException(
            status_code=400,
            detail="Credential access request task must belong to project",
        )
    if task.assigned_agent_id != access_request.agent_id:
        raise HTTPException(
            status_code=400,
            detail="Credential access request agent must match task assignment",
        )
    if access_request.tool_name not in task.required_tools:
        raise HTTPException(
            status_code=400,
            detail="Credential access request tool must be required by task",
        )


def validate_human_assistance_request(assistance_request: HumanAssistanceRequest) -> None:
    if not REPOSITORIES.projects.exists(assistance_request.project_id):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown project: {assistance_request.project_id}",
        )
    if assistance_request.task_id is None:
        return
    task = REPOSITORIES.tasks.get(assistance_request.task_id)
    if task is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task: {assistance_request.task_id}",
        )
    if task.project_id != assistance_request.project_id:
        raise HTTPException(
            status_code=400,
            detail="Human assistance request task must belong to project",
        )
    if task.assigned_agent_id != assistance_request.agent_id:
        raise HTTPException(
            status_code=400,
            detail="Human assistance request agent must match task assignment",
        )


def validate_connector_job(job: ConnectorJobRecord) -> None:
    if not REPOSITORIES.services.exists(job.service_id):
        raise HTTPException(status_code=400, detail=f"Unknown service: {job.service_id}")
    owner_agent = REPOSITORIES.agents.get(job.owner_agent_id)
    if owner_agent is None:
        raise HTTPException(status_code=400, detail=f"Unknown owner agent: {job.owner_agent_id}")
    if owner_agent.status != AgentStatus.active:
        raise HTTPException(
            status_code=400,
            detail=f"Connector job owner is not active: {job.owner_agent_id}",
        )
    if job.project_id is not None and not REPOSITORIES.projects.exists(job.project_id):
        raise HTTPException(status_code=400, detail=f"Unknown project: {job.project_id}")
    if job.task_id is not None:
        task = REPOSITORIES.tasks.get(job.task_id)
        if task is None:
            raise HTTPException(status_code=400, detail=f"Unknown task: {job.task_id}")
        if job.project_id is not None and task.project_id != job.project_id:
            raise HTTPException(
                status_code=400,
                detail="Connector job task must belong to project",
            )
        if task.assigned_agent_id != job.owner_agent_id:
            raise HTTPException(
                status_code=400,
                detail="Connector job owner must match task assignment",
            )
    if job.kind == "cron" and not (job.schedule or "").strip():
        raise HTTPException(status_code=400, detail="Cron connector jobs require schedule")
    if job.kind == "webhook" and not (job.webhook_path or "").strip():
        raise HTTPException(status_code=400, detail="Webhook connector jobs require webhook_path")
    if job.status != ConnectorJobStatus.active:
        raise HTTPException(status_code=400, detail="Connector jobs must be created active")
    if job.stopped_at is not None:
        raise HTTPException(status_code=400, detail="New connector jobs cannot be stopped")


def validate_connector_job_run_request(run_request: ConnectorJobRunRequest) -> None:
    if run_request.status == ConnectorJobRunStatus.failed and not run_request.error:
        raise HTTPException(status_code=400, detail="Failed connector job runs require error")
    if run_request.status == ConnectorJobRunStatus.blocked and not run_request.error:
        raise HTTPException(status_code=400, detail="Blocked connector job runs require error")
    if (
        run_request.status == ConnectorJobRunStatus.completed
        and run_request.error is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Completed connector job runs cannot include error",
        )
    if run_request.status == ConnectorJobRunStatus.skipped and run_request.error is not None:
        raise HTTPException(
            status_code=400,
            detail="Skipped connector job runs cannot include error",
        )
    if run_request.completed_at < run_request.started_at:
        raise HTTPException(
            status_code=400,
            detail="Connector job run completed_at cannot be before started_at",
        )


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def connector_job_cooldown_seconds(job: ConnectorJobRecord) -> int:
    raw_cooldown = job.metadata.get("cooldown_seconds")
    if isinstance(raw_cooldown, bool) or raw_cooldown is None:
        return DEFAULT_CONNECTOR_JOB_COOLDOWN_SECONDS
    if isinstance(raw_cooldown, int) and 1 <= raw_cooldown <= MAX_CONNECTOR_JOB_COOLDOWN_SECONDS:
        return raw_cooldown
    return DEFAULT_CONNECTOR_JOB_COOLDOWN_SECONDS


def connector_job_failure_cooldown_seconds(job: ConnectorJobRecord) -> int:
    raw_cooldown = job.metadata.get("failure_cooldown_seconds")
    if isinstance(raw_cooldown, bool) or raw_cooldown is None:
        return connector_job_cooldown_seconds(job)
    if isinstance(raw_cooldown, int) and 1 <= raw_cooldown <= MAX_CONNECTOR_JOB_COOLDOWN_SECONDS:
        return raw_cooldown
    return connector_job_cooldown_seconds(job)


def connector_job_max_runs(job: ConnectorJobRecord) -> int | None:
    raw_max_runs = job.metadata.get("max_runs")
    if isinstance(raw_max_runs, bool) or raw_max_runs is None:
        return None
    if isinstance(raw_max_runs, int) and 1 <= raw_max_runs <= MAX_CONNECTOR_JOB_RUN_LIMIT:
        return raw_max_runs
    return None


def connector_job_max_failures(job: ConnectorJobRecord) -> int | None:
    raw_max_failures = job.metadata.get("max_failures")
    if isinstance(raw_max_failures, bool) or raw_max_failures is None:
        return None
    if isinstance(raw_max_failures, int) and 1 <= raw_max_failures <= MAX_CONNECTOR_JOB_RUN_LIMIT:
        return raw_max_failures
    return None


def connector_job_is_due(job: ConnectorJobRecord, due_before: datetime | None) -> bool:
    if due_before is None or job.next_run_at is None:
        return True
    return utc_datetime(job.next_run_at) <= utc_datetime(due_before)


def connector_job_sort_key(job: ConnectorJobRecord) -> tuple[datetime, datetime, str]:
    return (
        utc_datetime(job.next_run_at or job.created_at),
        utc_datetime(job.created_at),
        job.id,
    )


def connector_job_run_count(
    job_id: str,
    status: ConnectorJobRunStatus | None = None,
) -> int:
    return len(
        [
            run
            for run in REPOSITORIES.connector_job_runs.list_records()
            if run.job_id == job_id and (status is None or run.status == status)
        ]
    )


def connector_job_latest_run(job_id: str) -> ConnectorJobRunRecord | None:
    runs = [
        run
        for run in REPOSITORIES.connector_job_runs.list_records()
        if run.job_id == job_id
    ]
    if not runs:
        return None
    return max(runs, key=lambda run: (utc_datetime(run.completed_at), run.id))


def connector_job_run_stop_reason(
    job: ConnectorJobRecord,
    run: ConnectorJobRunRecord,
) -> str | None:
    if run.output.get("stop_job") is True or run.output.get("stop_condition_met") is True:
        raw_reason = run.output.get("stop_reason") or run.output.get("reason")
        if isinstance(raw_reason, str) and raw_reason.strip():
            return raw_reason.strip()
        return "Connector job stop condition met by run output."

    max_failures = connector_job_max_failures(job)
    if (
        run.status == ConnectorJobRunStatus.failed
        and max_failures is not None
        and connector_job_run_count(job.id, ConnectorJobRunStatus.failed) >= max_failures
    ):
        return f"Connector job reached max_failures={max_failures}."

    if run.status == ConnectorJobRunStatus.blocked:
        return "Connector job blocked and requires human review."

    max_runs = connector_job_max_runs(job)
    if max_runs is not None and connector_job_run_count(job.id) >= max_runs:
        return f"Connector job reached max_runs={max_runs}."
    return None


def validate_project_workspace(workspace: ProjectWorkspace) -> None:
    if not REPOSITORIES.projects.exists(workspace.project_id):
        raise HTTPException(status_code=400, detail=f"Unknown project: {workspace.project_id}")
    unknown_agents = [
        agent_id
        for agent_id in workspace.allowed_agent_ids
        if not REPOSITORIES.agents.exists(agent_id)
    ]
    if unknown_agents:
        raise HTTPException(status_code=400, detail=f"Unknown workspace agents: {unknown_agents}")
    inactive_agents = inactive_known_agent_ids(workspace.allowed_agent_ids)
    if workspace.active and inactive_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace agents are not active: {inactive_agents}",
        )
    active_workspace = active_project_workspace(workspace.project_id)
    if active_workspace is not None and active_workspace.id != workspace.id and workspace.active:
        raise HTTPException(
            status_code=409,
            detail=f"Active workspace already exists for project: {workspace.project_id}",
        )


def active_project_workspace(project_id: str) -> ProjectWorkspace | None:
    active_workspaces = [
        workspace
        for workspace in REPOSITORIES.project_workspaces.list_records()
        if workspace.project_id == project_id and workspace.active
    ]
    if not active_workspaces:
        return None
    return sorted(
        active_workspaces,
        key=lambda workspace: workspace.created_at,
        reverse=True,
    )[0]


def project_tasks(project_id: str) -> list[TaskRecord]:
    return [task for task in REPOSITORIES.tasks.list_records() if task.project_id == project_id]


def active_project_assignments(project_id: str) -> list[AgentProjectAssignment]:
    return [
        assignment
        for assignment in REPOSITORIES.agent_project_assignments.list_records()
        if assignment.project_id == project_id
        and assignment.active
        and (agent := REPOSITORIES.agents.get(assignment.agent_id)) is not None
        and agent.status == AgentStatus.active
    ]


def build_project_complexity_report(project_id: str) -> ProjectComplexityReport:
    tasks = project_tasks(project_id)
    open_task_count = sum(task.status not in CLOSED_TASK_STATUSES for task in tasks)
    blocked_task_count = sum(task.status == TaskStatus.blocked for task in tasks)
    assigned_agent_count = len(
        {assignment.agent_id for assignment in active_project_assignments(project_id)}
    )
    workspace = active_project_workspace(project_id)
    workspace_bridge_count = len(workspace.bridge_project_ids) if workspace is not None else 0
    score = (
        open_task_count
        + blocked_task_count * 3
        + assigned_agent_count * 2
        + workspace_bridge_count * 2
    )
    reasons: list[str] = []
    if open_task_count >= 8:
        reasons.append(f"Project has {open_task_count} open tasks.")
    if blocked_task_count > 0:
        reasons.append(f"Project has {blocked_task_count} blocked tasks.")
    if assigned_agent_count >= 4:
        reasons.append(f"Project has {assigned_agent_count} active assigned agents.")
    if workspace_bridge_count > 0:
        reasons.append(f"Project has {workspace_bridge_count} explicit workspace bridges.")
    if score >= PROJECT_COMPLEXITY_SPLIT_THRESHOLD and not reasons:
        reasons.append("Project complexity score reached the split threshold.")

    return ProjectComplexityReport(
        project_id=project_id,
        task_count=len(tasks),
        open_task_count=open_task_count,
        blocked_task_count=blocked_task_count,
        assigned_agent_count=assigned_agent_count,
        workspace_bridge_count=workspace_bridge_count,
        score=score,
        threshold=PROJECT_COMPLEXITY_SPLIT_THRESHOLD,
        split_recommended=score >= PROJECT_COMPLEXITY_SPLIT_THRESHOLD,
        reasons=reasons,
    )


def proposed_project_shards(project: ProjectRecord, report: ProjectComplexityReport) -> list[str]:
    if report.blocked_task_count > 0:
        return [f"{project.title} - unblock", f"{project.title} - execution"]
    if report.assigned_agent_count >= 4:
        return [f"{project.title} - coordination", f"{project.title} - delivery"]
    return [f"{project.title} - planning", f"{project.title} - execution"]


def project_complexity_payload(report: ProjectComplexityReport) -> dict[str, Any]:
    return {
        "project_id": report.project_id,
        "report_id": report.id,
        "task_count": report.task_count,
        "open_task_count": report.open_task_count,
        "blocked_task_count": report.blocked_task_count,
        "assigned_agent_count": report.assigned_agent_count,
        "workspace_bridge_count": report.workspace_bridge_count,
        "score": report.score,
        "threshold": report.threshold,
        "split_recommended": report.split_recommended,
        "reasons": report.reasons,
    }


def validate_agent_project_assignment(assignment: AgentProjectAssignment) -> None:
    if not REPOSITORIES.projects.exists(assignment.project_id):
        raise HTTPException(status_code=400, detail=f"Unknown project: {assignment.project_id}")
    agent = REPOSITORIES.agents.get(assignment.agent_id)
    if agent is None:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {assignment.agent_id}")
    if assignment.active and agent.status != AgentStatus.active:
        raise HTTPException(
            status_code=400,
            detail=f"Agent is not active: {assignment.agent_id}",
        )
    workspace = REPOSITORIES.project_workspaces.get(assignment.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=400, detail=f"Unknown workspace: {assignment.workspace_id}")
    if workspace.project_id != assignment.project_id:
        raise HTTPException(
            status_code=400,
            detail="Assignment workspace must belong to the same project",
        )
    if assignment.active and assignment.agent_id not in workspace.allowed_agent_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Agent is not allowed in workspace: {assignment.agent_id}",
        )


def active_agent_soul(agent_id: str) -> AgentSoul | None:
    active_souls = [
        soul
        for soul in REPOSITORIES.agent_souls.list_records()
        if soul.agent_id == agent_id and soul.active
    ]
    if not active_souls:
        return None
    return sorted(active_souls, key=lambda soul: (soul.version, soul.created_at), reverse=True)[0]


def validate_agent_soul(soul: AgentSoul) -> None:
    if not REPOSITORIES.agents.exists(soul.agent_id):
        raise HTTPException(status_code=400, detail=f"Unknown agent: {soul.agent_id}")
    if soul.active:
        existing_active_soul = active_agent_soul(soul.agent_id)
        if existing_active_soul is not None and existing_active_soul.id != soul.id:
            raise HTTPException(
                status_code=409,
                detail=f"Active soul already exists for agent: {soul.agent_id}",
            )


def validate_lifecycle_proposed_soul(
    lifecycle_request: AgentLifecycleRequest,
    proposed_agent: AgentDefinition,
) -> None:
    proposed_soul = lifecycle_request.proposed_soul
    if proposed_soul is None:
        return
    if proposed_soul.agent_id != proposed_agent.id:
        raise HTTPException(
            status_code=400,
            detail="proposed_soul.agent_id must match proposed_agent.id",
        )
    if not proposed_soul.active:
        raise HTTPException(
            status_code=400,
            detail="proposed_soul must be active",
        )
    if REPOSITORIES.agent_souls.exists(proposed_soul.id):
        raise HTTPException(
            status_code=409,
            detail=f"Record already exists: {proposed_soul.id}",
        )


def validate_lifecycle_request(lifecycle_request: AgentLifecycleRequest) -> None:
    if lifecycle_request.action == LifecycleAction.create_agent:
        if lifecycle_request.proposed_agent is None:
            raise HTTPException(
                status_code=400,
                detail="create_agent requires proposed_agent",
            )
        validate_agent_model_policy(lifecycle_request.proposed_agent)
        validate_lifecycle_proposed_soul(lifecycle_request, lifecycle_request.proposed_agent)
        if REPOSITORIES.agents.exists(lifecycle_request.proposed_agent.id):
            raise HTTPException(
                status_code=409,
                detail=f"Record already exists: {lifecycle_request.proposed_agent.id}",
            )
        return

    if lifecycle_request.action == LifecycleAction.update_agent:
        if lifecycle_request.target_agent_id is None:
            raise HTTPException(
                status_code=400,
                detail="update_agent requires target_agent_id",
            )
        if lifecycle_request.proposed_agent is None:
            raise HTTPException(
                status_code=400,
                detail="update_agent requires proposed_agent",
            )
        if lifecycle_request.proposed_agent.id != lifecycle_request.target_agent_id:
            raise HTTPException(
                status_code=400,
                detail="proposed_agent.id must match target_agent_id",
            )
        if not REPOSITORIES.agents.exists(lifecycle_request.target_agent_id):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown target agent: {lifecycle_request.target_agent_id}",
            )
        validate_agent_model_policy(lifecycle_request.proposed_agent)
        validate_lifecycle_proposed_soul(lifecycle_request, lifecycle_request.proposed_agent)
        return

    if lifecycle_request.action == LifecycleAction.deactivate_agent:
        if lifecycle_request.proposed_soul is not None:
            raise HTTPException(
                status_code=400,
                detail="deactivate_agent does not accept proposed_soul",
            )
        if lifecycle_request.target_agent_id is None:
            raise HTTPException(
                status_code=400,
                detail="deactivate_agent requires target_agent_id",
            )
        if not REPOSITORIES.agents.exists(lifecycle_request.target_agent_id):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown target agent: {lifecycle_request.target_agent_id}",
            )
        return

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported lifecycle action: {lifecycle_request.action}",
    )


def lifecycle_subject_agent_id(lifecycle_request: AgentLifecycleRequest) -> str | None:
    if lifecycle_request.action == LifecycleAction.create_agent:
        if lifecycle_request.proposed_agent is None:
            return None
        return lifecycle_request.proposed_agent.id
    return lifecycle_request.target_agent_id


def validate_no_pending_lifecycle_conflict(lifecycle_request: AgentLifecycleRequest) -> None:
    subject_agent_id = lifecycle_subject_agent_id(lifecycle_request)
    if subject_agent_id is None:
        return
    for existing_request in REPOSITORIES.agent_lifecycle_requests.list_records():
        if existing_request.id == lifecycle_request.id:
            continue
        if existing_request.status != ApprovalStatus.requested:
            continue
        if existing_request.action != lifecycle_request.action:
            continue
        if lifecycle_subject_agent_id(existing_request) != subject_agent_id:
            continue
        raise HTTPException(
            status_code=409,
            detail=(
                "Pending lifecycle request already exists for "
                f"{subject_agent_id} and action {lifecycle_request.action}: "
                f"{existing_request.id}"
            ),
        )


@app.post("/divisions", response_model=DivisionRecord, status_code=201)
def create_division(division: DivisionRecord, request: Request) -> DivisionRecord:
    audit_context = audit_context_from_request(request)
    record = create_record(REPOSITORIES.divisions, division.id, division)
    write_audit_log(
        audit_context,
        action="division.created",
        target_type="division",
        target_id=record.id,
    )
    return record


@app.get("/divisions", response_model=list[DivisionRecord])
def list_divisions() -> list[DivisionRecord]:
    return REPOSITORIES.divisions.list_records()


@app.get("/divisions/{division_id}", response_model=DivisionRecord)
def read_division(division_id: str) -> DivisionRecord:
    return read_record(REPOSITORIES.divisions, division_id, "division")


@app.post("/agents", response_model=AgentDefinition, status_code=201)
def create_agent(agent: AgentDefinition, request: Request) -> AgentDefinition:
    audit_context = audit_context_from_request(request)
    validate_agent_model_policy(agent)
    record = create_record(REPOSITORIES.agents, agent.id, agent)
    write_audit_log(audit_context, action="agent.created", target_type="agent", target_id=record.id)
    return record


def agent_soul_created_event(soul: AgentSoul, trace_id: str | None) -> EventRecord:
    return EventRecord(
        type=EventType.agent_soul_created,
        source_agent_id=soul.created_by if REPOSITORIES.agents.exists(soul.created_by) else None,
        target=soul.agent_id,
        payload={"soul_id": soul.id, "version": soul.version, "active": soul.active},
        trace_id=trace_id,
    )


def create_agent_soul_record(
    soul: AgentSoul,
    audit_context: AuditContext | None,
    trace_id: str | None = None,
) -> tuple[AgentSoul, EventRecord]:
    validate_agent_soul(soul)
    record = create_record(REPOSITORIES.agent_souls, soul.id, soul)
    event_trace_id = audit_context.trace_id if audit_context is not None else trace_id
    event = create_domain_event(agent_soul_created_event(record, event_trace_id))
    write_audit_log(
        audit_context,
        action="agent_soul.created",
        target_type="agent_soul",
        target_id=record.id,
        payload={"agent_id": record.agent_id, "version": record.version, "active": record.active},
    )
    return record, event


def deactivate_active_agent_soul(
    agent_id: str,
    audit_context: AuditContext,
    *,
    lifecycle_request_id: str,
) -> AgentSoul | None:
    existing_soul = active_agent_soul(agent_id)
    if existing_soul is None:
        return None

    deactivated_soul = existing_soul.model_copy(
        update={"active": False, "updated_at": datetime.now(UTC)}
    )
    record = update_record(
        REPOSITORIES.agent_souls,
        existing_soul.id,
        deactivated_soul,
        "agent soul",
    )
    write_audit_log(
        audit_context,
        action="agent_soul.deactivated",
        target_type="agent_soul",
        target_id=record.id,
        payload={"agent_id": agent_id, "lifecycle_request_id": lifecycle_request_id},
    )
    return record


def agent_update_changed_fields(
    current_agent: AgentDefinition,
    updated_agent: AgentDefinition,
) -> list[str]:
    immutable_fields = {"id", "created_at", "updated_at"}
    current_payload = current_agent.model_dump(mode="json")
    updated_payload = updated_agent.model_dump(mode="json")
    return sorted(
        field
        for field in current_payload
        if field not in immutable_fields and current_payload[field] != updated_payload[field]
    )


@app.get("/agents", response_model=list[AgentDefinition])
def list_agents(division: str | None = None) -> list[AgentDefinition]:
    agents = REPOSITORIES.agents.list_records()
    if division is None:
        return agents
    return [agent for agent in agents if agent.division == division]


@app.get("/agents/{agent_id}", response_model=AgentDefinition)
def read_agent(agent_id: str) -> AgentDefinition:
    return read_record(REPOSITORIES.agents, agent_id, "agent")


@app.patch("/agents/{agent_id}/model-policy", response_model=AgentDefinition)
def update_agent_model_policy(
    agent_id: str,
    update: AgentModelPolicyUpdate,
    request: Request,
) -> AgentDefinition:
    audit_context = audit_context_from_request(request)
    current_agent = read_record(REPOSITORIES.agents, agent_id, "agent")
    if update.model_policy_id is not None and not REPOSITORIES.model_policies.exists(
        update.model_policy_id
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model policy: {update.model_policy_id}",
        )
    if current_agent.model_policy_id == update.model_policy_id:
        return current_agent

    updated_agent = current_agent.model_copy(
        update={
            "model_policy_id": update.model_policy_id,
            "updated_at": datetime.now(UTC),
        }
    )
    record = update_record(REPOSITORIES.agents, agent_id, updated_agent, "agent")
    create_domain_event(
        EventRecord(
            type=EventType.agent_updated,
            source_agent_id=agent_event_source(
                audit_context.actor_type,
                audit_context.actor_id,
            )
            if audit_context is not None
            else None,
            target=record.id,
            payload={
                "changed_fields": ["model_policy_id"],
                "previous_model_policy_id": current_agent.model_policy_id,
                "model_policy_id": record.model_policy_id,
            },
            trace_id=request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="agent.model_policy_updated",
        target_type="agent",
        target_id=record.id,
        payload={
            "previous_model_policy_id": current_agent.model_policy_id,
            "model_policy_id": record.model_policy_id,
        },
    )
    return record


@app.post("/agent-souls", response_model=AgentSoul, status_code=201)
def create_agent_soul(soul: AgentSoul, request: Request) -> AgentSoul:
    audit_context = audit_context_from_request(request)
    record, _event = create_agent_soul_record(
        soul,
        audit_context,
        trace_id=request.headers.get("x-synarch-trace-id"),
    )
    return record


@app.get("/agent-souls", response_model=list[AgentSoul])
def list_agent_souls(
    agent_id: str | None = None,
    active: bool | None = None,
) -> list[AgentSoul]:
    souls = REPOSITORIES.agent_souls.list_records()
    if agent_id is not None:
        souls = [soul for soul in souls if soul.agent_id == agent_id]
    if active is not None:
        souls = [soul for soul in souls if soul.active == active]
    return souls


@app.get("/agent-souls/{soul_id}", response_model=AgentSoul)
def read_agent_soul(soul_id: str) -> AgentSoul:
    return read_record(REPOSITORIES.agent_souls, soul_id, "agent soul")


@app.get("/agents/{agent_id}/soul", response_model=AgentSoul)
def read_active_agent_soul(agent_id: str) -> AgentSoul:
    if not REPOSITORIES.agents.exists(agent_id):
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")
    soul = active_agent_soul(agent_id)
    if soul is None:
        raise HTTPException(status_code=404, detail=f"No active soul for agent: {agent_id}")
    return soul


def validate_project_record(project: ProjectRecord) -> None:
    inactive_owners = inactive_known_agent_ids([project.owner_agent_id])
    if inactive_owners:
        raise HTTPException(
            status_code=400,
            detail=f"Project owner is not active: {project.owner_agent_id}",
        )


@app.post("/projects", response_model=ProjectRecord, status_code=201)
def create_project(project: ProjectRecord, request: Request) -> ProjectRecord:
    audit_context = audit_context_from_request(request)
    validate_project_record(project)
    record = create_record(REPOSITORIES.projects, project.id, project)
    write_audit_log(
        audit_context,
        action="project.created",
        target_type="project",
        target_id=record.id,
    )
    return record


@app.get("/projects", response_model=list[ProjectRecord])
def list_projects() -> list[ProjectRecord]:
    return REPOSITORIES.projects.list_records()


@app.get("/projects/{project_id}", response_model=ProjectRecord)
def read_project(project_id: str) -> ProjectRecord:
    return read_record(REPOSITORIES.projects, project_id, "project")


@app.post("/project-workspaces", response_model=ProjectWorkspace, status_code=201)
def create_project_workspace(
    workspace: ProjectWorkspace,
    request: Request,
) -> ProjectWorkspace:
    audit_context = audit_context_from_request(request)
    validate_project_workspace(workspace)
    record = create_record(REPOSITORIES.project_workspaces, workspace.id, workspace)
    create_domain_event(
        EventRecord(
            type=EventType.project_workspace_created,
            target=record.project_id,
            payload={
                "workspace_id": record.id,
                "memory_scope": record.memory_scope,
                "allowed_agent_ids": record.allowed_agent_ids,
            },
            trace_id=request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="project_workspace.created",
        target_type="project_workspace",
        target_id=record.id,
        payload={"project_id": record.project_id, "memory_scope": record.memory_scope},
    )
    return record


@app.get("/project-workspaces", response_model=list[ProjectWorkspace])
def list_project_workspaces(
    project_id: str | None = None,
    active: bool | None = None,
) -> list[ProjectWorkspace]:
    workspaces = REPOSITORIES.project_workspaces.list_records()
    if project_id is not None:
        workspaces = [workspace for workspace in workspaces if workspace.project_id == project_id]
    if active is not None:
        workspaces = [workspace for workspace in workspaces if workspace.active == active]
    return workspaces


@app.get("/project-workspaces/{workspace_id}", response_model=ProjectWorkspace)
def read_project_workspace(workspace_id: str) -> ProjectWorkspace:
    return read_record(REPOSITORIES.project_workspaces, workspace_id, "project workspace")


@app.get("/projects/{project_id}/workspace", response_model=ProjectWorkspace)
def read_active_project_workspace(project_id: str) -> ProjectWorkspace:
    if not REPOSITORIES.projects.exists(project_id):
        raise HTTPException(status_code=404, detail=f"Unknown project: {project_id}")
    workspace = active_project_workspace(project_id)
    if workspace is None:
        raise HTTPException(
            status_code=404, detail=f"No active workspace for project: {project_id}"
        )
    return workspace


@app.post("/agent-project-assignments", response_model=AgentProjectAssignment, status_code=201)
def create_agent_project_assignment(
    assignment: AgentProjectAssignment,
    request: Request,
) -> AgentProjectAssignment:
    audit_context = audit_context_from_request(request)
    validate_agent_project_assignment(assignment)
    record = create_record(REPOSITORIES.agent_project_assignments, assignment.id, assignment)
    create_domain_event(
        EventRecord(
            type=EventType.agent_project_assigned,
            source_agent_id=record.agent_id,
            target=record.project_id,
            payload={
                "assignment_id": record.id,
                "workspace_id": record.workspace_id,
                "assignment_role": record.assignment_role,
                "active": record.active,
            },
            trace_id=request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="agent_project.assigned",
        target_type="agent_project_assignment",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "workspace_id": record.workspace_id,
            "agent_id": record.agent_id,
            "assignment_role": record.assignment_role,
        },
    )
    return record


@app.get("/agent-project-assignments", response_model=list[AgentProjectAssignment])
def list_agent_project_assignments(
    project_id: str | None = None,
    agent_id: str | None = None,
    active: bool | None = None,
) -> list[AgentProjectAssignment]:
    assignments = REPOSITORIES.agent_project_assignments.list_records()
    if project_id is not None:
        assignments = [
            assignment for assignment in assignments if assignment.project_id == project_id
        ]
    if agent_id is not None:
        assignments = [assignment for assignment in assignments if assignment.agent_id == agent_id]
    if active is not None:
        assignments = [assignment for assignment in assignments if assignment.active == active]
    return assignments


@app.get("/agent-project-assignments/{assignment_id}", response_model=AgentProjectAssignment)
def read_agent_project_assignment(assignment_id: str) -> AgentProjectAssignment:
    return read_record(
        REPOSITORIES.agent_project_assignments,
        assignment_id,
        "agent project assignment",
    )


@app.post(
    "/projects/{project_id}/complexity-assessments",
    response_model=ProjectComplexityAssessment,
    status_code=201,
)
def assess_project_complexity(project_id: str, request: Request) -> ProjectComplexityAssessment:
    project = read_record(REPOSITORIES.projects, project_id, "project")
    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    source_agent_id = (
        agent_event_source(audit_context.actor_type, audit_context.actor_id)
        if audit_context is not None
        else None
    )

    report_draft = build_project_complexity_report(project_id)
    report = create_record(
        REPOSITORIES.project_complexity_reports,
        report_draft.id,
        report_draft,
    )

    create_domain_event(
        EventRecord(
            type=EventType.project_complexity_reported,
            source_agent_id=source_agent_id,
            target=project_id,
            payload=project_complexity_payload(report),
            trace_id=trace_id,
        )
    )
    write_audit_log(
        audit_context,
        action="project_complexity.reported",
        target_type="project_complexity_report",
        target_id=report.id,
        payload=project_complexity_payload(report),
    )

    split_request: ProjectSplitRequest | None = None
    if report.split_recommended:
        split_request_draft = ProjectSplitRequest(
            project_id=project_id,
            complexity_report_id=report.id,
            requested_by=audit_context.actor_id if audit_context is not None else "system",
            reason=" ".join(report.reasons),
            proposed_shard_titles=proposed_project_shards(project, report),
        )
        split_request = create_record(
            REPOSITORIES.project_split_requests,
            split_request_draft.id,
            split_request_draft,
        )
        create_domain_event(
            EventRecord(
                type=EventType.project_split_requested,
                source_agent_id=source_agent_id,
                target=project_id,
                payload={
                    "project_id": project_id,
                    "split_request_id": split_request.id,
                    "complexity_report_id": report.id,
                    "proposed_shard_titles": split_request.proposed_shard_titles,
                    "status": split_request.status,
                },
                trace_id=trace_id,
            )
        )
        write_audit_log(
            audit_context,
            action="project_split.requested",
            target_type="project_split_request",
            target_id=split_request.id,
            payload={
                "project_id": project_id,
                "complexity_report_id": report.id,
                "status": split_request.status,
            },
        )

    return ProjectComplexityAssessment(report=report, split_request=split_request)


@app.get("/project-complexity-reports", response_model=list[ProjectComplexityReport])
def list_project_complexity_reports(
    project_id: str | None = None,
) -> list[ProjectComplexityReport]:
    reports = REPOSITORIES.project_complexity_reports.list_records()
    if project_id is not None:
        reports = [report for report in reports if report.project_id == project_id]
    return reports


@app.get("/project-complexity-reports/{report_id}", response_model=ProjectComplexityReport)
def read_project_complexity_report(report_id: str) -> ProjectComplexityReport:
    return read_record(
        REPOSITORIES.project_complexity_reports,
        report_id,
        "project complexity report",
    )


@app.get("/project-split-requests", response_model=list[ProjectSplitRequest])
def list_project_split_requests(
    project_id: str | None = None,
    status: ApprovalStatus | None = None,
) -> list[ProjectSplitRequest]:
    split_requests = REPOSITORIES.project_split_requests.list_records()
    if project_id is not None:
        split_requests = [
            split_request
            for split_request in split_requests
            if split_request.project_id == project_id
        ]
    if status is not None:
        split_requests = [
            split_request for split_request in split_requests if split_request.status == status
        ]
    return split_requests


@app.get("/project-split-requests/{split_request_id}", response_model=ProjectSplitRequest)
def read_project_split_request(split_request_id: str) -> ProjectSplitRequest:
    return read_record(
        REPOSITORIES.project_split_requests,
        split_request_id,
        "project split request",
    )


def project_split_decided_event(
    split_request: ProjectSplitRequest,
    decision: ProjectSplitDecision,
    trace_id: str | None,
) -> EventRecord:
    return EventRecord(
        type=EventType.approval_decided,
        source_agent_id=agent_event_source(decision.decided_by_type, decision.decided_by_id),
        target=split_request.project_id,
        payload={
            "decision_type": "project_split",
            "split_request_id": split_request.id,
            "complexity_report_id": split_request.complexity_report_id,
            "status": decision.status,
            "rationale": decision.rationale,
            "proposed_shard_titles": split_request.proposed_shard_titles,
        },
        trace_id=trace_id,
    )


@app.post(
    "/project-split-requests/{split_request_id}/decisions",
    response_model=ProjectSplitDecision,
    status_code=201,
)
def decide_project_split_request(
    split_request_id: str,
    decision: ProjectSplitDecision,
    request: Request,
) -> ProjectSplitDecision:
    if decision.request_id != split_request_id:
        raise HTTPException(status_code=400, detail="Decision request_id must match path")
    if decision.status not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(
            status_code=400,
            detail="Project split decisions must be approved or rejected",
        )

    split_request = read_record(
        REPOSITORIES.project_split_requests,
        split_request_id,
        "project split request",
    )
    if split_request.status != ApprovalStatus.requested:
        raise HTTPException(
            status_code=409,
            detail=f"Project split request is already {split_request.status}",
        )

    context = split_decision_audit_context(decision, request)
    event = create_domain_event(
        project_split_decided_event(split_request, decision, context.trace_id)
    )
    update_record(
        REPOSITORIES.project_split_requests,
        split_request_id,
        split_request.model_copy(update={"status": decision.status}),
        "project split request",
    )
    write_audit_log(
        context,
        action=f"project_split_request.{decision.status}",
        target_type="project_split_request",
        target_id=split_request_id,
        payload={
            "project_id": split_request.project_id,
            "complexity_report_id": split_request.complexity_report_id,
            "rationale": decision.rationale,
        },
    )

    return decision.model_copy(update={"events_emitted": [event]})


def split_shard_titles(split_request: ProjectSplitRequest, project: ProjectRecord) -> list[str]:
    if split_request.proposed_shard_titles:
        return split_request.proposed_shard_titles
    return [f"{project.title} - shard"]


def split_allowed_agent_ids(project: ProjectRecord) -> list[str]:
    workspace = active_project_workspace(project.id)
    if workspace is None or not workspace.allowed_agent_ids:
        return [project.owner_agent_id]
    return list(dict.fromkeys([project.owner_agent_id, *workspace.allowed_agent_ids]))


def split_assignment_agent_roles(
    project: ProjectRecord, allowed_agent_ids: list[str]
) -> dict[str, str]:
    source_roles = {
        assignment.agent_id: assignment.assignment_role
        for assignment in active_project_assignments(project.id)
        if assignment.agent_id in allowed_agent_ids
    }
    roles = {**source_roles, project.owner_agent_id: "owner"}
    return {
        agent_id: role
        for agent_id, role in roles.items()
        if agent_id in allowed_agent_ids and REPOSITORIES.agents.exists(agent_id)
    }


def split_applied_event(
    split_request: ProjectSplitRequest,
    shard_projects: list[ProjectRecord],
    shard_tasks: list[TaskRecord],
    context: AuditContext | None,
) -> EventRecord:
    return EventRecord(
        type=EventType.project_split_applied,
        source_agent_id=agent_event_source(context.actor_type, context.actor_id)
        if context is not None
        else None,
        target=split_request.project_id,
        payload={
            "split_request_id": split_request.id,
            "source_project_id": split_request.project_id,
            "shard_project_ids": [project.id for project in shard_projects],
            "shard_task_ids": [task.id for task in shard_tasks],
        },
        trace_id=context.trace_id if context is not None else None,
    )


@app.post(
    "/project-split-requests/{split_request_id}/apply",
    response_model=ProjectSplitApplication,
    status_code=201,
)
def apply_project_split_request(
    split_request_id: str,
    request: Request,
) -> ProjectSplitApplication:
    split_request = read_record(
        REPOSITORIES.project_split_requests,
        split_request_id,
        "project split request",
    )
    if split_request.status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Project split request must be approved before application: {split_request.status}"
            ),
        )

    source_project = read_record(REPOSITORIES.projects, split_request.project_id, "project")
    allowed_agent_ids = split_allowed_agent_ids(source_project)
    assignment_roles = split_assignment_agent_roles(source_project, allowed_agent_ids)
    audit_context = audit_context_from_request(request)

    shard_projects: list[ProjectRecord] = []
    shard_workspaces: list[ProjectWorkspace] = []
    shard_assignments: list[AgentProjectAssignment] = []
    shard_tasks: list[TaskRecord] = []
    for title in split_shard_titles(split_request, source_project):
        shard_project_draft = ProjectRecord(
            title=title,
            goal=f"Shard of {source_project.title}: {split_request.reason}",
            priority=source_project.priority,
            owner_agent_id=source_project.owner_agent_id,
        )
        shard_project = create_record(
            REPOSITORIES.projects,
            shard_project_draft.id,
            shard_project_draft,
        )
        shard_projects.append(shard_project)

        shard_workspace_draft = ProjectWorkspace(
            project_id=shard_project.id,
            name=title,
            summary=f"Shard created from split request {split_request.id}.",
            memory_scope=f"project:{shard_project.id}",
            allowed_agent_ids=allowed_agent_ids,
            bridge_project_ids=[source_project.id],
        )
        shard_workspace = create_record(
            REPOSITORIES.project_workspaces,
            shard_workspace_draft.id,
            shard_workspace_draft,
        )
        shard_workspaces.append(shard_workspace)

        for agent_id, role in assignment_roles.items():
            shard_assignment_draft = AgentProjectAssignment(
                project_id=shard_project.id,
                workspace_id=shard_workspace.id,
                agent_id=agent_id,
                assignment_role=role,
            )
            shard_assignments.append(
                create_record(
                    REPOSITORIES.agent_project_assignments,
                    shard_assignment_draft.id,
                    shard_assignment_draft,
                )
            )

        shard_task_draft = TaskRecord(
            project_id=shard_project.id,
            title=f"Define execution plan for {title}",
            description="Prepare the first executable task chain for this shard.",
            assigned_agent_id=source_project.owner_agent_id,
            acceptance_criteria=[
                "Shard objective is restated with explicit scope.",
                "Next executable tasks are decomposed before runtime execution.",
            ],
            sequence=1,
        )
        shard_tasks.append(
            create_record(
                REPOSITORIES.tasks,
                shard_task_draft.id,
                shard_task_draft,
            )
        )

    updated_split_request = split_request.model_copy(update={"status": ApprovalStatus.applied})
    update_record(
        REPOSITORIES.project_split_requests,
        split_request_id,
        updated_split_request,
        "project split request",
    )
    event = create_domain_event(
        split_applied_event(updated_split_request, shard_projects, shard_tasks, audit_context)
    )
    write_audit_log(
        audit_context,
        action="project_split_request.applied",
        target_type="project_split_request",
        target_id=split_request_id,
        payload={
            "source_project_id": source_project.id,
            "shard_project_ids": [project.id for project in shard_projects],
            "shard_task_ids": [task.id for task in shard_tasks],
        },
    )

    return ProjectSplitApplication(
        request_id=split_request_id,
        split_request=updated_split_request,
        source_project_id=source_project.id,
        shard_projects=shard_projects,
        shard_workspaces=shard_workspaces,
        shard_assignments=shard_assignments,
        shard_tasks=shard_tasks,
        events_emitted=[event],
    )


@app.post("/tasks", response_model=TaskRecord, status_code=201)
def create_task(task: TaskRecord, request: Request) -> TaskRecord:
    audit_context = audit_context_from_request(request)
    if not REPOSITORIES.projects.exists(task.project_id):
        raise HTTPException(status_code=400, detail=f"Unknown project: {task.project_id}")
    validate_task_breakdown(task)
    validate_task_assigned_agent_active(task, status_code=400)
    record = create_record(REPOSITORIES.tasks, task.id, task)
    write_audit_log(
        audit_context,
        action="task.created",
        target_type="task",
        target_id=record.id,
        payload={"project_id": record.project_id},
    )
    return record


@app.get("/tasks", response_model=list[TaskRecord])
def list_tasks(project_id: str | None = None) -> list[TaskRecord]:
    tasks = REPOSITORIES.tasks.list_records()
    if project_id is None:
        return tasks
    return [task for task in tasks if task.project_id == project_id]


@app.get("/tasks/review-queue", response_model=list[TaskRecord])
def list_task_review_queue(project_id: str | None = None) -> list[TaskRecord]:
    tasks = [
        task
        for task in REPOSITORIES.tasks.list_records()
        if is_task_reviewable(task)
        and (project_id is None or task.project_id == project_id)
    ]
    return sorted(tasks, key=lambda task: task.dead_lettered_at or task.created_at)


@app.get("/tasks/{task_id}", response_model=TaskRecord)
def read_task(task_id: str) -> TaskRecord:
    return read_record(REPOSITORIES.tasks, task_id, "task")


def incomplete_dependency_ids(task: TaskRecord) -> list[str]:
    incomplete: list[str] = []
    for dependency_id in task.depends_on:
        dependency = REPOSITORIES.tasks.get(dependency_id)
        if dependency is None or dependency.status != TaskStatus.completed:
            incomplete.append(dependency_id)
    return incomplete


@app.post("/tasks/{task_id}/start", response_model=TaskRecord)
def start_task(task_id: str, request: Request) -> TaskRecord:
    task = read_record(REPOSITORIES.tasks, task_id, "task")
    if task.status != TaskStatus.queued:
        raise HTTPException(status_code=409, detail=f"Task is already {task.status}")
    if task.attempt_count >= task.max_attempts:
        raise HTTPException(status_code=409, detail="Task reached max attempts")
    validate_task_assigned_agent_active(task, status_code=409)

    started_at = datetime.now(UTC)
    if task.retry_after_at is not None and task.retry_after_at > started_at:
        raise HTTPException(
            status_code=409,
            detail=f"Task retry backoff has not elapsed: {task.retry_after_at.isoformat()}",
        )

    incomplete_dependencies = incomplete_dependency_ids(task)
    if incomplete_dependencies:
        raise HTTPException(
            status_code=409,
            detail=f"Task dependencies are not completed: {incomplete_dependencies}",
        )

    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    lease_expires_at = started_at + task_lease_duration_from_request(request)
    lease_owner_id = audit_context.actor_id if audit_context is not None else None
    expected_status = task.status
    record = update_record_if(
        REPOSITORIES.tasks,
        task_id,
        task.model_copy(
            update={
                "status": TaskStatus.running,
                "attempt_count": task.attempt_count + 1,
                "lease_owner_id": lease_owner_id,
                "lease_expires_at": lease_expires_at,
                "last_heartbeat_at": started_at,
                "retry_after_at": None,
            }
        ),
        {"status": expected_status},
    )
    if record is None:
        current_task = read_record(REPOSITORIES.tasks, task_id, "task")
        raise HTTPException(status_code=409, detail=f"Task is already {current_task.status}")

    create_domain_event(
        EventRecord(
            type=EventType.task_started,
            source_agent_id=record.assigned_agent_id,
            target=record.project_id,
            payload={
                "task_id": record.id,
                "status": record.status,
                "attempt_count": record.attempt_count,
                "max_attempts": record.max_attempts,
                "lease_owner_id": record.lease_owner_id,
                "lease_expires_at": record.lease_expires_at.isoformat()
                if record.lease_expires_at is not None
                else None,
            },
            trace_id=trace_id,
        )
    )
    write_audit_log(
        audit_context,
        action="task.started",
        target_type="task",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "agent_id": record.assigned_agent_id,
            "attempt_count": record.attempt_count,
            "lease_expires_at": record.lease_expires_at.isoformat()
            if record.lease_expires_at is not None
            else None,
        },
    )
    return record


@app.post("/tasks/{task_id}/heartbeat", response_model=TaskRecord)
def heartbeat_task(task_id: str, request: Request) -> TaskRecord:
    task = read_record(REPOSITORIES.tasks, task_id, "task")
    if task.status != TaskStatus.running:
        raise HTTPException(status_code=409, detail=f"Task is not running: {task.status}")

    audit_context = audit_context_from_request(request)
    if (
        task.lease_owner_id is not None
        and audit_context is not None
        and task.lease_owner_id != audit_context.actor_id
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Task lease is owned by {task.lease_owner_id}",
        )

    trace_id = request.headers.get("x-synarch-trace-id")
    heartbeat_at = datetime.now(UTC)
    lease_expires_at = heartbeat_at + task_lease_duration_from_request(request)
    expected: dict[str, object] = {"status": TaskStatus.running}
    if task.lease_owner_id is not None:
        expected["lease_owner_id"] = task.lease_owner_id
    record = update_record_if(
        REPOSITORIES.tasks,
        task_id,
        task.model_copy(
            update={
                "lease_expires_at": lease_expires_at,
                "last_heartbeat_at": heartbeat_at,
            }
        ),
        expected,
    )
    if record is None:
        raise HTTPException(status_code=409, detail="Task lease changed before heartbeat")

    create_domain_event(
        EventRecord(
            type=EventType.task_heartbeat,
            source_agent_id=record.assigned_agent_id,
            target=record.project_id,
            payload={
                "task_id": record.id,
                "lease_owner_id": record.lease_owner_id,
                "lease_expires_at": record.lease_expires_at.isoformat()
                if record.lease_expires_at is not None
                else None,
                "last_heartbeat_at": record.last_heartbeat_at.isoformat()
                if record.last_heartbeat_at is not None
                else None,
            },
            trace_id=trace_id,
        )
    )
    write_audit_log(
        audit_context,
        action="task.heartbeat",
        target_type="task",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "lease_expires_at": record.lease_expires_at.isoformat()
            if record.lease_expires_at is not None
            else None,
        },
    )
    return record


@app.post("/tasks/recover-expired-leases", response_model=TaskLeaseRecoveryResult)
def recover_expired_task_leases(request: Request) -> TaskLeaseRecoveryResult:
    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    inspected_at = datetime.now(UTC)
    base_retry_backoff = task_retry_backoff_from_request(request)
    recovered_tasks: list[TaskRecord] = []
    failed_tasks: list[TaskRecord] = []
    events: list[EventRecord] = []

    for task in REPOSITORIES.tasks.list_records():
        if (
            task.status != TaskStatus.running
            or task.lease_expires_at is None
            or task.lease_expires_at > inspected_at
        ):
            continue

        should_retry = task.attempt_count < task.max_attempts
        retry_after_at = (
            inspected_at + task_retry_delay(task, base_retry_backoff) if should_retry else None
        )
        next_status = TaskStatus.queued if should_retry else TaskStatus.needs_review
        result = task.result
        if not should_retry:
            result = {
                "summary": "Task needs review because its lease expired after max attempts.",
                "reason": "lease_expired",
                "attempt_count": task.attempt_count,
                "max_attempts": task.max_attempts,
            }
        updated_task = task.model_copy(
            update={
                "status": next_status,
                "result": result,
                "lease_owner_id": None,
                "lease_expires_at": None,
                "last_heartbeat_at": None,
                "retry_after_at": retry_after_at,
                "dead_letter_reason": None if should_retry else "lease_expired",
                "dead_lettered_at": None if should_retry else inspected_at,
            }
        )
        record = update_record_if(
            REPOSITORIES.tasks,
            task.id,
            updated_task,
            {
                "status": TaskStatus.running,
                "lease_expires_at": task.lease_expires_at,
            },
        )
        if record is None:
            continue

        event = create_domain_event(
            EventRecord(
                type=EventType.task_lease_expired,
                source_agent_id=record.assigned_agent_id,
                target=record.project_id,
                payload={
                    "task_id": record.id,
                    "previous_lease_owner_id": task.lease_owner_id,
                    "expired_at": inspected_at.isoformat(),
                    "previous_lease_expires_at": task.lease_expires_at.isoformat(),
                    "attempt_count": task.attempt_count,
                    "max_attempts": task.max_attempts,
                    "next_status": record.status,
                    "will_retry": should_retry,
                    "retry_after_at": retry_after_at.isoformat()
                    if retry_after_at is not None
                    else None,
                    "dead_letter_reason": record.dead_letter_reason,
                },
                trace_id=trace_id,
            )
        )
        write_audit_log(
            audit_context,
            action="task.lease_expired",
            target_type="task",
            target_id=record.id,
            payload={
                "project_id": record.project_id,
                "next_status": record.status,
                "will_retry": should_retry,
                "retry_after_at": retry_after_at.isoformat()
                if retry_after_at is not None
                else None,
                "dead_letter_reason": record.dead_letter_reason,
            },
        )
        events.append(event)
        if should_retry:
            recovered_tasks.append(record)
        else:
            failed_tasks.append(record)

    return TaskLeaseRecoveryResult(
        inspected_at=inspected_at,
        recovered_task_ids=[task.id for task in recovered_tasks],
        failed_task_ids=[task.id for task in failed_tasks],
        recovered_tasks=recovered_tasks,
        failed_tasks=failed_tasks,
        events=events,
    )


def validate_review_assignment(task: TaskRecord) -> None:
    assigned_agent = REPOSITORIES.agents.get(task.assigned_agent_id)
    if assigned_agent is not None and assigned_agent.status != AgentStatus.active:
        raise HTTPException(
            status_code=400,
            detail=f"Agent is not active: {task.assigned_agent_id}",
        )


def is_task_reviewable(task: TaskRecord) -> bool:
    return task.status in {TaskStatus.needs_review, TaskStatus.blocked}


def reviewed_task_result(
    task: TaskRecord,
    *,
    decision: TaskReviewDecision,
    reviewed_at: datetime,
    next_status: TaskStatus,
) -> dict[str, Any]:
    result = task.result if isinstance(task.result, dict) else {}
    return {
        **result,
        "review": {
            "action": decision.action,
            "reason": decision.reason,
            "reviewed_at": reviewed_at.isoformat(),
            "next_status": next_status,
        },
    }


def task_review_update(
    task: TaskRecord,
    decision: TaskReviewDecision,
    reviewed_at: datetime,
) -> TaskRecord:
    update: dict[str, Any] = {
        "result": reviewed_task_result(
            task,
            decision=decision,
            reviewed_at=reviewed_at,
            next_status=TaskStatus.needs_review,
        )
    }
    if decision.title is not None:
        update["title"] = decision.title
    if decision.description is not None:
        update["description"] = decision.description
    if decision.assigned_agent_id is not None:
        update["assigned_agent_id"] = decision.assigned_agent_id
    if decision.acceptance_criteria is not None:
        update["acceptance_criteria"] = decision.acceptance_criteria
    if decision.max_attempts is not None:
        update["max_attempts"] = decision.max_attempts

    if decision.action == TaskReviewAction.retry:
        max_attempts = update.get("max_attempts", task.max_attempts)
        if max_attempts <= task.attempt_count:
            max_attempts = task.attempt_count + 1
        update.update(
            {
                "status": TaskStatus.queued,
                "max_attempts": max_attempts,
                "lease_owner_id": None,
                "lease_expires_at": None,
                "last_heartbeat_at": None,
                "retry_after_at": decision.retry_after_at,
                "dead_letter_reason": None,
                "dead_lettered_at": None,
            }
        )
    elif decision.action == TaskReviewAction.cancel:
        update.update(
            {
                "status": TaskStatus.failed,
                "lease_owner_id": None,
                "lease_expires_at": None,
                "last_heartbeat_at": None,
                "retry_after_at": None,
                "dead_letter_reason": task.dead_letter_reason or "review_cancelled",
                "dead_lettered_at": task.dead_lettered_at or reviewed_at,
            }
        )
    else:
        update["status"] = TaskStatus.needs_review

    updated_task = task.model_copy(update=update)
    validate_task_breakdown(updated_task)
    validate_review_assignment(updated_task)
    return updated_task.model_copy(
        update={
            "result": reviewed_task_result(
                updated_task,
                decision=decision,
                reviewed_at=reviewed_at,
                next_status=updated_task.status,
            )
        }
    )


@app.post("/tasks/{task_id}/review-decisions", response_model=TaskReviewResult)
def apply_task_review_decision(
    task_id: str,
    decision: TaskReviewDecision,
    request: Request,
) -> TaskReviewResult:
    task = read_record(REPOSITORIES.tasks, task_id, "task")
    if not is_task_reviewable(task):
        raise HTTPException(status_code=409, detail=f"Task is not in review: {task.status}")

    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    reviewed_at = datetime.now(UTC)
    updated_task = task_review_update(task, decision, reviewed_at)
    record = update_record_if(
        REPOSITORIES.tasks,
        task_id,
        updated_task,
        {"status": task.status},
    )
    if record is None:
        current_task = read_record(REPOSITORIES.tasks, task_id, "task")
        raise HTTPException(status_code=409, detail=f"Task is already {current_task.status}")

    event = create_domain_event(
        EventRecord(
            type=EventType.task_reviewed,
            source_agent_id=agent_event_source(
                audit_context.actor_type,
                audit_context.actor_id,
            )
            if audit_context is not None
            else None,
            target=record.project_id,
            payload={
                "task_id": record.id,
                "action": decision.action,
                "reason": decision.reason,
                "previous_status": task.status,
                "next_status": record.status,
                "attempt_count": record.attempt_count,
                "max_attempts": record.max_attempts,
                "retry_after_at": record.retry_after_at.isoformat()
                if record.retry_after_at is not None
                else None,
                "dead_letter_reason": record.dead_letter_reason,
            },
            trace_id=trace_id,
        )
    )
    audit_log = write_audit_log(
        audit_context,
        action="task.reviewed",
        target_type="task",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "action": decision.action,
            "next_status": record.status,
            "reason": decision.reason,
        },
    )
    return TaskReviewResult(task=record, event=event, audit_log=audit_log)


def task_result_payload(result: AgentResult) -> dict[str, Any]:
    return {
        "agent_id": result.agent_id,
        "summary": result.summary,
        "actions_taken": result.actions_taken,
        "sub_tasks_created": [
            task_draft.model_dump(mode="json") for task_draft in result.sub_tasks_created
        ],
        "lifecycle_requests_created": [
            lifecycle_request.model_dump(mode="json")
            for lifecycle_request in result.lifecycle_requests_created
        ],
        "events_emitted": [event.model_dump(mode="json") for event in result.events_emitted],
        "memory_candidates": [
            memory_item.model_dump(mode="json") for memory_item in result.memory_candidates
        ],
        "tool_calls_requested": [
            tool_call.model_dump(mode="json") for tool_call in result.tool_calls_requested
        ],
        "tool_results": [
            tool_result.model_dump(mode="json") for tool_result in result.tool_results
        ],
        "model_usage": result.model_usage.model_dump(mode="json")
        if result.model_usage is not None
        else None,
    }


def status_event_type(status: TaskStatus) -> EventType:
    if status == TaskStatus.running:
        return EventType.task_started
    if status == TaskStatus.completed:
        return EventType.task_completed
    if status == TaskStatus.blocked:
        return EventType.task_blocked
    return EventType.agent_reported


def task_status_event(task: TaskRecord, result: AgentResult, trace_id: str | None) -> EventRecord:
    return EventRecord(
        type=status_event_type(result.status),
        source_agent_id=result.agent_id,
        target=task.project_id,
        payload={
            "task_id": task.id,
            "status": result.status,
            "summary": result.summary,
        },
        trace_id=trace_id,
    )


def normalize_result_event(
    event: EventRecord,
    task: TaskRecord,
    result: AgentResult,
    trace_id: str | None,
) -> EventRecord:
    payload = {"task_id": task.id, **event.payload}
    return event.model_copy(
        update={
            "source_agent_id": event.source_agent_id or result.agent_id,
            "target": event.target or task.project_id,
            "payload": payload,
            "trace_id": event.trace_id or trace_id,
        }
    )


@app.post("/tasks/{task_id}/results", response_model=TaskRecord)
def record_task_result(
    task_id: str,
    result: AgentResult,
    request: Request,
) -> TaskRecord:
    if result.task_id != task_id:
        raise HTTPException(status_code=400, detail="Result task_id must match path")

    task = read_record(REPOSITORIES.tasks, task_id, "task")
    if result.agent_id != task.assigned_agent_id:
        raise HTTPException(
            status_code=400,
            detail=f"Result agent does not match assigned agent: {task.assigned_agent_id}",
        )

    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    updated_task = task.model_copy(
        update={
            "status": result.status,
            "result": task_result_payload(result),
            "lease_owner_id": None,
            "lease_expires_at": None,
            "last_heartbeat_at": None,
            "retry_after_at": None,
            "dead_letter_reason": None,
            "dead_lettered_at": None,
        }
    )
    record = update_record(REPOSITORIES.tasks, task_id, updated_task, "task")

    events = [
        normalize_result_event(event, record, result, trace_id) for event in result.events_emitted
    ]
    event_type = status_event_type(result.status)
    if not any(event.type == event_type for event in events):
        events.insert(0, task_status_event(record, result, trace_id))
    for event in events:
        create_domain_event(event)

    write_audit_log(
        audit_context,
        action="task.result_recorded",
        target_type="task",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "agent_id": result.agent_id,
            "status": result.status,
        },
    )
    return record


@app.post("/events", response_model=EventRecord, status_code=201)
def create_event(event: EventRecord, request: Request) -> EventRecord:
    audit_context = audit_context_from_request(request)
    record = create_record(REPOSITORIES.events, event.id, event)
    write_audit_log(
        audit_context,
        action="event.recorded",
        target_type="event",
        target_id=record.id,
        payload={"event_type": record.type},
    )
    return record


@app.get("/events", response_model=list[EventRecord])
def list_events(event_type: str | None = None, trace_id: str | None = None) -> list[EventRecord]:
    events = REPOSITORIES.events.list_records()
    if event_type is not None:
        events = [event for event in events if event.type == event_type]
    if trace_id is not None:
        events = [event for event in events if event.trace_id == trace_id]
    return sorted(events, key=lambda event: event.timestamp)


@app.get("/events/{event_id}", response_model=EventRecord)
def read_event(event_id: str) -> EventRecord:
    return read_record(REPOSITORIES.events, event_id, "event")


@app.post("/services", response_model=ServiceDefinition, status_code=201)
def create_service(service: ServiceDefinition, request: Request) -> ServiceDefinition:
    audit_context = audit_context_from_request(request)
    validate_service_definition(service)
    record = create_record(REPOSITORIES.services, service.id, service)
    write_audit_log(
        audit_context,
        action="service.created",
        target_type="service",
        target_id=record.id,
    )
    return record


@app.get("/services", response_model=list[ServiceDefinition])
def list_services(kind: str | None = None, enabled: bool | None = None) -> list[ServiceDefinition]:
    services = REPOSITORIES.services.list_records()
    if kind is not None:
        services = [service for service in services if service.kind == kind]
    if enabled is not None:
        services = [service for service in services if service.enabled == enabled]
    return services


@app.get("/services/{service_id}", response_model=ServiceDefinition)
def read_service(service_id: str) -> ServiceDefinition:
    return read_record(REPOSITORIES.services, service_id, "service")


def connector_job_payload(job: ConnectorJobRecord) -> dict[str, object]:
    return {
        "connector_job_id": job.id,
        "service_id": job.service_id,
        "project_id": job.project_id,
        "task_id": job.task_id,
        "owner_agent_id": job.owner_agent_id,
        "kind": job.kind,
        "status": job.status,
        "schedule": job.schedule,
        "webhook_path": job.webhook_path,
        "next_run_at": job.next_run_at,
    }


def connector_job_event(
    job: ConnectorJobRecord,
    event_type: EventType,
    trace_id: str | None,
    *,
    extra_payload: dict[str, object] | None = None,
) -> EventRecord:
    payload = connector_job_payload(job)
    if extra_payload is not None:
        payload.update(extra_payload)
    return EventRecord(
        type=event_type,
        source_agent_id=job.owner_agent_id,
        target=job.project_id or job.service_id,
        payload=payload,
        trace_id=trace_id,
    )


def connector_job_run_event(
    job: ConnectorJobRecord,
    run: ConnectorJobRunRecord,
    trace_id: str | None,
) -> EventRecord:
    return EventRecord(
        type=EventType.connector_job_run_recorded,
        source_agent_id=job.owner_agent_id,
        target=job.project_id or job.service_id,
        payload={
            **connector_job_payload(job),
            "connector_job_run_id": run.id,
            "run_status": run.status,
            "error": run.error,
        },
        trace_id=trace_id,
    )


def connector_job_tick_payload(
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
    }


def connector_job_tick_event(batch_result: ConnectorJobRunBatchResult) -> EventRecord:
    return EventRecord(
        type=EventType.connector_job_tick,
        target=(batch_result.project_id or batch_result.service_id or CONNECTOR_JOB_RUNNER_ID),
        payload=connector_job_tick_payload(batch_result),
        trace_id=batch_result.trace_id,
    )


def connector_job_tick_audit(
    batch_result: ConnectorJobRunBatchResult,
) -> AuditLogRecord:
    if batch_result.project_id is not None:
        target_type = "project"
        target_id = batch_result.project_id
    elif batch_result.service_id is not None:
        target_type = "service"
        target_id = batch_result.service_id
    else:
        target_type = "connector_job_runner"
        target_id = CONNECTOR_JOB_RUNNER_ID

    return AuditLogRecord(
        actor_type=ActorType.service,
        actor_id=CONNECTOR_JOB_RUNNER_ID,
        action="connector_job.tick",
        target_type=target_type,
        target_id=target_id,
        payload=connector_job_tick_payload(batch_result),
        trace_id=batch_result.trace_id,
    )


def create_connector_job_run_result(
    job: ConnectorJobRecord,
    run_request: ConnectorJobRunRequest,
    trace_id: str | None,
    audit_context: AuditContext | None,
) -> ConnectorJobRunResult:
    validate_connector_job_run_request(run_request)
    if job.status != ConnectorJobStatus.active:
        raise HTTPException(status_code=409, detail="Connector job is stopped")
    run = ConnectorJobRunRecord(
        job_id=job.id,
        service_id=job.service_id,
        project_id=job.project_id,
        task_id=job.task_id,
        owner_agent_id=job.owner_agent_id,
        status=run_request.status,
        triggered_by_type=run_request.triggered_by_type,
        triggered_by_id=run_request.triggered_by_id,
        trace_id=trace_id,
        output=run_request.output,
        error=run_request.error,
        started_at=run_request.started_at,
        completed_at=run_request.completed_at,
    )
    record = create_record(REPOSITORIES.connector_job_runs, run.id, run)
    event_job, policy_stop_reason = update_connector_job_after_run(job, record)
    event = create_domain_event(connector_job_run_event(event_job, record, trace_id))
    audit = write_audit_log(
        audit_context,
        action="connector_job.run_recorded",
        target_type="connector_job",
        target_id=job.id,
        payload={
            **connector_job_payload(event_job),
            "connector_job_run_id": record.id,
            "run_status": record.status,
        },
    )
    if policy_stop_reason is not None:
        record_connector_job_policy_stop(
            event_job,
            record,
            policy_stop_reason,
            trace_id,
            audit_context,
        )
    return ConnectorJobRunResult(run=record, event=event, audit_log=audit)


def update_connector_job_after_run(
    job: ConnectorJobRecord,
    run: ConnectorJobRunRecord,
) -> tuple[ConnectorJobRecord, str | None]:
    if job.status != ConnectorJobStatus.active:
        return job, None
    completed_at = utc_datetime(run.completed_at)
    stop_reason = connector_job_run_stop_reason(job, run)
    if stop_reason is not None:
        stopped_job = job.model_copy(
            update={
                "status": ConnectorJobStatus.stopped,
                "updated_at": completed_at,
                "next_run_at": None,
                "stopped_at": completed_at,
            }
        )
        record = update_record(
            REPOSITORIES.connector_jobs,
            job.id,
            stopped_job,
            "connector job",
        )
        return record, stop_reason

    if job.kind != ConnectorJobKind.cron:
        return job, None
    cooldown_seconds = (
        connector_job_failure_cooldown_seconds(job)
        if run.status == ConnectorJobRunStatus.failed
        else connector_job_cooldown_seconds(job)
    )
    updated_job = job.model_copy(
        update={
            "updated_at": completed_at,
            "next_run_at": completed_at + timedelta(seconds=cooldown_seconds),
        }
    )
    record = update_record(
        REPOSITORIES.connector_jobs,
        job.id,
        updated_job,
        "connector job",
    )
    return record, None


def record_connector_job_policy_stop(
    job: ConnectorJobRecord,
    run: ConnectorJobRunRecord,
    reason: str,
    trace_id: str | None,
    audit_context: AuditContext | None,
) -> None:
    stop_payload: dict[str, object] = {"reason": reason, "stopped_by_run_id": run.id}
    create_domain_event(
        connector_job_event(
            job,
            EventType.connector_job_stopped,
            trace_id,
            extra_payload=stop_payload,
        )
    )
    write_audit_log(
        audit_context,
        action="connector_job.stopped",
        target_type="connector_job",
        target_id=job.id,
        payload={**connector_job_payload(job), **stop_payload},
    )


@app.post("/connector-jobs", response_model=ConnectorJobMutationResult, status_code=201)
def create_connector_job(
    job: ConnectorJobRecord,
    request: Request,
) -> ConnectorJobMutationResult:
    validate_connector_job(job)
    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    record = create_record(REPOSITORIES.connector_jobs, job.id, job)
    event = create_domain_event(
        connector_job_event(record, EventType.connector_job_created, trace_id)
    )
    audit = write_audit_log(
        audit_context,
        action="connector_job.created",
        target_type="connector_job",
        target_id=record.id,
        payload=connector_job_payload(record),
    )
    return ConnectorJobMutationResult(job=record, event=event, audit_log=audit)


@app.get("/connector-jobs", response_model=list[ConnectorJobRecord])
def list_connector_jobs(
    service_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    owner_agent_id: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    last_run_status: ConnectorJobRunStatus | None = None,
    due_before: datetime | None = None,
) -> list[ConnectorJobRecord]:
    jobs = REPOSITORIES.connector_jobs.list_records()
    if service_id is not None:
        jobs = [job for job in jobs if job.service_id == service_id]
    if project_id is not None:
        jobs = [job for job in jobs if job.project_id == project_id]
    if task_id is not None:
        jobs = [job for job in jobs if job.task_id == task_id]
    if owner_agent_id is not None:
        jobs = [job for job in jobs if job.owner_agent_id == owner_agent_id]
    if kind is not None:
        jobs = [job for job in jobs if job.kind == kind]
    if status is not None:
        jobs = [job for job in jobs if job.status == status]
    if last_run_status is not None:
        jobs = [
            job
            for job in jobs
            if (latest_run := connector_job_latest_run(job.id)) is not None
            and latest_run.status == last_run_status
        ]
    if due_before is not None:
        jobs = [job for job in jobs if connector_job_is_due(job, due_before)]
        return sorted(jobs, key=connector_job_sort_key)
    return sorted(jobs, key=lambda job: (utc_datetime(job.created_at), job.id))


@app.post("/connector-jobs/tick", response_model=ConnectorJobRunBatchResult)
def tick_connector_jobs(
    request: Request,
    max_jobs: int = 1,
    kind: ConnectorJobKind = ConnectorJobKind.cron,
    service_id: str | None = None,
    project_id: str | None = None,
    owner_agent_id: str | None = None,
) -> ConnectorJobRunBatchResult:
    if max_jobs < 1 or max_jobs > MAX_CONNECTOR_JOB_TICK_JOBS:
        raise HTTPException(
            status_code=400,
            detail=f"max_jobs must be between 1 and {MAX_CONNECTOR_JOB_TICK_JOBS}",
        )

    trace_id = request.headers.get("x-synarch-trace-id") or (
        f"trace_connector_job_tick_{uuid4().hex[:12]}"
    )
    jobs = list_connector_jobs(
        service_id=service_id,
        project_id=project_id,
        owner_agent_id=owner_agent_id,
        kind=kind,
        status=ConnectorJobStatus.active,
        due_before=datetime.now(UTC),
    )
    selected_jobs = jobs[:max_jobs]
    runs = [
        create_connector_job_run_result(
            job,
            ConnectorJobRunRequest(
                status=ConnectorJobRunStatus.skipped,
                triggered_by_type=ActorType.service,
                triggered_by_id=CONNECTOR_JOB_RUNNER_ID,
                output={
                    "executed": False,
                    "reason": CONNECTOR_JOB_ADAPTER_NOT_WIRED_REASON,
                    "adapter_required": True,
                    "kind": job.kind,
                    "schedule": job.schedule,
                    "webhook_path": job.webhook_path,
                },
            ),
            trace_id,
            connector_job_runner_audit_context(request, trace_id),
        )
        for job in selected_jobs
    ]
    stop_reason = "max_jobs_reached" if len(jobs) > len(selected_jobs) else "no_ready_connector_job"
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
    tick_event = create_domain_event(connector_job_tick_event(batch_result))
    tick_audit = connector_job_tick_audit(batch_result)
    tick_audit_log = create_record(REPOSITORIES.audit_logs, tick_audit.id, tick_audit)
    return batch_result.model_copy(
        update={"tick_event": tick_event, "tick_audit_log": tick_audit_log}
    )


@app.get("/connector-jobs/{job_id}", response_model=ConnectorJobRecord)
def read_connector_job(job_id: str) -> ConnectorJobRecord:
    return read_record(REPOSITORIES.connector_jobs, job_id, "connector job")


@app.post(
    "/connector-jobs/{job_id}/runs",
    response_model=ConnectorJobRunResult,
    status_code=201,
)
def record_connector_job_run(
    job_id: str,
    run_request: ConnectorJobRunRequest,
    request: Request,
) -> ConnectorJobRunResult:
    job = read_record(REPOSITORIES.connector_jobs, job_id, "connector job")
    trace_id = request.headers.get("x-synarch-trace-id")
    return create_connector_job_run_result(
        job,
        run_request,
        trace_id,
        connector_job_run_audit_context(run_request, request),
    )


@app.get("/connector-job-runs", response_model=list[ConnectorJobRunRecord])
def list_connector_job_runs(
    job_id: str | None = None,
    service_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    owner_agent_id: str | None = None,
    status: str | None = None,
) -> list[ConnectorJobRunRecord]:
    runs = REPOSITORIES.connector_job_runs.list_records()
    if job_id is not None:
        runs = [run for run in runs if run.job_id == job_id]
    if service_id is not None:
        runs = [run for run in runs if run.service_id == service_id]
    if project_id is not None:
        runs = [run for run in runs if run.project_id == project_id]
    if task_id is not None:
        runs = [run for run in runs if run.task_id == task_id]
    if owner_agent_id is not None:
        runs = [run for run in runs if run.owner_agent_id == owner_agent_id]
    if status is not None:
        runs = [run for run in runs if run.status == status]
    return sorted(runs, key=lambda run: run.started_at)


@app.post("/connector-jobs/{job_id}/stop", response_model=ConnectorJobMutationResult)
def stop_connector_job(
    job_id: str,
    stop_request: ConnectorJobStopRequest,
    request: Request,
) -> ConnectorJobMutationResult:
    job = read_record(REPOSITORIES.connector_jobs, job_id, "connector job")
    if job.status == ConnectorJobStatus.stopped:
        raise HTTPException(status_code=409, detail="Connector job is already stopped")
    stopped_job = job.model_copy(
        update={
            "status": ConnectorJobStatus.stopped,
            "updated_at": stop_request.stopped_at,
            "next_run_at": None,
            "stopped_at": stop_request.stopped_at,
        }
    )
    record = update_record(REPOSITORIES.connector_jobs, job_id, stopped_job, "connector job")
    trace_id = request.headers.get("x-synarch-trace-id")
    event = create_domain_event(
        connector_job_event(
            record,
            EventType.connector_job_stopped,
            trace_id,
            extra_payload={"reason": stop_request.reason},
        )
    )
    audit = write_audit_log(
        connector_job_stop_audit_context(stop_request, request),
        action="connector_job.stopped",
        target_type="connector_job",
        target_id=record.id,
        payload={**connector_job_payload(record), "reason": stop_request.reason},
    )
    return ConnectorJobMutationResult(job=record, event=event, audit_log=audit)


@app.post("/connector-jobs/{job_id}/resume", response_model=ConnectorJobMutationResult)
def resume_connector_job(
    job_id: str,
    resume_request: ConnectorJobResumeRequest,
    request: Request,
) -> ConnectorJobMutationResult:
    job = read_record(REPOSITORIES.connector_jobs, job_id, "connector job")
    if job.status == ConnectorJobStatus.active:
        raise HTTPException(status_code=409, detail="Connector job is already active")
    resumed_at = utc_datetime(resume_request.resumed_at)
    resumed_job = job.model_copy(
        update={
            "status": ConnectorJobStatus.active,
            "updated_at": resumed_at,
            "next_run_at": utc_datetime(resume_request.next_run_at)
            if resume_request.next_run_at is not None
            else resumed_at,
            "stopped_at": None,
        }
    )
    validate_connector_job(resumed_job)
    record = update_record(REPOSITORIES.connector_jobs, job_id, resumed_job, "connector job")
    trace_id = request.headers.get("x-synarch-trace-id")
    event = create_domain_event(
        connector_job_event(
            record,
            EventType.connector_job_resumed,
            trace_id,
            extra_payload={"reason": resume_request.reason},
        )
    )
    audit = write_audit_log(
        connector_job_resume_audit_context(resume_request, request),
        action="connector_job.resumed",
        target_type="connector_job",
        target_id=record.id,
        payload={**connector_job_payload(record), "reason": resume_request.reason},
    )
    return ConnectorJobMutationResult(job=record, event=event, audit_log=audit)


@app.post("/skills", response_model=SkillDefinition, status_code=201)
def create_skill(skill: SkillDefinition, request: Request) -> SkillDefinition:
    audit_context = audit_context_from_request(request)
    validate_skill_definition(skill)
    record = create_record(REPOSITORIES.skills, skill.id, skill)
    write_audit_log(
        audit_context,
        action="skill.created",
        target_type="skill",
        target_id=record.id,
    )
    return record


@app.get("/skills", response_model=list[SkillDefinition])
def list_skills(enabled: bool | None = None) -> list[SkillDefinition]:
    skills = REPOSITORIES.skills.list_records()
    if enabled is not None:
        skills = [skill for skill in skills if skill.enabled == enabled]
    return skills


@app.get("/skills/{skill_id}", response_model=SkillDefinition)
def read_skill(skill_id: str) -> SkillDefinition:
    return read_record(REPOSITORIES.skills, skill_id, "skill")


@app.post("/model-providers", response_model=ModelProviderConfig, status_code=201)
def create_model_provider(provider: ModelProviderConfig, request: Request) -> ModelProviderConfig:
    audit_context = audit_context_from_request(request)
    record = create_record(REPOSITORIES.model_providers, provider.id, provider)
    write_audit_log(
        audit_context,
        action="model_provider.created",
        target_type="model_provider",
        target_id=record.id,
    )
    return record


@app.get("/model-providers", response_model=list[ModelProviderConfig])
def list_model_providers(enabled: bool | None = None) -> list[ModelProviderConfig]:
    providers = REPOSITORIES.model_providers.list_records()
    if enabled is None:
        return providers
    return [provider for provider in providers if provider.enabled == enabled]


@app.get("/model-providers/{provider_id}", response_model=ModelProviderConfig)
def read_model_provider(provider_id: str) -> ModelProviderConfig:
    return read_record(REPOSITORIES.model_providers, provider_id, "model provider")


@app.post("/model-definitions", response_model=ModelDefinition, status_code=201)
def create_model_definition(model: ModelDefinition, request: Request) -> ModelDefinition:
    audit_context = audit_context_from_request(request)
    if not REPOSITORIES.model_providers.exists(model.provider_id):
        raise HTTPException(status_code=400, detail=f"Unknown model provider: {model.provider_id}")
    record = create_record(REPOSITORIES.model_definitions, model.id, model)
    write_audit_log(
        audit_context,
        action="model_definition.created",
        target_type="model_definition",
        target_id=record.id,
        payload={"provider_id": record.provider_id},
    )
    return record


@app.get("/model-definitions", response_model=list[ModelDefinition])
def list_model_definitions(
    provider_id: str | None = None,
    enabled: bool | None = None,
) -> list[ModelDefinition]:
    models = REPOSITORIES.model_definitions.list_records()
    if provider_id is not None:
        models = [model for model in models if model.provider_id == provider_id]
    if enabled is not None:
        models = [model for model in models if model.enabled == enabled]
    return models


@app.get("/model-definitions/{model_id:path}", response_model=ModelDefinition)
def read_model_definition(model_id: str) -> ModelDefinition:
    return read_record(REPOSITORIES.model_definitions, model_id, "model definition")


@app.post("/model-policies", response_model=ModelPolicy, status_code=201)
def create_model_policy(policy: ModelPolicy, request: Request) -> ModelPolicy:
    audit_context = audit_context_from_request(request)
    model_ids = {policy.default_model_id, *policy.allowed_model_ids}
    unknown_model_ids = sorted(
        model_id for model_id in model_ids if not REPOSITORIES.model_definitions.exists(model_id)
    )
    if unknown_model_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model definitions: {unknown_model_ids}",
        )
    record = create_record(REPOSITORIES.model_policies, policy.id, policy)
    write_audit_log(
        audit_context,
        action="model_policy.created",
        target_type="model_policy",
        target_id=record.id,
        payload={"default_model_id": record.default_model_id},
    )
    return record


@app.get("/model-policies", response_model=list[ModelPolicy])
def list_model_policies() -> list[ModelPolicy]:
    return REPOSITORIES.model_policies.list_records()


@app.get("/model-policies/{policy_id}", response_model=ModelPolicy)
def read_model_policy(policy_id: str) -> ModelPolicy:
    return read_record(REPOSITORIES.model_policies, policy_id, "model policy")


@app.post("/cost-records", response_model=CostRecord, status_code=201)
def create_cost_record(cost: CostRecord, request: Request) -> CostRecord:
    audit_context = audit_context_from_request(request)
    if not REPOSITORIES.model_definitions.exists(cost.model_id):
        raise HTTPException(status_code=400, detail=f"Unknown model definition: {cost.model_id}")
    if not REPOSITORIES.model_providers.exists(cost.provider_id):
        raise HTTPException(status_code=400, detail=f"Unknown model provider: {cost.provider_id}")
    record = create_record(REPOSITORIES.cost_records, cost.id, cost)
    create_domain_event(
        EventRecord(
            type=EventType.cost_recorded,
            source_agent_id=record.agent_id,
            target=record.project_id or record.task_id,
            payload={
                "cost_id": record.id,
                "provider_id": record.provider_id,
                "model_id": record.model_id,
                "task_id": record.task_id,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_cost": record.total_cost,
                "currency": record.currency,
            },
            trace_id=record.trace_id or request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="cost.recorded",
        target_type="cost_record",
        target_id=record.id,
        payload={"project_id": record.project_id, "task_id": record.task_id},
    )
    return record


@app.get("/cost-records", response_model=list[CostRecord])
def list_cost_records(
    project_id: str | None = None,
    agent_id: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    trace_id: str | None = None,
) -> list[CostRecord]:
    costs = REPOSITORIES.cost_records.list_records()
    if project_id is not None:
        costs = [cost for cost in costs if cost.project_id == project_id]
    if agent_id is not None:
        costs = [cost for cost in costs if cost.agent_id == agent_id]
    if provider_id is not None:
        costs = [cost for cost in costs if cost.provider_id == provider_id]
    if model_id is not None:
        costs = [cost for cost in costs if cost.model_id == model_id]
    if trace_id is not None:
        costs = [cost for cost in costs if cost.trace_id == trace_id]
    return costs


@app.get("/cost-records/{cost_id}", response_model=CostRecord)
def read_cost_record(cost_id: str) -> CostRecord:
    return read_record(REPOSITORIES.cost_records, cost_id, "cost record")


@app.post("/audit-logs", response_model=AuditLogRecord, status_code=201)
def create_audit_log(audit: AuditLogRecord) -> AuditLogRecord:
    return create_record(REPOSITORIES.audit_logs, audit.id, audit)


@app.get("/audit-logs", response_model=list[AuditLogRecord])
def list_audit_logs(
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    trace_id: str | None = None,
) -> list[AuditLogRecord]:
    audits = REPOSITORIES.audit_logs.list_records()
    if actor_id is not None:
        audits = [audit for audit in audits if audit.actor_id == actor_id]
    if target_type is not None:
        audits = [audit for audit in audits if audit.target_type == target_type]
    if target_id is not None:
        audits = [audit for audit in audits if audit.target_id == target_id]
    if trace_id is not None:
        audits = [audit for audit in audits if audit.trace_id == trace_id]
    return audits


@app.get("/audit-logs/{audit_id}", response_model=AuditLogRecord)
def read_audit_log(audit_id: str) -> AuditLogRecord:
    return read_record(REPOSITORIES.audit_logs, audit_id, "audit log")


def human_assistance_payload(request_record: HumanAssistanceRequest) -> dict[str, object]:
    return {
        "human_assistance_request_id": request_record.id,
        "project_id": request_record.project_id,
        "task_id": request_record.task_id,
        "agent_id": request_record.agent_id,
        "kind": request_record.kind,
        "title": request_record.title,
        "urgency": request_record.urgency,
        "status": request_record.status,
    }


def task_human_assistance_resolution_payload(
    task: TaskRecord,
    request_record: HumanAssistanceRequest,
    resolution: HumanAssistanceResolution,
    next_status: TaskStatus,
) -> dict[str, object]:
    return {
        "human_assistance_request_id": request_record.id,
        "task_id": task.id,
        "project_id": task.project_id,
        "kind": request_record.kind,
        "status": resolution.status,
        "response": resolution.response,
        "resolved_by_type": resolution.resolved_by_type,
        "resolved_by_id": resolution.resolved_by_id,
        "resolved_at": resolution.resolved_at.isoformat(),
        "next_status": next_status,
    }


def task_result_with_human_assistance_resolution(
    task: TaskRecord,
    request_record: HumanAssistanceRequest,
    resolution: HumanAssistanceResolution,
    next_status: TaskStatus,
) -> dict[str, Any]:
    result = task.result if isinstance(task.result, dict) else {}
    resolution_payload = task_human_assistance_resolution_payload(
        task,
        request_record,
        resolution,
        next_status,
    )
    previous_resolutions = result.get("human_assistance_resolutions")
    if not isinstance(previous_resolutions, list):
        previous_resolutions = []
    return {
        **result,
        "last_human_assistance_resolution": resolution_payload,
        "human_assistance_resolutions": [*previous_resolutions, resolution_payload],
    }


def resolve_linked_human_assistance_task(
    request_record: HumanAssistanceRequest,
    resolution: HumanAssistanceResolution,
    audit_context: AuditContext | None,
    trace_id: str | None,
) -> EventRecord | None:
    if request_record.task_id is None:
        return None
    task = REPOSITORIES.tasks.get(request_record.task_id)
    if task is None or task.status not in {TaskStatus.blocked, TaskStatus.needs_review}:
        return None

    if resolution.status == HumanAssistanceStatus.answered:
        next_status = TaskStatus.queued
        max_attempts = task.max_attempts
        if max_attempts <= task.attempt_count:
            max_attempts = task.attempt_count + 1
        update = {
            "status": next_status,
            "max_attempts": max_attempts,
            "lease_owner_id": None,
            "lease_expires_at": None,
            "last_heartbeat_at": None,
            "retry_after_at": None,
            "dead_letter_reason": None,
            "dead_lettered_at": None,
        }
    else:
        next_status = TaskStatus.needs_review
        update = {
            "status": next_status,
            "lease_owner_id": None,
            "lease_expires_at": None,
            "last_heartbeat_at": None,
            "retry_after_at": None,
            "dead_letter_reason": task.dead_letter_reason
            or "human_assistance_dismissed",
            "dead_lettered_at": task.dead_lettered_at or resolution.resolved_at,
        }

    updated_task = task.model_copy(
        update={
            **update,
            "result": task_result_with_human_assistance_resolution(
                task,
                request_record,
                resolution,
                next_status,
            ),
        }
    )
    record = update_record_if(
        REPOSITORIES.tasks,
        task.id,
        updated_task,
        {"status": task.status},
    )
    if record is None:
        return None

    event = create_domain_event(
        EventRecord(
            type=EventType.task_reviewed,
            source_agent_id=agent_event_source(
                audit_context.actor_type,
                audit_context.actor_id,
            )
            if audit_context is not None
            else None,
            target=record.project_id,
            payload={
                "task_id": record.id,
                "action": "human_assistance_resolved",
                "previous_status": task.status,
                "next_status": record.status,
                "human_assistance_request_id": request_record.id,
                "human_assistance_status": resolution.status,
            },
            trace_id=trace_id,
        )
    )
    write_audit_log(
        audit_context,
        action="task.human_assistance_applied",
        target_type="task",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "previous_status": task.status,
            "next_status": record.status,
            "human_assistance_request_id": request_record.id,
            "human_assistance_status": resolution.status,
        },
    )
    return event


@app.post(
    "/human-assistance-requests",
    response_model=HumanAssistanceRequest,
    status_code=201,
)
def create_human_assistance_request(
    assistance_request: HumanAssistanceRequest,
    request: Request,
) -> HumanAssistanceRequest:
    validate_human_assistance_request(assistance_request)
    audit_context = audit_context_from_request(request)
    record = create_record(
        REPOSITORIES.human_assistance_requests,
        assistance_request.id,
        assistance_request,
    )
    create_domain_event(
        EventRecord(
            type=EventType.human_assistance_requested,
            source_agent_id=agent_event_source(
                record.requested_by_type,
                record.requested_by_id,
            ),
            target=record.project_id,
            payload=human_assistance_payload(record),
            trace_id=request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="human_assistance_request.created",
        target_type="human_assistance_request",
        target_id=record.id,
        payload=human_assistance_payload(record),
    )
    return record


@app.get("/human-assistance-requests", response_model=list[HumanAssistanceRequest])
def list_human_assistance_requests(
    project_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    kind: HumanAssistanceKind | None = None,
    status: HumanAssistanceStatus | None = None,
) -> list[HumanAssistanceRequest]:
    assistance_requests = REPOSITORIES.human_assistance_requests.list_records()
    if project_id is not None:
        assistance_requests = [
            assistance_request
            for assistance_request in assistance_requests
            if assistance_request.project_id == project_id
        ]
    if task_id is not None:
        assistance_requests = [
            assistance_request
            for assistance_request in assistance_requests
            if assistance_request.task_id == task_id
        ]
    if agent_id is not None:
        assistance_requests = [
            assistance_request
            for assistance_request in assistance_requests
            if assistance_request.agent_id == agent_id
        ]
    if kind is not None:
        assistance_requests = [
            assistance_request
            for assistance_request in assistance_requests
            if assistance_request.kind == kind
        ]
    if status is not None:
        assistance_requests = [
            assistance_request
            for assistance_request in assistance_requests
            if assistance_request.status == status
        ]
    return sorted(assistance_requests, key=lambda item: item.created_at)


@app.get(
    "/human-assistance-requests/{request_id}",
    response_model=HumanAssistanceRequest,
)
def read_human_assistance_request(request_id: str) -> HumanAssistanceRequest:
    return read_record(
        REPOSITORIES.human_assistance_requests,
        request_id,
        "human assistance request",
    )


@app.post(
    "/human-assistance-requests/{request_id}/resolutions",
    response_model=HumanAssistanceResolution,
    status_code=201,
)
def resolve_human_assistance_request(
    request_id: str,
    resolution: HumanAssistanceResolution,
    request: Request,
) -> HumanAssistanceResolution:
    if resolution.request_id != request_id:
        raise HTTPException(status_code=400, detail="Resolution request_id must match path")
    if resolution.status not in {
        HumanAssistanceStatus.answered,
        HumanAssistanceStatus.dismissed,
    }:
        raise HTTPException(
            status_code=400,
            detail="Human assistance resolution must be answered or dismissed",
        )

    assistance_request = read_record(
        REPOSITORIES.human_assistance_requests,
        request_id,
        "human assistance request",
    )
    if assistance_request.status != HumanAssistanceStatus.requested:
        raise HTTPException(
            status_code=409,
            detail=f"Human assistance request is already {assistance_request.status}",
        )

    resolved_request = assistance_request.model_copy(
        update={
            "status": resolution.status,
            "response": resolution.response,
            "resolved_by_type": resolution.resolved_by_type,
            "resolved_by_id": resolution.resolved_by_id,
            "resolved_at": resolution.resolved_at,
        }
    )
    update_record(
        REPOSITORIES.human_assistance_requests,
        request_id,
        resolved_request,
        "human assistance request",
    )
    trace_id = request.headers.get("x-synarch-trace-id")
    audit_context = audit_context_from_request(request) or AuditContext(
        actor_type=resolution.resolved_by_type,
        actor_id=resolution.resolved_by_id,
        trace_id=trace_id,
    )
    event = create_domain_event(
        EventRecord(
            type=EventType.human_assistance_resolved,
            source_agent_id=agent_event_source(
                resolution.resolved_by_type,
                resolution.resolved_by_id,
            ),
            target=assistance_request.project_id,
            payload={
                **human_assistance_payload(resolved_request),
                "response": resolution.response,
            },
            trace_id=trace_id,
        )
    )
    task_event = resolve_linked_human_assistance_task(
        resolved_request,
        resolution,
        audit_context,
        trace_id,
    )
    write_audit_log(
        audit_context,
        action=f"human_assistance_request.{resolution.status}",
        target_type="human_assistance_request",
        target_id=request_id,
        payload={
            **human_assistance_payload(resolved_request),
            "response": resolution.response,
        },
    )
    events_emitted = [event]
    if task_event is not None:
        events_emitted.append(task_event)
    return resolution.model_copy(update={"events_emitted": events_emitted})


@app.post(
    "/credential-access-requests",
    response_model=CredentialAccessRequest,
    status_code=201,
)
def create_credential_access_request(
    access_request: CredentialAccessRequest,
    request: Request,
) -> CredentialAccessRequest:
    validate_credential_access_request(access_request)
    audit_context = audit_context_from_request(request)
    record = create_record(
        REPOSITORIES.credential_access_requests,
        access_request.id,
        access_request,
    )
    create_domain_event(
        EventRecord(
            type=EventType.approval_requested,
            source_agent_id=agent_event_source(
                record.requested_by_type,
                record.requested_by_id,
            ),
            target=record.project_id,
            payload={
                "request_type": "credential_access",
                "credential_access_request_id": record.id,
                "task_id": record.task_id,
                "agent_id": record.agent_id,
                "tool_name": record.tool_name,
                "requested_scopes": record.requested_scopes,
                "candidate_service_ids": record.candidate_service_ids,
                "status": record.status,
            },
            trace_id=request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="credential_access_request.created",
        target_type="credential_access_request",
        target_id=record.id,
        payload={
            "project_id": record.project_id,
            "task_id": record.task_id,
            "agent_id": record.agent_id,
            "tool_name": record.tool_name,
            "requested_scopes": record.requested_scopes,
            "status": record.status,
        },
    )
    return record


@app.get("/credential-access-requests", response_model=list[CredentialAccessRequest])
def list_credential_access_requests(
    project_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    status: str | None = None,
) -> list[CredentialAccessRequest]:
    access_requests = REPOSITORIES.credential_access_requests.list_records()
    if project_id is not None:
        access_requests = [
            access_request
            for access_request in access_requests
            if access_request.project_id == project_id
        ]
    if task_id is not None:
        access_requests = [
            access_request
            for access_request in access_requests
            if access_request.task_id == task_id
        ]
    if agent_id is not None:
        access_requests = [
            access_request
            for access_request in access_requests
            if access_request.agent_id == agent_id
        ]
    if status is not None:
        access_requests = [
            access_request for access_request in access_requests if access_request.status == status
        ]
    return sorted(access_requests, key=lambda access_request: access_request.created_at)


@app.get("/credential-access-requests/{request_id}", response_model=CredentialAccessRequest)
def read_credential_access_request(request_id: str) -> CredentialAccessRequest:
    return read_record(
        REPOSITORIES.credential_access_requests,
        request_id,
        "credential access request",
    )


def credential_access_decided_event(
    access_request: CredentialAccessRequest,
    decision: CredentialAccessDecision,
    trace_id: str | None,
) -> EventRecord:
    return EventRecord(
        type=EventType.approval_decided,
        source_agent_id=agent_event_source(decision.decided_by_type, decision.decided_by_id),
        target=access_request.project_id,
        payload={
            "request_type": "credential_access",
            "credential_access_request_id": access_request.id,
            "task_id": access_request.task_id,
            "agent_id": access_request.agent_id,
            "tool_name": access_request.tool_name,
            "status": decision.status,
            "rationale": decision.rationale,
        },
        trace_id=trace_id,
    )


@app.post(
    "/credential-access-requests/{request_id}/decisions",
    response_model=CredentialAccessDecision,
    status_code=201,
)
def decide_credential_access_request(
    request_id: str,
    decision: CredentialAccessDecision,
    request: Request,
) -> CredentialAccessDecision:
    if decision.request_id != request_id:
        raise HTTPException(status_code=400, detail="Decision request_id must match path")
    if decision.status not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(
            status_code=400,
            detail="Credential access decisions must be approved or rejected",
        )

    access_request = read_record(
        REPOSITORIES.credential_access_requests,
        request_id,
        "credential access request",
    )
    if access_request.status != ApprovalStatus.requested:
        raise HTTPException(
            status_code=409,
            detail=f"Credential access request is already {access_request.status}",
        )

    context = credential_decision_audit_context(decision, request)
    event = create_domain_event(
        credential_access_decided_event(access_request, decision, context.trace_id)
    )
    update_record(
        REPOSITORIES.credential_access_requests,
        request_id,
        access_request.model_copy(update={"status": decision.status}),
        "credential access request",
    )
    write_audit_log(
        context,
        action=f"credential_access_request.{decision.status}",
        target_type="credential_access_request",
        target_id=request_id,
        payload={
            "project_id": access_request.project_id,
            "task_id": access_request.task_id,
            "agent_id": access_request.agent_id,
            "tool_name": access_request.tool_name,
            "rationale": decision.rationale,
        },
    )
    return decision.model_copy(update={"events_emitted": [event]})


def credential_grant_id(request_id: str, service_id: str) -> str:
    safe_request_id = "".join(
        character if character.isalnum() else "_"
        for character in request_id
    ).strip("_")
    safe_service_id = "".join(
        character if character.isalnum() else "_"
        for character in service_id
    ).strip("_")
    return f"credential_grant_{safe_request_id}_{safe_service_id}"


def merged_scopes(existing_scopes: list[str], granted_scopes: list[str]) -> list[str]:
    merged: list[str] = []
    for scope in [*existing_scopes, *granted_scopes]:
        if scope not in merged:
            merged.append(scope)
    return merged


def credential_grant_applied_event(
    access_request: CredentialAccessRequest,
    grant: CredentialGrant,
    trace_id: str | None,
) -> EventRecord:
    return EventRecord(
        type=EventType.credential_grant_applied,
        source_agent_id=agent_event_source(grant.granted_by_type, grant.granted_by_id),
        target=access_request.project_id,
        payload={
            "request_type": "credential_access",
            "credential_access_request_id": access_request.id,
            "credential_grant_id": grant.id,
            "service_id": grant.service_id,
            "task_id": access_request.task_id,
            "agent_id": access_request.agent_id,
            "tool_name": access_request.tool_name,
            "granted_scopes": grant.scopes,
            "status": ApprovalStatus.applied,
        },
        trace_id=trace_id,
    )


@app.post(
    "/credential-access-requests/{request_id}/grant-applications",
    response_model=CredentialGrantApplication,
    status_code=201,
)
def apply_credential_access_grant(
    request_id: str,
    application: CredentialGrantApplicationRequest,
    request: Request,
) -> CredentialGrantApplication:
    if application.request_id != request_id:
        raise HTTPException(status_code=400, detail="Application request_id must match path")

    access_request = read_record(
        REPOSITORIES.credential_access_requests,
        request_id,
        "credential access request",
    )
    if access_request.status == ApprovalStatus.applied:
        raise HTTPException(
            status_code=409,
            detail="Credential access request is already applied",
        )
    if access_request.status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=409,
            detail="Credential access request must be approved before grants can be applied",
        )
    if application.service_id not in access_request.candidate_service_ids:
        raise HTTPException(
            status_code=400,
            detail="Grant service_id must be one of the candidate services",
        )

    service = read_record(REPOSITORIES.services, application.service_id, "service")
    if access_request.tool_name not in service.capabilities:
        raise HTTPException(
            status_code=400,
            detail="Grant service must expose the requested tool",
        )

    context = credential_grant_application_audit_context(application, request)
    grant = CredentialGrant(
        id=credential_grant_id(request_id, application.service_id),
        request_id=request_id,
        service_id=application.service_id,
        agent_id=access_request.agent_id,
        project_id=access_request.project_id,
        task_id=access_request.task_id,
        tool_name=access_request.tool_name,
        scopes=list(access_request.requested_scopes),
        granted_by_type=application.applied_by_type,
        granted_by_id=application.applied_by_id,
        rationale=application.rationale,
    )
    created_grant = create_record(REPOSITORIES.credential_grants, grant.id, grant)
    updated_service = update_record(
        REPOSITORIES.services,
        service.id,
        service.model_copy(
            update={
                "credential_scopes": merged_scopes(
                    service.credential_scopes,
                    access_request.requested_scopes,
                )
            }
        ),
        "service",
    )
    updated_request = update_record(
        REPOSITORIES.credential_access_requests,
        request_id,
        access_request.model_copy(update={"status": ApprovalStatus.applied}),
        "credential access request",
    )
    event = create_domain_event(
        credential_grant_applied_event(updated_request, created_grant, context.trace_id)
    )
    write_audit_log(
        context,
        action="credential_access_request.applied",
        target_type="credential_access_request",
        target_id=request_id,
        payload={
            "project_id": access_request.project_id,
            "task_id": access_request.task_id,
            "agent_id": access_request.agent_id,
            "tool_name": access_request.tool_name,
            "service_id": application.service_id,
            "credential_grant_id": created_grant.id,
            "granted_scopes": created_grant.scopes,
            "rationale": application.rationale,
        },
    )
    return CredentialGrantApplication(
        request_id=request_id,
        service_id=application.service_id,
        access_request=updated_request,
        grant=created_grant,
        service=updated_service,
        events_emitted=[event],
    )


@app.get("/credential-grants", response_model=list[CredentialGrant])
def list_credential_grants(
    request_id: str | None = None,
    service_id: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    active: bool | None = None,
) -> list[CredentialGrant]:
    grants = REPOSITORIES.credential_grants.list_records()
    if request_id is not None:
        grants = [grant for grant in grants if grant.request_id == request_id]
    if service_id is not None:
        grants = [grant for grant in grants if grant.service_id == service_id]
    if agent_id is not None:
        grants = [grant for grant in grants if grant.agent_id == agent_id]
    if project_id is not None:
        grants = [grant for grant in grants if grant.project_id == project_id]
    if active is not None:
        grants = [grant for grant in grants if grant.active == active]
    return sorted(grants, key=lambda grant: grant.created_at)


@app.post("/agent-lifecycle-requests", response_model=AgentLifecycleRequest, status_code=201)
def create_agent_lifecycle_request(
    lifecycle_request: AgentLifecycleRequest,
    request: Request,
) -> AgentLifecycleRequest:
    validate_lifecycle_request(lifecycle_request)
    validate_no_pending_lifecycle_conflict(lifecycle_request)
    audit_context = audit_context_from_request(request)
    record = create_record(
        REPOSITORIES.agent_lifecycle_requests,
        lifecycle_request.id,
        lifecycle_request,
    )
    create_domain_event(
        EventRecord(
            type=EventType.approval_requested,
            source_agent_id=agent_event_source(record.requested_by_type, record.requested_by_id),
            target=record.id,
            payload={
                "lifecycle_action": record.action,
                "requested_by_type": record.requested_by_type,
                "requested_by_id": record.requested_by_id,
                "status": record.status,
            },
            trace_id=request.headers.get("x-synarch-trace-id"),
        )
    )
    write_audit_log(
        audit_context,
        action="agent_lifecycle_request.created",
        target_type="agent_lifecycle_request",
        target_id=record.id,
        payload={"lifecycle_action": record.action, "status": record.status},
    )
    return record


@app.get("/agent-lifecycle-requests", response_model=list[AgentLifecycleRequest])
def list_agent_lifecycle_requests(
    requested_by_id: str | None = None,
    status: str | None = None,
) -> list[AgentLifecycleRequest]:
    requests = REPOSITORIES.agent_lifecycle_requests.list_records()
    if requested_by_id is not None:
        requests = [request for request in requests if request.requested_by_id == requested_by_id]
    if status is not None:
        requests = [request for request in requests if request.status == status]
    return requests


@app.get("/agent-lifecycle-requests/{request_id}", response_model=AgentLifecycleRequest)
def read_agent_lifecycle_request(request_id: str) -> AgentLifecycleRequest:
    return read_record(
        REPOSITORIES.agent_lifecycle_requests,
        request_id,
        "agent lifecycle request",
    )


def approval_decided_event(
    lifecycle_request: AgentLifecycleRequest,
    decision: AgentLifecycleDecision,
    trace_id: str | None,
) -> EventRecord:
    return EventRecord(
        type=EventType.approval_decided,
        source_agent_id=agent_event_source(decision.decided_by_type, decision.decided_by_id),
        target=lifecycle_request.id,
        payload={
            "lifecycle_action": lifecycle_request.action,
            "status": decision.status,
            "rationale": decision.rationale,
        },
        trace_id=trace_id,
    )


def apply_agent_lifecycle_request(
    lifecycle_request: AgentLifecycleRequest,
    decision_context: AuditContext,
) -> list[EventRecord]:
    if lifecycle_request.action == LifecycleAction.create_agent:
        proposed_agent = lifecycle_request.proposed_agent
        if proposed_agent is None:
            raise HTTPException(status_code=400, detail="create_agent requires proposed_agent")
        validate_agent_model_policy(proposed_agent)
        created_agent = create_record(REPOSITORIES.agents, proposed_agent.id, proposed_agent)
        write_audit_log(
            decision_context,
            action="agent.created",
            target_type="agent",
            target_id=created_agent.id,
            payload={"lifecycle_request_id": lifecycle_request.id},
        )
        events = [
            create_domain_event(
                EventRecord(
                    type=EventType.agent_created,
                    source_agent_id=agent_event_source(
                        decision_context.actor_type,
                        decision_context.actor_id,
                    ),
                    target=created_agent.id,
                    payload={"lifecycle_request_id": lifecycle_request.id},
                    trace_id=decision_context.trace_id,
                )
            ),
        ]
        if lifecycle_request.proposed_soul is not None:
            _created_soul, soul_event = create_agent_soul_record(
                lifecycle_request.proposed_soul,
                decision_context,
            )
            events.append(soul_event)
        return events

    if lifecycle_request.action == LifecycleAction.update_agent:
        target_agent_id = lifecycle_request.target_agent_id
        proposed_agent = lifecycle_request.proposed_agent
        if target_agent_id is None:
            raise HTTPException(status_code=400, detail="update_agent requires target_agent_id")
        if proposed_agent is None:
            raise HTTPException(status_code=400, detail="update_agent requires proposed_agent")
        current_agent = read_record(REPOSITORIES.agents, target_agent_id, "agent")
        validate_agent_model_policy(proposed_agent)
        updated_agent = proposed_agent.model_copy(
            update={
                "created_at": current_agent.created_at,
                "created_by": current_agent.created_by,
                "updated_at": datetime.now(UTC),
            }
        )
        changed_fields = agent_update_changed_fields(current_agent, updated_agent)
        update_record(REPOSITORIES.agents, target_agent_id, updated_agent, "agent")
        write_audit_log(
            decision_context,
            action="agent.updated",
            target_type="agent",
            target_id=target_agent_id,
            payload={
                "lifecycle_request_id": lifecycle_request.id,
                "changed_fields": changed_fields,
            },
        )
        events = [
            create_domain_event(
                EventRecord(
                    type=EventType.agent_updated,
                    source_agent_id=agent_event_source(
                        decision_context.actor_type,
                        decision_context.actor_id,
                    ),
                    target=target_agent_id,
                    payload={
                        "lifecycle_request_id": lifecycle_request.id,
                        "changed_fields": changed_fields,
                    },
                    trace_id=decision_context.trace_id,
                )
            ),
        ]
        if lifecycle_request.proposed_soul is not None:
            deactivate_active_agent_soul(
                target_agent_id,
                decision_context,
                lifecycle_request_id=lifecycle_request.id,
            )
            _created_soul, soul_event = create_agent_soul_record(
                lifecycle_request.proposed_soul,
                decision_context,
            )
            events.append(soul_event)
        return events

    if lifecycle_request.action == LifecycleAction.deactivate_agent:
        target_agent_id = lifecycle_request.target_agent_id
        if target_agent_id is None:
            raise HTTPException(status_code=400, detail="deactivate_agent requires target_agent_id")
        agent = read_record(REPOSITORIES.agents, target_agent_id, "agent")
        deactivated_agent = agent.model_copy(
            update={
                "status": AgentStatus.inactive,
                "updated_at": datetime.now(UTC),
            }
        )
        update_record(REPOSITORIES.agents, target_agent_id, deactivated_agent, "agent")
        write_audit_log(
            decision_context,
            action="agent.deactivated",
            target_type="agent",
            target_id=target_agent_id,
            payload={"lifecycle_request_id": lifecycle_request.id},
        )
        return [
            create_domain_event(
                EventRecord(
                    type=EventType.agent_deactivated,
                    source_agent_id=agent_event_source(
                        decision_context.actor_type,
                        decision_context.actor_id,
                    ),
                    target=target_agent_id,
                    payload={"lifecycle_request_id": lifecycle_request.id},
                    trace_id=decision_context.trace_id,
                )
            ),
        ]

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported lifecycle action: {lifecycle_request.action}",
    )


@app.post(
    "/agent-lifecycle-requests/{request_id}/decisions",
    response_model=AgentLifecycleDecision,
    status_code=201,
)
def decide_agent_lifecycle_request(
    request_id: str,
    decision: AgentLifecycleDecision,
    request: Request,
) -> AgentLifecycleDecision:
    if decision.request_id != request_id:
        raise HTTPException(status_code=400, detail="Decision request_id must match path")
    if decision.status not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(
            status_code=400,
            detail="Lifecycle decisions must be approved or rejected",
        )

    lifecycle_request = read_record(
        REPOSITORIES.agent_lifecycle_requests,
        request_id,
        "agent lifecycle request",
    )
    if lifecycle_request.status != ApprovalStatus.requested:
        raise HTTPException(
            status_code=409,
            detail=f"Lifecycle request is already {lifecycle_request.status}",
        )

    context = decision_audit_context(decision, request)
    events = [
        create_domain_event(approval_decided_event(lifecycle_request, decision, context.trace_id))
    ]
    final_status = decision.status
    if decision.status == ApprovalStatus.approved:
        events.extend(apply_agent_lifecycle_request(lifecycle_request, context))
        final_status = ApprovalStatus.applied

    updated_request = lifecycle_request.model_copy(update={"status": final_status})
    update_record(
        REPOSITORIES.agent_lifecycle_requests,
        request_id,
        updated_request,
        "agent lifecycle request",
    )
    write_audit_log(
        context,
        action=f"agent_lifecycle_request.{final_status}",
        target_type="agent_lifecycle_request",
        target_id=request_id,
        payload={"lifecycle_action": lifecycle_request.action, "rationale": decision.rationale},
    )

    return decision.model_copy(update={"status": final_status, "events_emitted": events})
