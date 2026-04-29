from psycopg.types.json import Jsonb

from synarch_models import AgentDefinition, AgentLifecycleRequest
from synarch_state_service.postgres_repositories import (
    PostgresRecordRepository,
    normalize_postgres_dsn,
)
from synarch_state_service.repositories import StateRepositories


def test_normalize_postgres_dsn_accepts_sqlalchemy_psycopg_scheme() -> None:
    assert (
        normalize_postgres_dsn("postgresql+psycopg://synarch:synarch@postgres:5432/synarch")
        == "postgresql://synarch:synarch@postgres:5432/synarch"
    )


def test_postgres_repository_factory_builds_all_state_stores() -> None:
    repositories = StateRepositories.postgres("postgresql://synarch:synarch@localhost:5432/synarch")

    assert isinstance(repositories.projects, PostgresRecordRepository)
    assert isinstance(repositories.project_workspaces, PostgresRecordRepository)
    assert isinstance(repositories.agent_project_assignments, PostgresRecordRepository)
    assert isinstance(repositories.project_complexity_reports, PostgresRecordRepository)
    assert isinstance(repositories.project_split_requests, PostgresRecordRepository)
    assert isinstance(repositories.agent_souls, PostgresRecordRepository)
    assert isinstance(repositories.audit_logs, PostgresRecordRepository)
    assert repositories.projects.table_name == "projects"
    assert repositories.project_workspaces.table_name == "project_workspaces"
    assert repositories.agent_project_assignments.table_name == "agent_project_assignments"
    assert repositories.project_complexity_reports.table_name == "project_complexity_reports"
    assert repositories.project_split_requests.table_name == "project_split_requests"
    assert repositories.agent_souls.table_name == "agent_souls"
    assert repositories.audit_logs.table_name == "audit_logs"


def test_postgres_repository_adapts_jsonb_with_json_serializable_values() -> None:
    proposed_agent = AgentDefinition(
        id="agent-seed-review",
        name="IA Seed Review",
        role="Review proposed seed data",
        division="admin-knowledge",
        manager_id="agent-direction",
    )
    lifecycle_request = AgentLifecycleRequest(
        action="create_agent",
        requested_by_type="agent",
        requested_by_id="agent-direction",
        reason="Need a reviewer for seed data changes.",
        proposed_agent=proposed_agent,
    )
    repository = PostgresRecordRepository(
        "postgresql://synarch:synarch@localhost:5432/synarch",
        "agent_lifecycle_requests",
        AgentLifecycleRequest,
        ("proposed_agent",),
        frozenset({"proposed_agent"}),
    )
    python_data = lifecycle_request.model_dump(mode="python")
    json_data = lifecycle_request.model_dump(mode="json")

    adapted = repository._adapt_value(
        "proposed_agent",
        python_data["proposed_agent"],
        json_data["proposed_agent"],
    )

    assert isinstance(adapted, Jsonb)
    assert isinstance(adapted.obj["created_at"], str)
