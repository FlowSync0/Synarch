import os

import pytest

from synarch_models import ProjectRecord
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
