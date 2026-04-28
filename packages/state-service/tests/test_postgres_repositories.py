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
    assert isinstance(repositories.audit_logs, PostgresRecordRepository)
    assert repositories.projects.table_name == "projects"
    assert repositories.audit_logs.table_name == "audit_logs"
