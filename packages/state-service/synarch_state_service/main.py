import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from synarch_models import (
    ActorType,
    AgentDefinition,
    AgentLifecycleDecision,
    AgentLifecycleRequest,
    AgentResult,
    AgentStatus,
    ApprovalStatus,
    AuditLogRecord,
    CostRecord,
    DivisionRecord,
    EventRecord,
    EventType,
    HealthResponse,
    LifecycleAction,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ProjectRecord,
    ServiceDefinition,
    TaskRecord,
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


def write_audit_log(
    context: AuditContext | None,
    *,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if context is None:
        return

    audit = AuditLogRecord(
        actor_type=context.actor_type,
        actor_id=context.actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        trace_id=context.trace_id,
        payload=payload or {},
    )
    create_record(REPOSITORIES.audit_logs, audit.id, audit)


def create_domain_event(event: EventRecord) -> EventRecord:
    return create_record(REPOSITORIES.events, event.id, event)


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


def validate_lifecycle_request(lifecycle_request: AgentLifecycleRequest) -> None:
    if lifecycle_request.action == LifecycleAction.create_agent:
        if lifecycle_request.proposed_agent is None:
            raise HTTPException(
                status_code=400,
                detail="create_agent requires proposed_agent",
            )
        validate_agent_model_policy(lifecycle_request.proposed_agent)
        if REPOSITORIES.agents.exists(lifecycle_request.proposed_agent.id):
            raise HTTPException(
                status_code=409,
                detail=f"Record already exists: {lifecycle_request.proposed_agent.id}",
            )
        return

    if lifecycle_request.action == LifecycleAction.deactivate_agent:
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


@app.get("/agents", response_model=list[AgentDefinition])
def list_agents(division: str | None = None) -> list[AgentDefinition]:
    agents = REPOSITORIES.agents.list_records()
    if division is None:
        return agents
    return [agent for agent in agents if agent.division == division]


@app.get("/agents/{agent_id}", response_model=AgentDefinition)
def read_agent(agent_id: str) -> AgentDefinition:
    return read_record(REPOSITORIES.agents, agent_id, "agent")


@app.post("/projects", response_model=ProjectRecord, status_code=201)
def create_project(project: ProjectRecord, request: Request) -> ProjectRecord:
    audit_context = audit_context_from_request(request)
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


@app.post("/tasks", response_model=TaskRecord, status_code=201)
def create_task(task: TaskRecord, request: Request) -> TaskRecord:
    audit_context = audit_context_from_request(request)
    if not REPOSITORIES.projects.exists(task.project_id):
        raise HTTPException(status_code=400, detail=f"Unknown project: {task.project_id}")
    assigned_agent = REPOSITORIES.agents.get(task.assigned_agent_id)
    if assigned_agent is not None and assigned_agent.status != AgentStatus.active:
        raise HTTPException(
            status_code=400,
            detail=f"Agent is not active: {task.assigned_agent_id}",
        )
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

    incomplete_dependencies = incomplete_dependency_ids(task)
    if incomplete_dependencies:
        raise HTTPException(
            status_code=409,
            detail=f"Task dependencies are not completed: {incomplete_dependencies}",
        )

    audit_context = audit_context_from_request(request)
    trace_id = request.headers.get("x-synarch-trace-id")
    record = update_record(
        REPOSITORIES.tasks,
        task_id,
        task.model_copy(update={"status": TaskStatus.running}),
        "task",
    )
    create_domain_event(
        EventRecord(
            type=EventType.task_started,
            source_agent_id=record.assigned_agent_id,
            target=record.project_id,
            payload={"task_id": record.id, "status": record.status},
            trace_id=trace_id,
        )
    )
    write_audit_log(
        audit_context,
        action="task.started",
        target_type="task",
        target_id=record.id,
        payload={"project_id": record.project_id, "agent_id": record.assigned_agent_id},
    )
    return record


def task_result_payload(result: AgentResult) -> dict[str, Any]:
    return {
        "agent_id": result.agent_id,
        "summary": result.summary,
        "actions_taken": result.actions_taken,
        "sub_tasks_created": [
            task_draft.model_dump(mode="json") for task_draft in result.sub_tasks_created
        ],
        "events_emitted": [event.model_dump(mode="json") for event in result.events_emitted],
        "memory_candidates": [
            memory_item.model_dump(mode="json") for memory_item in result.memory_candidates
        ],
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
        }
    )
    record = update_record(REPOSITORIES.tasks, task_id, updated_task, "task")

    events = [
        normalize_result_event(event, record, result, trace_id)
        for event in result.events_emitted
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
    return events


@app.get("/events/{event_id}", response_model=EventRecord)
def read_event(event_id: str) -> EventRecord:
    return read_record(REPOSITORIES.events, event_id, "event")


@app.post("/services", response_model=ServiceDefinition, status_code=201)
def create_service(service: ServiceDefinition, request: Request) -> ServiceDefinition:
    audit_context = audit_context_from_request(request)
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


@app.post("/agent-lifecycle-requests", response_model=AgentLifecycleRequest, status_code=201)
def create_agent_lifecycle_request(
    lifecycle_request: AgentLifecycleRequest,
    request: Request,
) -> AgentLifecycleRequest:
    validate_lifecycle_request(lifecycle_request)
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
) -> EventRecord:
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
        return EventRecord(
            type=EventType.agent_created,
            source_agent_id=agent_event_source(
                decision_context.actor_type,
                decision_context.actor_id,
            ),
            target=created_agent.id,
            payload={"lifecycle_request_id": lifecycle_request.id},
            trace_id=decision_context.trace_id,
        )

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
        return EventRecord(
            type=EventType.agent_deactivated,
            source_agent_id=agent_event_source(
                decision_context.actor_type,
                decision_context.actor_id,
            ),
            target=target_agent_id,
            payload={"lifecycle_request_id": lifecycle_request.id},
            trace_id=decision_context.trace_id,
        )

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
        events.append(
            create_domain_event(apply_agent_lifecycle_request(lifecycle_request, context))
        )
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
