from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

from synarch_state_service.postgres_repositories import normalize_postgres_dsn

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def migration_files(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[Path]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migration directory does not exist: {migrations_dir}")
    return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())


def run_migrations(
    database_url: str,
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(normalize_postgres_dsn(database_url), autocommit=True) as connection:
        for migration_file in migration_files(migrations_dir):
            connection.execute(migration_file.read_text(encoding="utf-8"))
            applied.append(migration_file.name)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Synarch state-service SQL migrations.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help="Directory containing ordered .sql migration files.",
    )
    args = parser.parse_args()

    if args.database_url is None:
        raise SystemExit("DATABASE_URL or --database-url is required.")

    applied = run_migrations(args.database_url, args.migrations_dir)
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("No migrations found.")


if __name__ == "__main__":
    main()
