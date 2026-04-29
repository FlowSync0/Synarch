from synarch_state_service.repositories import StateRepositories
from synarch_state_service.seeds import (
    DEFAULT_AGENT_SOULS,
    DEFAULT_AGENTS,
    DEFAULT_DIVISIONS,
    DEFAULT_MODEL_DEFINITIONS,
    DEFAULT_MODEL_POLICIES,
    DEFAULT_MODEL_PROVIDERS,
    LOCAL_RUNTIME_MODEL_ID,
    LOCAL_RUNTIME_PROVIDER_ID,
    seed_repositories,
)


def test_seed_repositories_creates_default_divisions_and_agents() -> None:
    repositories = StateRepositories.in_memory()

    summary = seed_repositories(repositories)

    assert summary.divisions_created == len(DEFAULT_DIVISIONS)
    assert summary.agents_created == len(DEFAULT_AGENTS)
    assert summary.agent_souls_created == len(DEFAULT_AGENT_SOULS)
    assert summary.model_providers_created == len(DEFAULT_MODEL_PROVIDERS)
    assert summary.model_definitions_created == len(DEFAULT_MODEL_DEFINITIONS)
    assert summary.model_policies_created == len(DEFAULT_MODEL_POLICIES)
    assert repositories.divisions.exists("division-direction")
    assert repositories.agents.exists("agent-direction")
    assert repositories.agents.exists("agent-finance")
    assert repositories.agent_souls.exists("soul-agent-direction-v1")
    assert repositories.model_providers.exists(LOCAL_RUNTIME_PROVIDER_ID)
    assert repositories.model_definitions.exists(LOCAL_RUNTIME_MODEL_ID)


def test_seed_repositories_is_idempotent() -> None:
    repositories = StateRepositories.in_memory()

    first_summary = seed_repositories(repositories)
    second_summary = seed_repositories(repositories)

    assert first_summary.divisions_created == len(DEFAULT_DIVISIONS)
    assert first_summary.agents_created == len(DEFAULT_AGENTS)
    assert first_summary.agent_souls_created == len(DEFAULT_AGENT_SOULS)
    assert first_summary.model_providers_created == len(DEFAULT_MODEL_PROVIDERS)
    assert first_summary.model_definitions_created == len(DEFAULT_MODEL_DEFINITIONS)
    assert first_summary.model_policies_created == len(DEFAULT_MODEL_POLICIES)
    assert second_summary.divisions_created == 0
    assert second_summary.agents_created == 0
    assert second_summary.agent_souls_created == 0
    assert second_summary.model_providers_created == 0
    assert second_summary.model_definitions_created == 0
    assert second_summary.model_policies_created == 0
    assert len(repositories.divisions.list_records()) == len(DEFAULT_DIVISIONS)
    assert len(repositories.agents.list_records()) == len(DEFAULT_AGENTS)
    assert len(repositories.agent_souls.list_records()) == len(DEFAULT_AGENT_SOULS)
    assert len(repositories.model_providers.list_records()) == len(DEFAULT_MODEL_PROVIDERS)
    assert len(repositories.model_definitions.list_records()) == len(DEFAULT_MODEL_DEFINITIONS)
    assert len(repositories.model_policies.list_records()) == len(DEFAULT_MODEL_POLICIES)
