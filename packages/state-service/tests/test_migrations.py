from pathlib import Path

import pytest

from synarch_state_service.migrations import (
    DEFAULT_MIGRATIONS_DIR,
    migration_files,
)


def test_default_migration_directory_contains_initial_schema() -> None:
    assert (DEFAULT_MIGRATIONS_DIR / "0001_initial.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0006_memory_item_status.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0007_services_skills_access.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0008_task_leases.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0009_task_retry_review.sql").exists()
    assert (
        DEFAULT_MIGRATIONS_DIR / "0010_ops_sourcing_web_fetch_permission.sql"
    ).exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0011_supplier_web_fetch_capability.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0012_service_credential_scopes.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0013_task_required_tools.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0014_credential_access_requests.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0015_credential_grants.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0016_task_required_tool_scopes.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0017_connector_jobs.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0018_connector_job_next_run_at.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0019_lifecycle_proposed_soul.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0020_memory_item_metadata.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0021_connector_job_create_tool.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0022_connector_job_stop_tool.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0023_connector_job_list_tool.sql").exists()
    assert (DEFAULT_MIGRATIONS_DIR / "0024_web_extract_provider_registry.sql").exists()


def test_migration_files_are_sorted(tmp_path: Path) -> None:
    second = tmp_path / "0002_second.sql"
    first = tmp_path / "0001_first.sql"
    ignored = tmp_path / "notes.txt"
    second.write_text("SELECT 2;", encoding="utf-8")
    first.write_text("SELECT 1;", encoding="utf-8")
    ignored.write_text("ignore me", encoding="utf-8")

    assert migration_files(tmp_path) == [first, second]


def test_missing_migration_directory_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migration_files(tmp_path / "missing")
