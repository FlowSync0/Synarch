from fastapi import FastAPI, HTTPException

from synarch_models import (
    AgentDefinition,
    AgentLifecycleRequest,
    AuditLogRecord,
    CostRecord,
    DivisionRecord,
    EventRecord,
    HealthResponse,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ProjectRecord,
    ServiceDefinition,
    TaskRecord,
)
from synarch_state_service.repositories import RecordRepository, StateRepositories

app = FastAPI(title="Synarch State Service", version="0.1.0")

REPOSITORIES = StateRepositories.in_memory()


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


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="state-service")


@app.post("/divisions", response_model=DivisionRecord, status_code=201)
def create_division(division: DivisionRecord) -> DivisionRecord:
    return create_record(REPOSITORIES.divisions, division.id, division)


@app.get("/divisions", response_model=list[DivisionRecord])
def list_divisions() -> list[DivisionRecord]:
    return REPOSITORIES.divisions.list_records()


@app.get("/divisions/{division_id}", response_model=DivisionRecord)
def read_division(division_id: str) -> DivisionRecord:
    return read_record(REPOSITORIES.divisions, division_id, "division")


@app.post("/agents", response_model=AgentDefinition, status_code=201)
def create_agent(agent: AgentDefinition) -> AgentDefinition:
    if agent.model_policy_id is not None and not REPOSITORIES.model_policies.exists(
        agent.model_policy_id
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model policy: {agent.model_policy_id}",
        )
    return create_record(REPOSITORIES.agents, agent.id, agent)


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
def create_project(project: ProjectRecord) -> ProjectRecord:
    return create_record(REPOSITORIES.projects, project.id, project)


@app.get("/projects", response_model=list[ProjectRecord])
def list_projects() -> list[ProjectRecord]:
    return REPOSITORIES.projects.list_records()


@app.get("/projects/{project_id}", response_model=ProjectRecord)
def read_project(project_id: str) -> ProjectRecord:
    return read_record(REPOSITORIES.projects, project_id, "project")


@app.post("/tasks", response_model=TaskRecord, status_code=201)
def create_task(task: TaskRecord) -> TaskRecord:
    if not REPOSITORIES.projects.exists(task.project_id):
        raise HTTPException(status_code=400, detail=f"Unknown project: {task.project_id}")
    return create_record(REPOSITORIES.tasks, task.id, task)


@app.get("/tasks", response_model=list[TaskRecord])
def list_tasks(project_id: str | None = None) -> list[TaskRecord]:
    tasks = REPOSITORIES.tasks.list_records()
    if project_id is None:
        return tasks
    return [task for task in tasks if task.project_id == project_id]


@app.get("/tasks/{task_id}", response_model=TaskRecord)
def read_task(task_id: str) -> TaskRecord:
    return read_record(REPOSITORIES.tasks, task_id, "task")


@app.post("/events", response_model=EventRecord, status_code=201)
def create_event(event: EventRecord) -> EventRecord:
    return create_record(REPOSITORIES.events, event.id, event)


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
def create_service(service: ServiceDefinition) -> ServiceDefinition:
    return create_record(REPOSITORIES.services, service.id, service)


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
def create_model_provider(provider: ModelProviderConfig) -> ModelProviderConfig:
    return create_record(REPOSITORIES.model_providers, provider.id, provider)


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
def create_model_definition(model: ModelDefinition) -> ModelDefinition:
    if not REPOSITORIES.model_providers.exists(model.provider_id):
        raise HTTPException(status_code=400, detail=f"Unknown model provider: {model.provider_id}")
    return create_record(REPOSITORIES.model_definitions, model.id, model)


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
def create_model_policy(policy: ModelPolicy) -> ModelPolicy:
    model_ids = {policy.default_model_id, *policy.allowed_model_ids}
    unknown_model_ids = sorted(
        model_id for model_id in model_ids if not REPOSITORIES.model_definitions.exists(model_id)
    )
    if unknown_model_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model definitions: {unknown_model_ids}",
        )
    return create_record(REPOSITORIES.model_policies, policy.id, policy)


@app.get("/model-policies", response_model=list[ModelPolicy])
def list_model_policies() -> list[ModelPolicy]:
    return REPOSITORIES.model_policies.list_records()


@app.get("/model-policies/{policy_id}", response_model=ModelPolicy)
def read_model_policy(policy_id: str) -> ModelPolicy:
    return read_record(REPOSITORIES.model_policies, policy_id, "model policy")


@app.post("/cost-records", response_model=CostRecord, status_code=201)
def create_cost_record(cost: CostRecord) -> CostRecord:
    if not REPOSITORIES.model_definitions.exists(cost.model_id):
        raise HTTPException(status_code=400, detail=f"Unknown model definition: {cost.model_id}")
    if not REPOSITORIES.model_providers.exists(cost.provider_id):
        raise HTTPException(status_code=400, detail=f"Unknown model provider: {cost.provider_id}")
    return create_record(REPOSITORIES.cost_records, cost.id, cost)


@app.get("/cost-records", response_model=list[CostRecord])
def list_cost_records(
    project_id: str | None = None,
    agent_id: str | None = None,
    trace_id: str | None = None,
) -> list[CostRecord]:
    costs = REPOSITORIES.cost_records.list_records()
    if project_id is not None:
        costs = [cost for cost in costs if cost.project_id == project_id]
    if agent_id is not None:
        costs = [cost for cost in costs if cost.agent_id == agent_id]
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
def create_agent_lifecycle_request(request: AgentLifecycleRequest) -> AgentLifecycleRequest:
    return create_record(REPOSITORIES.agent_lifecycle_requests, request.id, request)


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
