from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from synarch_models import (
    AgentProjectAssignment,
    AgentResult,
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

    def list_tasks(self) -> list[TaskRecord]: ...

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

    def list_tasks(self) -> list[TaskRecord]:
        response = self._get("/tasks")
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

    def _get(self, path: str) -> httpx.Response:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}{path}",
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
