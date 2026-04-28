from synarch_state_service.repositories import StateRepositories
from synarch_state_service.seeds import DEFAULT_AGENTS, DEFAULT_DIVISIONS, seed_repositories


def test_seed_repositories_creates_default_divisions_and_agents() -> None:
    repositories = StateRepositories.in_memory()

    summary = seed_repositories(repositories)

    assert summary.divisions_created == len(DEFAULT_DIVISIONS)
    assert summary.agents_created == len(DEFAULT_AGENTS)
    assert repositories.divisions.exists("division-direction")
    assert repositories.agents.exists("agent-direction")
    assert repositories.agents.exists("agent-finance")


def test_seed_repositories_is_idempotent() -> None:
    repositories = StateRepositories.in_memory()

    first_summary = seed_repositories(repositories)
    second_summary = seed_repositories(repositories)

    assert first_summary.divisions_created == len(DEFAULT_DIVISIONS)
    assert first_summary.agents_created == len(DEFAULT_AGENTS)
    assert second_summary.divisions_created == 0
    assert second_summary.agents_created == 0
    assert len(repositories.divisions.list_records()) == len(DEFAULT_DIVISIONS)
    assert len(repositories.agents.list_records()) == len(DEFAULT_AGENTS)
