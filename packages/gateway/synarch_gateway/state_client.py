from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from synarch_models import (
    AgentProjectAssignment,
    AgentResult,
    AuditLogRecord,
    CostRecord,
    EventRecord,
    ProjectComplexityAssessment,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectWorkspace,
    TaskRecord,
)


class StateServiceUnavailable(Exception):
    pass


class StateServiceRequestError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class StateClient(Protocol):
    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord: ...

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord: ...

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace: ...

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment: ...

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord: ...

    def list_events(
        self,
        *,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventRecord]: ...

    def assess_project_complexity(
        self,
        project_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectComplexityAssessment: ...

    def apply_project_split(
        self,
        split_request_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectSplitApplication: ...

    def get_project(self, project_id: str) -> ProjectRecord: ...

    def list_tasks(self, *, project_id: str | None = None) -> list[TaskRecord]: ...

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord: ...

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord: ...

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord: ...

    def list_cost_records(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[CostRecord]: ...

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[AuditLogRecord]: ...


@dataclass(frozen=True)
class HttpStateClient:
    base_url: str
    timeout_seconds: float = 5.0

    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        response = self._post("/projects", project.model_dump(mode="json"), headers)
        return ProjectRecord.model_validate(response.json())

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self._post("/tasks", task.model_dump(mode="json"), headers)
        return TaskRecord.model_validate(response.json())

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace:
        response = self._post("/project-workspaces", workspace.model_dump(mode="json"), headers)
        return ProjectWorkspace.model_validate(response.json())

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment:
        response = self._post(
            "/agent-project-assignments",
            assignment.model_dump(mode="json"),
            headers,
        )
        return AgentProjectAssignment.model_validate(response.json())

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        response = self._post("/events", event.model_dump(mode="json"), headers)
        return EventRecord.model_validate(response.json())

    def list_events(
        self,
        *,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventRecord]:
        response = self._get(
            "/events",
            params=compact_params(event_type=event_type, trace_id=trace_id),
        )
        return [EventRecord.model_validate(event) for event in response.json()]

    def assess_project_complexity(
        self,
        project_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectComplexityAssessment:
        response = self._post(f"/projects/{project_id}/complexity-assessments", None, headers)
        return ProjectComplexityAssessment.model_validate(response.json())

    def apply_project_split(
        self,
        split_request_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectSplitApplication:
        response = self._post(f"/project-split-requests/{split_request_id}/apply", None, headers)
        return ProjectSplitApplication.model_validate(response.json())

    def get_project(self, project_id: str) -> ProjectRecord:
        response = self._get(f"/projects/{project_id}")
        return ProjectRecord.model_validate(response.json())

    def list_tasks(self, *, project_id: str | None = None) -> list[TaskRecord]:
        response = self._get("/tasks", params=compact_params(project_id=project_id))
        return [TaskRecord.model_validate(task) for task in response.json()]

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self._post(f"/tasks/{task_id}/start", None, headers)
        return TaskRecord.model_validate(response.json())

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self._post(
            f"/tasks/{task_id}/results",
            result.model_dump(mode="json"),
            headers,
        )
        return TaskRecord.model_validate(response.json())

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord:
        response = self._post("/cost-records", cost.model_dump(mode="json"), headers)
        return CostRecord.model_validate(response.json())

    def list_cost_records(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[CostRecord]:
        response = self._get(
            "/cost-records",
            params=compact_params(
                project_id=project_id,
                agent_id=agent_id,
                provider_id=provider_id,
                model_id=model_id,
                trace_id=trace_id,
            ),
        )
        return [CostRecord.model_validate(cost) for cost in response.json()]

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[AuditLogRecord]:
        response = self._get(
            "/audit-logs",
            params=compact_params(
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
                trace_id=trace_id,
            ),
        )
        return [AuditLogRecord.model_validate(audit) for audit in response.json()]

    def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}{path}",
                params=params,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        return response

    def _post(
        self,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}{path}",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        if 400 <= response.status_code < 500:
            raise StateServiceRequestError(response.status_code, response_detail(response))

        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        return response


def response_detail(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict):
        return body.get("detail", body)
    return body


def compact_params(**values: str | None) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}
