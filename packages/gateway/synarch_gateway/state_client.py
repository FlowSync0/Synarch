from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from synarch_models import EventRecord, ProjectRecord, TaskRecord


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

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord: ...


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

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        response = self._post("/events", event.model_dump(mode="json"), headers)
        return EventRecord.model_validate(response.json())

    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
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
