import os

import pytest

from synarch_models import ProjectRecord, TaskRecord, TaskStatus
from synarch_state_service.repositories import StateRepositories

pytestmark = pytest.mark.integration


def test_postgres_project_survives_repository_recreation() -> None:
    database_url = os.getenv("SYNARCH_POSTGRES_TEST_URL")
    if database_url is None:
        pytest.skip("Set SYNARCH_POSTGRES_TEST_URL to run PostgreSQL persistence tests.")

    project = ProjectRecord(
        title="Postgres restart survival",
        goal="Read the same project through a fresh repository instance",
        owner_agent_id="agent-direction",
    )
    first_repositories = StateRepositories.postgres(database_url)
    first_repositories.projects.create(project.id, project)

    second_repositories = StateRepositories.postgres(database_url)
    loaded_project = second_repositories.projects.get(project.id)

    assert loaded_project is not None
    assert loaded_project.id == project.id
    assert loaded_project.title == project.title


def test_postgres_task_result_survives_repository_recreation() -> None:
    database_url = os.getenv("SYNARCH_POSTGRES_TEST_URL")
    if database_url is None:
        pytest.skip("Set SYNARCH_POSTGRES_TEST_URL to run PostgreSQL persistence tests.")

    project = ProjectRecord(
        title="Postgres task result survival",
        goal="Read an updated task result through a fresh repository instance",
        owner_agent_id="agent-direction",
    )
    task = TaskRecord(
        project_id=project.id,
        title="Persist task result",
        assigned_agent_id="agent-direction",
    )
    first_repositories = StateRepositories.postgres(database_url)
    first_repositories.projects.create(project.id, project)
    first_repositories.tasks.create(task.id, task)
    first_repositories.tasks.update(
        task.id,
        task.model_copy(
            update={
                "status": TaskStatus.completed,
                "result": {"summary": "Task result survived repository recreation."},
            }
        ),
    )

    second_repositories = StateRepositories.postgres(database_url)
    loaded_task = second_repositories.tasks.get(task.id)

    assert loaded_task is not None
    assert loaded_task.status == TaskStatus.completed
    assert loaded_task.result == {"summary": "Task result survived repository recreation."}
