import os
from typing import NoReturn

from fastapi import FastAPI, HTTPException, Request

from synarch_models import (
    AgentDefinition,
    AgentLifecycleDecision,
    AgentLifecycleRequest,
    HealthResponse,
    LocalWorldView,
    ServiceDefinition,
    SkillDefinition,
)

from .agent_sources import (
    AgentSource,
    AgentSourceRequestError,
    AgentSourceUnavailable,
    SeedAgentSource,
    StateServiceAgentSource,
)

app = FastAPI(title="Synarch Control Plane", version="0.1.0")


def default_agent_source() -> AgentSource:
    state_service_url = os.getenv("STATE_SERVICE_URL")
    if state_service_url:
        return StateServiceAgentSource(state_service_url)
    return SeedAgentSource()


AGENT_SOURCE: AgentSource = default_agent_source()


def set_agent_source(agent_source: AgentSource | None = None) -> None:
    global AGENT_SOURCE
    AGENT_SOURCE = agent_source or default_agent_source()


def get_agent_or_404(agent_id: str) -> AgentDefinition:
    try:
        agent = AGENT_SOURCE.get_agent(agent_id)
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")
    return agent


def list_agents_from_source() -> list[AgentDefinition]:
    try:
        return AGENT_SOURCE.list_agents()
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error


def source_request_headers(request: Request) -> dict[str, str]:
    forwarded_headers = (
        "x-synarch-actor-type",
        "x-synarch-actor-id",
        "x-synarch-trace-id",
    )
    return {
        header: request.headers[header] for header in forwarded_headers if header in request.headers
    }


def raise_source_error(error: AgentSourceRequestError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


def access_rule_matches_agent(
    agent: AgentDefinition,
    *,
    allowed_agent_ids: list[str],
    allowed_divisions: list[str],
) -> bool:
    if allowed_agent_ids and agent.id not in allowed_agent_ids:
        return False
    return not (allowed_divisions and agent.division not in allowed_divisions)


def required_tools_are_allowed(agent: AgentDefinition, required_tools: list[str]) -> bool:
    denied_tools = set(agent.permissions.denied_tools)
    if denied_tools.intersection(required_tools):
        return False
    allowed_tools = set(agent.permissions.allowed_tools)
    return not required_tools or set(required_tools).issubset(allowed_tools)


def service_capabilities_available_to_agent(
    agent: AgentDefinition,
    service: ServiceDefinition,
) -> list[str]:
    allowed_tools = set(agent.permissions.allowed_tools)
    denied_tools = set(agent.permissions.denied_tools)
    return [
        capability
        for capability in service.capabilities
        if capability in allowed_tools and capability not in denied_tools
    ]


def service_is_available_to_agent(agent: AgentDefinition, service: ServiceDefinition) -> bool:
    if not service.enabled:
        return False
    if not access_rule_matches_agent(
        agent,
        allowed_agent_ids=service.allowed_agent_ids,
        allowed_divisions=service.allowed_divisions,
    ):
        return False
    if service.capabilities and not service_capabilities_available_to_agent(agent, service):
        return False
    if service.owner_agent_id is None or service.owner_agent_id == agent.id:
        return True
    return bool(
        service.allowed_agent_ids
        or service.allowed_divisions
        or service_capabilities_available_to_agent(agent, service)
    )


def skill_is_available_to_agent(agent: AgentDefinition, skill: SkillDefinition) -> bool:
    if not skill.enabled:
        return False
    if skill.id not in agent.capabilities.skills:
        return False
    if not access_rule_matches_agent(
        agent,
        allowed_agent_ids=skill.allowed_agent_ids,
        allowed_divisions=skill.allowed_divisions,
    ):
        return False
    return required_tools_are_allowed(agent, skill.required_tools)


def list_available_services(agent: AgentDefinition) -> list[ServiceDefinition]:
    try:
        services = AGENT_SOURCE.list_services()
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error

    return [service for service in services if service_is_available_to_agent(agent, service)]


def list_available_connector_ids(services: list[ServiceDefinition]) -> list[str]:
    connector_kinds = {"external", "ai_provider", "tool_provider"}
    return [service.id for service in services if service.kind in connector_kinds]


def list_available_skill_ids(agent: AgentDefinition) -> list[str]:
    try:
        skills = AGENT_SOURCE.list_skills()
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error
    return [skill.id for skill in skills if skill_is_available_to_agent(agent, skill)]


def world_view_policy_labels(agent: AgentDefinition) -> list[str]:
    policies = [
        "least_privilege_tools",
        "event_log_required",
        "memory_budget_required",
    ]
    if agent.model_policy_id is None:
        return policies

    try:
        policy = AGENT_SOURCE.get_model_policy(agent.model_policy_id)
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error

    if policy is None:
        policies.append(f"missing_model_policy:{agent.model_policy_id}")
        return policies

    policies.append(f"model_policy:{policy.id}")
    policies.append(f"default_model:{policy.default_model_id}")
    return policies


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="control-plane")


