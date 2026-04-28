from synarch_models import ProjectRecord
from synarch_state_service.repositories import InMemoryRecordRepository, StateRepositories


def test_in_memory_repository_stores_records_by_id() -> None:
    repository = InMemoryRecordRepository[str]()

    repository.create("record-1", "alpha")
    repository.create("record-2", "beta")
    repository.update("record-2", "gamma")

    assert repository.exists("record-1")
    assert repository.get("record-1") == "alpha"
    assert repository.get("record-2") == "gamma"
    assert repository.get("missing") is None
    assert repository.list_records() == ["alpha", "gamma"]


def test_state_repositories_factory_returns_isolated_stores() -> None:
    first = StateRepositories.in_memory()
    second = StateRepositories.in_memory()
    project = ProjectRecord(
        title="Repository slice",
        goal="Prove state repositories are isolated",
        owner_agent_id="agent-dev",
    )

    first.projects.create(project.id, project)

    assert first.projects.exists(project.id)
    assert not second.projects.exists(project.id)
