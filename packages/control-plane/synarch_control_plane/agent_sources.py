from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from synarch_models import AgentDefinition, ModelPolicy, ServiceDefinition

from .seed import AGENTS


class AgentSourceUnavailable(Exception):
    pass


class AgentSource(Protocol):
    def list_agents(self) -> list[AgentDefinition]: ...

    def get_agent(self, agent_id: str) -> AgentDefinition | None: ...

    def list_services(self) -> list[ServiceDefinition]: ...

    def get_model_policy(self, policy_id: str) -> ModelPolicy | None: ...


@dataclass(frozen=True)
class SeedAgentSource:
    agents: tuple[AgentDefinition, ...] = tuple(AGENTS)

    def list_agents(self) -> list[AgentDefinition]:
        return list(self.agents)

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        return next((agent for agent in self.agents if agent.id == agent_id), None)

    def list_services(self) -> list[ServiceDefinition]:
        return []

    def get_model_policy(self, policy_id: str) -> ModelPolicy | None:
        return None


@dataclass(frozen=True)
class StateServiceAgentSource:
    base_url: str
    timeout_seconds: float = 5.0

    def list_agents(self) -> list[AgentDefinition]:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}/agents",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        return [AgentDefinition.model_validate(agent) for agent in response.json()]

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        response = self._get_optional(f"/agents/{agent_id}")
        if response is None:
            return None
        return AgentDefinition.model_validate(response.json())

    def list_services(self) -> list[ServiceDefinition]:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}/services",
                params={"enabled": True},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        return [ServiceDefinition.model_validate(service) for service in response.json()]

    def get_model_policy(self, policy_id: str) -> ModelPolicy | None:
        response = self._get_optional(f"/model-policies/{policy_id}")
        if response is None:
            return None
        return ModelPolicy.model_validate(response.json())

    def _get_optional(self, path: str) -> httpx.Response | None:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}{path}",
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        return response
