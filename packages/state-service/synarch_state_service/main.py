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

app = FastAPI(title="Synarch State Service", version="0.1.0")

DIVISIONS: dict[str, DivisionRecord] = {}
AGENTS: dict[str, AgentDefinition] = {}
PROJECTS: dict[str, ProjectRecord] = {}
TASKS: dict[str, TaskRecord] = {}
EVENTS: dict[str, EventRecord] = {}
SERVICES: dict[str, ServiceDefinition] = {}
MODEL_PROVIDERS: dict[str, ModelProviderConfig] = {}
MODEL_DEFINITIONS: dict[str, ModelDefinition] = {}
MODEL_POLICIES: dict[str, ModelPolicy] = {}
COST_RECORDS: dict[str, CostRecord] = {}
AUDIT_LOGS: dict[str, AuditLogRecord] = {}
AGENT_LIFECYCLE_REQUESTS: dict[str, AgentLifecycleRequest] = {}


def create_record[RecordT](
    store: dict[str, RecordT],
    record_id: str,
    record: RecordT,
) -> RecordT:
    if record_id in store:
        raise HTTPException(status_code=409, detail=f"Record already exists: {record_id}")
    store[record_id] = record
    return record


def read_record[RecordT](store: dict[str, RecordT], record_id: str, label: str) -> RecordT:
    if record_id not in store:
        raise HTTPException(status_code=404, detail=f"Unknown {label}: {record_id}")
    return store[record_id]


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="state-service")


@app.post("/divisions", response_model=DivisionRecord, status_code=201)
def create_division(division: DivisionRecord) -> DivisionRecord:
    return create_record(DIVISIONS, division.id, division)


@app.get("/divisions", response_model=list[DivisionRecord])
def list_divisions() -> list[DivisionRecord]:
    return list(DIVISIONS.values())


@app.get("/divisions/{division_id}", response_model=DivisionRecord)
def read_division(division_id: str) -> DivisionRecord:
    return read_record(DIVISIONS, division_id, "division")


@app.post("/agents", response_model=AgentDefinition, status_code=201)
def create_agent(agent: AgentDefinition) -> AgentDefinition:
    if agent.model_policy_id is not None and agent.model_policy_id not in MODEL_POLICIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model policy: {agent.model_policy_id}",
        )
    return create_record(AGENTS, agent.id, agent)


@app.get("/agents", response_model=list[AgentDefinition])
def list_agents(division: str | None = None) -> list[AgentDefinition]:
    agents = list(AGENTS.values())
    if division is None:
        return agents
    return [agent for agent in agents if agent.division == division]


@app.get("/agents/{agent_id}", response_model=AgentDefinition)
def read_agent(agent_id: str) -> AgentDefinition:
    return read_record(AGENTS, agent_id, "agent")


@app.post("/projects", response_model=ProjectRecord, status_code=201)
def create_project(project: ProjectRecord) -> ProjectRecord:
    return create_record(PROJECTS, project.id, project)


@app.get("/projects", response_model=list[ProjectRecord])
def list_projects() -> list[ProjectRecord]:
    return list(PROJECTS.values())


@app.get("/projects/{project_id}", response_model=ProjectRecord)
def read_project(project_id: str) -> ProjectRecord:
    return read_record(PROJECTS, project_id, "project")


@app.post("/tasks", response_model=TaskRecord, status_code=201)
def create_task(task: TaskRecord) -> TaskRecord:
    if task.project_id not in PROJECTS:
        raise HTTPException(status_code=400, detail=f"Unknown project: {task.project_id}")
    return create_record(TASKS, task.id, task)


@app.get("/tasks", response_model=list[TaskRecord])
def list_tasks(project_id: str | None = None) -> list[TaskRecord]:
    tasks = list(TASKS.values())
    if project_id is None:
        return tasks
    return [task for task in tasks if task.project_id == project_id]


@app.get("/tasks/{task_id}", response_model=TaskRecord)
def read_task(task_id: str) -> TaskRecord:
    return read_record(TASKS, task_id, "task")


@app.post("/events", response_model=EventRecord, status_code=201)
def create_event(event: EventRecord) -> EventRecord:
    return create_record(EVENTS, event.id, event)


@app.get("/events", response_model=list[EventRecord])
def list_events(event_type: str | None = None, trace_id: str | None = None) -> list[EventRecord]:
    events = list(EVENTS.values())
    if event_type is not None:
        events = [event for event in events if event.type == event_type]
    if trace_id is not None:
        events = [event for event in events if event.trace_id == trace_id]
    return events


@app.get("/events/{event_id}", response_model=EventRecord)
def read_event(event_id: str) -> EventRecord:
    return read_record(EVENTS, event_id, "event")


@app.post("/services", response_model=ServiceDefinition, status_code=201)
def create_service(service: ServiceDefinition) -> ServiceDefinition:
    return create_record(SERVICES, service.id, service)


@app.get("/services", response_model=list[ServiceDefinition])
def list_services(kind: str | None = None, enabled: bool | None = None) -> list[ServiceDefinition]:
    services = list(SERVICES.values())
    if kind is not None:
        services = [service for service in services if service.kind == kind]
    if enabled is not None:
        services = [service for service in services if service.enabled == enabled]
    return services


@app.get("/services/{service_id}", response_model=ServiceDefinition)
def read_service(service_id: str) -> ServiceDefinition:
    return read_record(SERVICES, service_id, "service")


