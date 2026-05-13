from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from synarch_models import (
    AgentDefinition,
    AgentLifecycleDecision,
    AgentLifecycleRequest,
    AgentModelPolicyUpdate,
    AgentProjectAssignment,
    AgentSoul,
    ModelPolicy,
    ServiceDefinition,
    SkillDefinition,
)

from .seed import AGENT_SOULS, AGENTS, MODEL_POLICIES


class AgentSourceUnavailable(Exception):
    pass


class AgentSourceRequestError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class AgentSource(Protocol):
    def list_agents(self) -> list[AgentDefinition]: ...

    def get_agent(self, agent_id: str) -> AgentDefinition | None: ...

    def get_agent_soul(self, agent_id: str) -> AgentSoul | None: ...

    def list_agent_project_assignments(self, agent_id: str) -> list[AgentProjectAssignment]: ...

    def list_services(self) -> list[ServiceDefinition]: ...

    def list_skills(self) -> list[SkillDefinition]: ...

    def get_model_policy(self, policy_id: str) -> ModelPolicy | None: ...

    def update_agent_model_policy(
        self,
        agent_id: str,
        update: AgentModelPolicyUpdate,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentDefinition: ...

    def list_agent_lifecycle_requests(
        self,
        *,
        requested_by_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentLifecycleRequest]: ...

    def create_agent_lifecycle_request(
        self,
        lifecycle_request: AgentLifecycleRequest,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentLifecycleRequest: ...

    def decide_agent_lifecycle_request(
        self,
        request_id: str,
        decision: AgentLifecycleDecision,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentLifecycleDecision: ...


@dataclass(frozen=True)
class SeedAgentSource:
    agents: tuple[AgentDefinition, ...] = tuple(AGENTS)
    model_policies: tuple[ModelPolicy, ...] = tuple(MODEL_POLICIES)

    def list_agents(self) -> list[AgentDefinition]:
        return list(self.agents)

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        return next((agent for agent in self.agents if agent.id == agent_id), None)

    def get_agent_soul(self, agent_id: str) -> AgentSoul | None:
        return next(
            (soul for soul in AGENT_SOULS if soul.agent_id == agent_id and soul.active), None
        )

    def list_agent_project_assignments(self, agent_id: str) -> list[AgentProjectAssignment]:
        return []

    def list_services(self) -> list[ServiceDefinition]:
        return []

    def list_skills(self) -> list[SkillDefinition]:
        return []

    def get_model_policy(self, policy_id: str) -> ModelPolicy | None:
        return next(
            (policy for policy in self.model_policies if policy.id == policy_id),
            None,
        )

    def update_agent_model_policy(
        self,
        agent_id: str,
        update: AgentModelPolicyUpdate,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentDefinition:
        raise AgentSourceUnavailable("State service is required for model policy updates")

    def list_agent_lifecycle_requests(
        self,
        *,
        requested_by_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentLifecycleRequest]:
        return []

    def create_agent_lifecycle_request(
        self,
        lifecycle_request: AgentLifecycleRequest,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentLifecycleRequest:
        raise AgentSourceUnavailable("State service is required for lifecycle requests")

    def decide_agent_lifecycle_request(
        self,
        request_id: str,
        decision: AgentLifecycleDecision,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentLifecycleDecision:
        raise AgentSourceUnavailable("State service is required for lifecycle decisions")


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

    def get_agent_soul(self, agent_id: str) -> AgentSoul | None:
        response = self._get_optional(f"/agents/{agent_id}/soul")
        if response is None:
            return None
        return AgentSoul.model_validate(response.json())

    def list_agent_project_assignments(self, agent_id: str) -> list[AgentProjectAssignment]:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}/agent-project-assignments",
                params={"agent_id": agent_id, "active": True},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        return [AgentProjectAssignment.model_validate(assignment) for assignment in response.json()]

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

    def list_skills(self) -> list[SkillDefinition]:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}/skills",
                params={"enabled": True},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        return [SkillDefinition.model_validate(skill) for skill in response.json()]

    def get_model_policy(self, policy_id: str) -> ModelPolicy | None:
        response = self._get_optional(f"/model-policies/{policy_id}")
        if response is None:
            return None
        return ModelPolicy.model_validate(response.json())

    def update_agent_model_policy(
        self,
        agent_id: str,
        update: AgentModelPolicyUpdate,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentDefinition:
        try:
            response = httpx.patch(
                f"{self.base_url.rstrip('/')}/agents/{agent_id}/model-policy",
                json=update.model_dump(mode="json"),
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        self._raise_for_write_status(response)
        return AgentDefinition.model_validate(response.json())

    def list_agent_lifecycle_requests(
        self,
        *,
        requested_by_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentLifecycleRequest]:
        params = {
            name: value
            for name, value in {
                "requested_by_id": requested_by_id,
                "status": status,
            }.items()
            if value is not None
        }
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}/agent-lifecycle-requests",
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        return [
            AgentLifecycleRequest.model_validate(lifecycle_request)
            for lifecycle_request in response.json()
        ]

    def create_agent_lifecycle_request(
        self,
        lifecycle_request: AgentLifecycleRequest,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentLifecycleRequest:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/agent-lifecycle-requests",
                json=lifecycle_request.model_dump(mode="json"),
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        self._raise_for_write_status(response)
        return AgentLifecycleRequest.model_validate(response.json())

    def decide_agent_lifecycle_request(
        self,
        request_id: str,
        decision: AgentLifecycleDecision,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentLifecycleDecision:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/agent-lifecycle-requests/{request_id}/decisions",
                json=decision.model_dump(mode="json"),
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
        self._raise_for_write_status(response)
        return AgentLifecycleDecision.model_validate(response.json())

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

    @staticmethod
    def _raise_for_write_status(response: httpx.Response) -> None:
        if 400 <= response.status_code < 500:
            try:
                body = response.json()
            except ValueError:
                detail: Any = response.text
            else:
                detail = body.get("detail", body) if isinstance(body, dict) else body
            raise AgentSourceRequestError(response.status_code, detail)
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AgentSourceUnavailable(str(error)) from error
