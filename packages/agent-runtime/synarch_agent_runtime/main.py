from fastapi import FastAPI

from synarch_models import (
    AgentResult,
    AgentTaskRequest,
    EventRecord,
    EventType,
    HealthResponse,
    TaskStatus,
)

app = FastAPI(title="Synarch Agent Runtime", version="0.1.0")


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="agent-runtime")


@app.post("/tasks/run", response_model=AgentResult)
def run_task(request: AgentTaskRequest) -> AgentResult:
    status = task_status_for_stub(request)
    event = EventRecord(
        type=EventType.agent_reported,
        source_agent_id=request.world_view.agent_id,
        target=request.task.project_id,
        payload={
            "task_id": request.task.id,
            "division": request.world_view.division,
            "mode": "stub-runtime",
        },
    )
    return AgentResult(
        agent_id=request.world_view.agent_id,
        task_id=request.task.id,
        status=status,
        actions_taken=["Loaded LocalWorldView", "Prepared execution plan"],
        events_emitted=[event],
        summary=summary_for_status(status),
    )


def task_status_for_stub(request: AgentTaskRequest) -> TaskStatus:
    if (
        request.world_view.agent_id == "agent-direction"
        and request.task.title == "Clarify success criteria"
    ):
        return TaskStatus.completed
    return TaskStatus.needs_review


def summary_for_status(status: TaskStatus) -> str:
    if status == TaskStatus.completed:
        return "Runtime stub completed the deterministic preparation step."
    return "Runtime stub prepared the task for a real agent executor."
