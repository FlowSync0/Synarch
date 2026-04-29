import os
from typing import NoReturn

from fastapi import FastAPI, HTTPException, Request

from synarch_models import (
    AgentDefinition,
    AgentLifecycleDecision,
    AgentLifecycleRequest,
    HealthResponse,
    LocalWorldView,
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
        header: request.headers[header]
        for header in forwarded_headers
        if header in request.headers
    }


def raise_source_error(error: AgentSourceRequestError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


def list_available_service_ids(agent: AgentDefinition) -> list[str]:
    try:
        services = AGENT_SOURCE.list_services()
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error

    allowed_tools = set(agent.permissions.allowed_tools)
    return [
        service.id
        for service in services
        if service.enabled
        and (
            service.owner_agent_id in {None, agent.id}
            or bool(allowed_tools.intersection(service.capabilities))
        )
    ]


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
    except AgentSourceUnavailable as error:
        raise HTTPException(status_code=502, detail="Agent source unavailable") from error
    peers = [
        candidate.id
        for candidate in agents
        if candidate.division == agent.division and candidate.id != agent.id
    ]
    return LocalWorldView(
        agent_id=agent.id,
        role=agent.role,
        division=agent.division,
        peers=peers,
        manager=agent.manager_id,
        soul=soul,
        permissions=agent.permissions,
        capabilities=agent.capabilities,
        policies=world_view_policy_labels(agent),
        available_services=list_available_service_ids(agent),
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
