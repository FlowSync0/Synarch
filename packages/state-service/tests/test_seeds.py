from synarch_state_service.repositories import StateRepositories
from synarch_state_service.seeds import (
    DEFAULT_AGENT_SOULS,
    DEFAULT_AGENTS,
    DEFAULT_DIVISIONS,
    DEFAULT_MODEL_DEFINITIONS,
    DEFAULT_MODEL_POLICIES,
    DEFAULT_MODEL_PROVIDERS,
    DEFAULT_SERVICES,
    DEFAULT_SKILLS,
    LOCAL_RUNTIME_MODEL_ID,
    LOCAL_RUNTIME_PROVIDER_ID,
    OPENROUTER_DEEPSEEK_V4_MODEL_ID,
    OPENROUTER_PROVIDER_ID,
    WORKER_DEFAULT_MODEL_POLICY_ID,
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
    assert summary.services_created == len(DEFAULT_SERVICES)
    assert summary.skills_created == len(DEFAULT_SKILLS)
    assert repositories.divisions.exists("division-direction")
    assert repositories.agents.exists("agent-direction")
    assert repositories.agents.exists("agent-finance")
    assert repositories.agent_souls.exists("soul-agent-direction-v1")
    assert repositories.model_providers.exists(LOCAL_RUNTIME_PROVIDER_ID)
    assert repositories.model_definitions.exists(LOCAL_RUNTIME_MODEL_ID)
    assert repositories.model_providers.exists(OPENROUTER_PROVIDER_ID)
    assert repositories.model_definitions.exists(OPENROUTER_DEEPSEEK_V4_MODEL_ID)
    assert repositories.model_policies.exists(WORKER_DEFAULT_MODEL_POLICY_ID)
    assert all(
        agent.model_policy_id == WORKER_DEFAULT_MODEL_POLICY_ID
        for agent in repositories.agents.list_records()
    )
    worker_policy = repositories.model_policies.get(WORKER_DEFAULT_MODEL_POLICY_ID)
    assert worker_policy is not None
    assert worker_policy.default_model_id == LOCAL_RUNTIME_MODEL_ID
    assert OPENROUTER_DEEPSEEK_V4_MODEL_ID in worker_policy.allowed_model_ids
    assert repositories.services.exists("connector-github")
    github = repositories.services.get("connector-github")
    assert github is not None
    assert github.metadata["manual_connection_url"] == (
        "https://github.com/settings/personal-access-tokens/new"
    )
    assert repositories.services.exists("connector-web-local")
    assert repositories.services.exists("connector-web-browser-local")
    assert repositories.services.exists("connector-firecrawl")
    firecrawl = repositories.services.get("connector-firecrawl")
    assert firecrawl is not None
    assert firecrawl.metadata["manual_connection_url"] == "https://www.firecrawl.dev"
    assert repositories.services.exists("connector-browserless")
    browserless = repositories.services.get("connector-browserless")
    assert browserless is not None
    assert browserless.credential_scopes == ["browserless:api_key"]
    assert browserless.metadata["web_provider"] == "browserless"
    assert browserless.metadata["manual_connection_url"] == "https://account.browserless.io"
    ops_agent = repositories.agents.get("agent-ops-sourcing")
    assert ops_agent is not None
    assert "web.extract" in ops_agent.permissions.allowed_tools
    assert "web.extract" in ops_agent.capabilities.tools
    supplier_search = repositories.skills.get("supplier_search")
    assert supplier_search is not None
    assert "web.extract" in supplier_search.required_tools
    assert repositories.skills.exists("implementation")


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
    assert first_summary.services_created == len(DEFAULT_SERVICES)
    assert first_summary.skills_created == len(DEFAULT_SKILLS)
    assert second_summary.divisions_created == 0
    assert second_summary.agents_created == 0
    assert second_summary.agent_souls_created == 0
    assert second_summary.model_providers_created == 0
    assert second_summary.model_definitions_created == 0
    assert second_summary.model_policies_created == 0
    assert second_summary.services_created == 0
    assert second_summary.skills_created == 0
    assert len(repositories.divisions.list_records()) == len(DEFAULT_DIVISIONS)
    assert len(repositories.agents.list_records()) == len(DEFAULT_AGENTS)
    assert len(repositories.agent_souls.list_records()) == len(DEFAULT_AGENT_SOULS)
    assert len(repositories.model_providers.list_records()) == len(DEFAULT_MODEL_PROVIDERS)
    assert len(repositories.model_definitions.list_records()) == len(DEFAULT_MODEL_DEFINITIONS)
    assert len(repositories.model_policies.list_records()) == len(DEFAULT_MODEL_POLICIES)
    assert len(repositories.services.list_records()) == len(DEFAULT_SERVICES)
    assert len(repositories.skills.list_records()) == len(DEFAULT_SKILLS)


def test_seed_repositories_backfills_default_agent_model_policy() -> None:
    repositories = StateRepositories.in_memory()
    legacy_agent = DEFAULT_AGENTS[0].model_copy(update={"model_policy_id": None})
    repositories.agents.create(legacy_agent.id, legacy_agent)

    summary = seed_repositories(repositories)

    assert summary.agents_created == len(DEFAULT_AGENTS) - 1
    updated_agent = repositories.agents.get(legacy_agent.id)
    assert updated_agent is not None
    assert updated_agent.model_policy_id == WORKER_DEFAULT_MODEL_POLICY_ID
