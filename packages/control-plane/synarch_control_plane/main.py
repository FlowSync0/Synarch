from fastapi import FastAPI, HTTPException

from synarch_models import AgentDefinition, HealthResponse, LocalWorldView

from .seed import AGENTS

app = FastAPI(title="Synarch Control Plane", version="0.1.0")


def get_agent_or_404(agent_id: str) -> AgentDefinition:
    for agent in AGENTS:
        if agent.id == agent_id:
            return agent
    raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="control-plane")


@app.get("/agents", response_model=list[AgentDefinition])
def list_agents() -> list[AgentDefinition]:
    return AGENTS


@app.get("/agents/{agent_id}", response_model=AgentDefinition)
def read_agent(agent_id: str) -> AgentDefinition:
    return get_agent_or_404(agent_id)


@app.get("/agents/{agent_id}/world-view", response_model=LocalWorldView)
def read_world_view(agent_id: str) -> LocalWorldView:
    agent = get_agent_or_404(agent_id)
    peers = [
        candidate.id
        for candidate in AGENTS
        if candidate.division == agent.division and candidate.id != agent.id
    ]
    return LocalWorldView(
        agent_id=agent.id,
        role=agent.role,
        division=agent.division,
        peers=peers,
        manager=agent.manager_id,
        permissions=agent.permissions,
        capabilities=agent.capabilities,
        policies=[
            "least_privilege_tools",
            "event_log_required",
            "memory_budget_required",
        ],
    )