@app.get("/agents", response_model=list[AgentDefinition])
def list_agents() -> list[AgentDefinition]:
    return list_agents_from_source()


@app.get("/agents/{agent_id}", response_model=AgentDefinition)
def read_agent(agent_id: str) -> AgentDefinition:
    return get_agent_or_404(agent_id)


@app.get("/agents/{agent_id}/world-view", response_model=LocalWorldView)
def read_world_view(agent_id: str) -> LocalWorldView:
    agent = get_agent_or_404(agent_id)
    agents = list_agents_from_source()
    try:
        soul = AGENT_SOURCE.get_agent_soul(agent.id)
        assignments = AGENT_SOURCE.list_agent_project_assignments(agent.id)
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error
    peers = [
        candidate.id
        for candidate in agents
        if candidate.division == agent.division and candidate.id != agent.id
    ]
    direct_report_agent_ids = [
        candidate.id for candidate in agents if candidate.manager_id == agent.id
    ]
    available_services = list_available_services(agent)
    return LocalWorldView(
        agent_id=agent.id,
        name=agent.name,
        role=agent.role,
        division=agent.division,
        peers=peers,
        manager=agent.manager_id,
        manager_agent_id=agent.manager_id,
        peer_agent_ids=peers,
        direct_report_agent_ids=direct_report_agent_ids,
        soul=soul,
        active_projects=[assignment.project_id for assignment in assignments],
        permissions=agent.permissions,
        capabilities=agent.capabilities,
        policies=world_view_policy_labels(agent),
        available_services=[service.id for service in available_services],
        available_service_capabilities={
            service.id: service_capabilities_available_to_agent(agent, service)
            for service in available_services
        },
        available_service_credential_scopes={
            service.id: service.credential_scopes for service in available_services
        },
        available_connector_ids=list_available_connector_ids(available_services),
        available_skill_ids=list_available_skill_ids(agent),
    )


@app.get("/agent-lifecycle-requests", response_model=list[AgentLifecycleRequest])
def list_agent_lifecycle_requests(
    requested_by_id: str | None = None,
    status: str | None = None,
) -> list[AgentLifecycleRequest]:
    try:
        return AGENT_SOURCE.list_agent_lifecycle_requests(
            requested_by_id=requested_by_id,
            status=status,
        )
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error


@app.post("/agent-lifecycle-requests", response_model=AgentLifecycleRequest, status_code=201)
def create_agent_lifecycle_request(
    lifecycle_request: AgentLifecycleRequest,
    request: Request,
) -> AgentLifecycleRequest:
    try:
        return AGENT_SOURCE.create_agent_lifecycle_request(
            lifecycle_request,
            headers=source_request_headers(request),
        )
    except AgentSourceRequestError as error:
        raise_source_error(error)
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error


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
    try:
        return AGENT_SOURCE.decide_agent_lifecycle_request(
            request_id,
            decision,
            headers=source_request_headers(request),
        )
    except AgentSourceRequestError as error:
        raise_source_error(error)
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error
