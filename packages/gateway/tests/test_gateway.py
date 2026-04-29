from fastapi.testclient import TestClient

from synarch_gateway.main import app, get_state_client, get_task_runner
from synarch_gateway.state_client import StateServiceUnavailable
from synarch_gateway.task_runner import TaskRunner
from synarch_models import (
    AgentResult,
    AgentTaskRequest,
    EventRecord,
    LocalWorldView,
    MemoryContext,
    ProjectRecord,
    TaskRecord,
    TaskStatus,
)


class FakeStateClient:
    def __init__(self) -> None:
        self.projects: list[ProjectRecord] = []
        self.tasks: list[TaskRecord] = []
        self.events: list[EventRecord] = []
        self.headers: list[dict[str, str]] = []

    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        self.headers.append(headers)
        self.projects.append(project)
        return project

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        self.tasks.append(task)
        return task

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        self.headers.append(headers)
        self.events.append(event)
        return event

    def list_tasks(self) -> list[TaskRecord]:
        return self.tasks

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        started_task = task.model_copy(update={"status": TaskStatus.running})
        self.tasks[self.tasks.index(task)] = started_task
        return started_task

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        recorded_task = task.model_copy(
            update={
                "status": result.status,
                "result": {"summary": result.summary},
            }
        )
        self.tasks[self.tasks.index(task)] = recorded_task
        return recorded_task


class FailingStateClient(FakeStateClient):
    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        raise StateServiceUnavailable("state-service offline")


class FakeControlPlaneClient:
    def get_world_view(self, agent_id: str) -> LocalWorldView:
        return LocalWorldView(agent_id=agent_id, role="Code and infra", division="dev")


class FakeMemoryClient:
    def assemble_context(self, context: MemoryContext) -> MemoryContext:
        return context.model_copy(update={"summary": "Fake context assembled."})


class FakeAgentRuntimeClient:
    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.needs_review,
            actions_taken=["Loaded LocalWorldView", "Prepared execution plan"],
            summary="Runtime stub prepared the task for review.",
        )


def test_goal_routes_to_dev_agent() -> None:
    response = TestClient(app).post(
        "/goals",
        json={"goal": "Corriger un bug API sur le gateway", "priority": "high"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "agent-dev" in payload["target_agents"]
    assert payload["project_intent"]["priority"] == "high"


def test_goal_submit_persists_project_tasks_and_events() -> None:
    state_client = FakeStateClient()
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/goals/submit",
            json={
                "goal": "Traiter une facture fournisseur avec TVA",
                "priority": "high",
                "requester": "hugo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["project"]["goal"] == "Traiter une facture fournisseur avec TVA"
    assert payload["project"]["owner_agent_id"] == "agent-direction"
    assert [task["assigned_agent_id"] for task in payload["tasks"]] == [
        "agent-direction",
        "agent-finance",
    ]
    assert payload["tasks"][1]["depends_on"] == [payload["tasks"][0]["id"]]
    assert [event["type"] for event in payload["events"]] == [
        "goal.received",
        "routing.decided",
        "project.created",
        "task.created",
        "task.created",
    ]
    assert {event["trace_id"] for event in payload["events"]} == {payload["trace_id"]}
    assert state_client.projects[0].id == payload["project"]["id"]
    assert state_client.headers[0]["x-synarch-actor-id"] == "hugo"
    assert state_client.headers[0]["x-synarch-trace-id"] == payload["trace_id"]


def test_goal_submit_returns_bad_gateway_when_state_service_is_unavailable() -> None:
    app.dependency_overrides[get_state_client] = FailingStateClient

    try:
        response = TestClient(app).post(
            "/goals/submit",
            json={"goal": "Corriger un bug API", "priority": "high"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "State service unavailable"


def test_run_next_task_executes_first_ready_task() -> None:
    state_client = FakeStateClient()
    state_client.tasks.append(
        TaskRecord(
            project_id="project_demo",
            title="Ready task",
            assigned_agent_id="agent-dev",
        )
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_gateway_runner_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trace_gateway_runner_test"
    assert payload["task"]["status"] == "needs_review"
    assert payload["task"]["result"]["summary"] == "Runtime stub prepared the task for review."
    assert payload["world_view"]["agent_id"] == "agent-dev"
    assert payload["memory_context"]["summary"] == "Fake context assembled."
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-task-runner"


def test_run_next_task_returns_404_when_no_task_is_ready() -> None:
    runner = TaskRunner(
        state=FakeStateClient(),
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post("/tasks/run-next")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "No queued task is ready to run"