@app.post("/model-providers", response_model=ModelProviderConfig, status_code=201)
def create_model_provider(provider: ModelProviderConfig) -> ModelProviderConfig:
    return create_record(MODEL_PROVIDERS, provider.id, provider)


@app.get("/model-providers", response_model=list[ModelProviderConfig])
def list_model_providers(enabled: bool | None = None) -> list[ModelProviderConfig]:
    providers = list(MODEL_PROVIDERS.values())
    if enabled is None:
        return providers
    return [provider for provider in providers if provider.enabled == enabled]


@app.get("/model-providers/{provider_id}", response_model=ModelProviderConfig)
def read_model_provider(provider_id: str) -> ModelProviderConfig:
    return read_record(MODEL_PROVIDERS, provider_id, "model provider")


@app.post("/model-definitions", response_model=ModelDefinition, status_code=201)
def create_model_definition(model: ModelDefinition) -> ModelDefinition:
    if model.provider_id not in MODEL_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown model provider: {model.provider_id}")
    return create_record(MODEL_DEFINITIONS, model.id, model)


@app.get("/model-definitions", response_model=list[ModelDefinition])
def list_model_definitions(
    provider_id: str | None = None,
    enabled: bool | None = None,
) -> list[ModelDefinition]:
    models = list(MODEL_DEFINITIONS.values())
    if provider_id is not None:
        models = [model for model in models if model.provider_id == provider_id]
    if enabled is not None:
        models = [model for model in models if model.enabled == enabled]
    return models


@app.get("/model-definitions/{model_id:path}", response_model=ModelDefinition)
def read_model_definition(model_id: str) -> ModelDefinition:
    return read_record(MODEL_DEFINITIONS, model_id, "model definition")


@app.post("/model-policies", response_model=ModelPolicy, status_code=201)
def create_model_policy(policy: ModelPolicy) -> ModelPolicy:
    model_ids = {policy.default_model_id, *policy.allowed_model_ids}
    unknown_model_ids = sorted(
        model_id for model_id in model_ids if model_id not in MODEL_DEFINITIONS
    )
    if unknown_model_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model definitions: {unknown_model_ids}",
        )
    return create_record(MODEL_POLICIES, policy.id, policy)


@app.get("/model-policies", response_model=list[ModelPolicy])
def list_model_policies() -> list[ModelPolicy]:
    return list(MODEL_POLICIES.values())


@app.get("/model-policies/{policy_id}", response_model=ModelPolicy)
def read_model_policy(policy_id: str) -> ModelPolicy:
    return read_record(MODEL_POLICIES, policy_id, "model policy")


@app.post("/cost-records", response_model=CostRecord, status_code=201)
def create_cost_record(cost: CostRecord) -> CostRecord:
    if cost.model_id not in MODEL_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown model definition: {cost.model_id}")
    if cost.provider_id not in MODEL_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown model provider: {cost.provider_id}")
    return create_record(COST_RECORDS, cost.id, cost)


@app.get("/cost-records", response_model=list[CostRecord])
def list_cost_records(
    project_id: str | None = None,
    agent_id: str | None = None,
    trace_id: str | None = None,
) -> list[CostRecord]:
    costs = list(COST_RECORDS.values())
    if project_id is not None:
        costs = [cost for cost in costs if cost.project_id == project_id]
    if agent_id is not None:
        costs = [cost for cost in costs if cost.agent_id == agent_id]
    if trace_id is not None:
        costs = [cost for cost in costs if cost.trace_id == trace_id]
    return costs


@app.get("/cost-records/{cost_id}", response_model=CostRecord)
def read_cost_record(cost_id: str) -> CostRecord:
    return read_record(COST_RECORDS, cost_id, "cost record")


@app.post("/audit-logs", response_model=AuditLogRecord, status_code=201)
def create_audit_log(audit: AuditLogRecord) -> AuditLogRecord:
    return create_record(AUDIT_LOGS, audit.id, audit)


@app.get("/audit-logs", response_model=list[AuditLogRecord])
def list_audit_logs(
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    trace_id: str | None = None,
) -> list[AuditLogRecord]:
    audits = list(AUDIT_LOGS.values())
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
    return read_record(AUDIT_LOGS, audit_id, "audit log")


@app.post("/agent-lifecycle-requests", response_model=AgentLifecycleRequest, status_code=201)
def create_agent_lifecycle_request(request: AgentLifecycleRequest) -> AgentLifecycleRequest:
    return create_record(AGENT_LIFECYCLE_REQUESTS, request.id, request)


@app.get("/agent-lifecycle-requests", response_model=list[AgentLifecycleRequest])
def list_agent_lifecycle_requests(
    requested_by_id: str | None = None,
    status: str | None = None,
) -> list[AgentLifecycleRequest]:
    requests = list(AGENT_LIFECYCLE_REQUESTS.values())
    if requested_by_id is not None:
        requests = [request for request in requests if request.requested_by_id == requested_by_id]
    if status is not None:
        requests = [request for request in requests if request.status == status]
    return requests


@app.get("/agent-lifecycle-requests/{request_id}", response_model=AgentLifecycleRequest)
def read_agent_lifecycle_request(request_id: str) -> AgentLifecycleRequest:
    return read_record(AGENT_LIFECYCLE_REQUESTS, request_id, "agent lifecycle request")
