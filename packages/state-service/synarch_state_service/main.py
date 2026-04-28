from fastapi import FastAPI, HTTPException

from synarch_models import HealthResponse, ProjectRecord, TaskRecord

app = FastAPI(title="Synarch State Service", version="0.1.0")

PROJECTS: dict[str, ProjectRecord] = {}
TASKS: dict[str, TaskRecord] = {}


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="state-service")


@app.post("/projects", response_model=ProjectRecord, status_code=201)
def create_project(project: ProjectRecord) -> ProjectRecord:
    PROJECTS[project.id] = project
    return project


@app.get("/projects", response_model=list[ProjectRecord])
def list_projects() -> list[ProjectRecord]:
    return list(PROJECTS.values())


@app.get("/projects/{project_id}", response_model=ProjectRecord)
def read_project(project_id: str) -> ProjectRecord:
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail=f"Unknown project: {project_id}")
    return PROJECTS[project_id]


@app.post("/tasks", response_model=TaskRecord, status_code=201)
def create_task(task: TaskRecord) -> TaskRecord:
    if task.project_id not in PROJECTS:
        raise HTTPException(status_code=400, detail=f"Unknown project: {task.project_id}")
    TASKS[task.id] = task
    return task


@app.get("/tasks", response_model=list[TaskRecord])
def list_tasks(project_id: str | None = None) -> list[TaskRecord]:
    tasks = list(TASKS.values())
    if project_id is None:
        return tasks
    return [task for task in tasks if task.project_id == project_id]
