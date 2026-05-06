from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import rows, sql
from psycopg.types.json import Jsonb

from synarch_models import (
    AgentDefinition,
    AgentLifecycleRequest,
    AgentProjectAssignment,
    AgentSoul,
    AuditLogRecord,
    CostRecord,
    DivisionRecord,
    EventRecord,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ProjectComplexityReport,
    ProjectRecord,
    ProjectSplitRequest,
    ProjectWorkspace,
    ServiceDefinition,
    SkillDefinition,
    TaskRecord,
)
from synarch_models.contracts import SynarchModel
from synarch_state_service.repositories import StateRepositories


def normalize_postgres_dsn(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


@dataclass(frozen=True)
class PostgresRecordRepository[RecordT: SynarchModel]:
    database_url: str
    table_name: str
    model: type[RecordT]
    columns: tuple[str, ...]
    jsonb_columns: frozenset[str] = frozenset()

    def create(self, record_id: str, record: RecordT) -> RecordT:
        python_data = record.model_dump(mode="python")
        json_data = record.model_dump(mode="json")
        values = [
            self._adapt_value(
                column,
                python_data.get(column),
                json_data.get(column),
            )
            for column in self.columns
        ]
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            self._column_list(self.columns),
            sql.SQL(", ").join([sql.Placeholder() for _ in self.columns]),
        )
        with psycopg.connect(normalize_postgres_dsn(self.database_url)) as connection:
            connection.execute(query, values)
        return record

    def update(self, record_id: str, record: RecordT) -> RecordT:
        update_columns = tuple(column for column in self.columns if column != "id")
        python_data = record.model_dump(mode="python")
        json_data = record.model_dump(mode="json")
        values = [
            self._adapt_value(
                column,
                python_data.get(column),
                json_data.get(column),
            )
            for column in update_columns
        ]
        values.append(record_id)
        query = sql.SQL("UPDATE {} SET {} WHERE {} = {}").format(
            sql.Identifier(self.table_name),
            self._assignments(update_columns),
            sql.Identifier("id"),
            sql.Placeholder(),
        )
        with psycopg.connect(normalize_postgres_dsn(self.database_url)) as connection:
            cursor = connection.execute(query, values)
            if cursor.rowcount == 0:
                raise KeyError(record_id)
        return record

    def update_if(
        self,
        record_id: str,
        record: RecordT,
        expected: dict[str, object],
    ) -> RecordT | None:
        update_columns = tuple(column for column in self.columns if column != "id")
        python_data = record.model_dump(mode="python")
        json_data = record.model_dump(mode="json")
        values = [
            self._adapt_value(
                column,
                python_data.get(column),
                json_data.get(column),
            )
            for column in update_columns
        ]
        expected_columns = tuple(expected)
        values.append(record_id)
        values.extend(
            self._adapt_value(column, expected[column], expected[column])
            for column in expected_columns
        )
        query = sql.SQL("UPDATE {} SET {} WHERE {}").format(
            sql.Identifier(self.table_name),
            self._assignments(update_columns),
            self._conditions(("id", *expected_columns)),
        )
        with psycopg.connect(normalize_postgres_dsn(self.database_url)) as connection:
            cursor = connection.execute(query, values)
            if cursor.rowcount == 0:
                return None
        return record

    def exists(self, record_id: str) -> bool:
        query = sql.SQL("SELECT 1 FROM {} WHERE {} = {} LIMIT 1").format(
            sql.Identifier(self.table_name),
            sql.Identifier("id"),
            sql.Placeholder(),
        )
        with psycopg.connect(normalize_postgres_dsn(self.database_url)) as connection:
            result = connection.execute(query, [record_id]).fetchone()
        return result is not None

    def get(self, record_id: str) -> RecordT | None:
        query = sql.SQL("SELECT {} FROM {} WHERE {} = {}").format(
            self._column_list(self.columns),
            sql.Identifier(self.table_name),
            sql.Identifier("id"),
            sql.Placeholder(),
        )
        with psycopg.connect(
            normalize_postgres_dsn(self.database_url),
            row_factory=rows.dict_row,
        ) as connection:
            row = connection.execute(query, [record_id]).fetchone()
        if row is None:
            return None
        return self.model.model_validate(row)

    def list_records(self) -> list[RecordT]:
        query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
            self._column_list(self.columns),
            sql.Identifier(self.table_name),
            sql.Identifier("id"),
        )
        with psycopg.connect(
            normalize_postgres_dsn(self.database_url),
            row_factory=rows.dict_row,
        ) as connection:
            records = connection.execute(query).fetchall()
        return [self.model.model_validate(record) for record in records]

    def _adapt_value(self, column: str, python_value: Any, json_value: Any) -> Any:
        if column in self.jsonb_columns and python_value is not None:
            return Jsonb(json_value)
        return python_value

    @staticmethod
    def _column_list(columns: tuple[str, ...]) -> sql.Composed:
        return sql.SQL(", ").join([sql.Identifier(column) for column in columns])

    @staticmethod
    def _assignments(columns: tuple[str, ...]) -> sql.Composed:
        return sql.SQL(", ").join(
            [
                sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder())
                for column in columns
            ]
        )

    @staticmethod
    def _conditions(columns: tuple[str, ...]) -> sql.Composed:
        return sql.SQL(" AND ").join(
            [
                sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder())
                for column in columns
            ]
        )


def build_postgres_repositories(database_url: str) -> StateRepositories:
    return StateRepositories(
        divisions=PostgresRecordRepository(
            database_url,
            "divisions",
            DivisionRecord,
            ("id", "name", "purpose", "manager_agent_id", "created_at"),
        ),
        agents=PostgresRecordRepository(
            database_url,
            "agents",
            AgentDefinition,
            (
                "id",
                "name",
                "role",
                "division",
                "manager_id",
                "status",
                "capabilities",
                "permissions",
                "model",
                "model_policy_id",
                "allowed_model_ids",
                "created_by",
                "created_at",
                "updated_at",
            ),
            frozenset({"capabilities", "permissions"}),
        ),
        agent_souls=PostgresRecordRepository(
            database_url,
            "agent_souls",
            AgentSoul,
            (
                "id",
                "agent_id",
                "version",
                "identity",
                "mission",
                "responsibilities",
                "operating_principles",
                "boundaries",
                "escalation_rules",
                "communication_style",
                "created_by",
                "active",
                "created_at",
                "updated_at",
            ),
        ),
        projects=PostgresRecordRepository(
            database_url,
            "projects",
            ProjectRecord,
            ("id", "title", "goal", "status", "priority", "owner_agent_id", "created_at"),
        ),
        project_workspaces=PostgresRecordRepository(
            database_url,
            "project_workspaces",
            ProjectWorkspace,
            (
                "id",
                "project_id",
                "name",
                "summary",
                "memory_scope",
                "allowed_agent_ids",
                "bridge_project_ids",
                "active",
                "created_at",
                "updated_at",
            ),
        ),
        agent_project_assignments=PostgresRecordRepository(
            database_url,
            "agent_project_assignments",
            AgentProjectAssignment,
            (
                "id",
                "project_id",
                "workspace_id",
                "agent_id",
                "assignment_role",
                "active",
                "created_at",
            ),
        ),
        project_complexity_reports=PostgresRecordRepository(
            database_url,
            "project_complexity_reports",
            ProjectComplexityReport,
            (
                "id",
                "project_id",
                "task_count",
                "open_task_count",
                "blocked_task_count",
                "assigned_agent_count",
                "workspace_bridge_count",
                "score",
                "threshold",
                "split_recommended",
                "reasons",
                "created_at",
            ),
        ),
        project_split_requests=PostgresRecordRepository(
            database_url,
            "project_split_requests",
            ProjectSplitRequest,
            (
                "id",
                "project_id",
                "complexity_report_id",
                "requested_by",
                "reason",
                "proposed_shard_titles",
                "status",
                "created_at",
            ),
        ),
        tasks=PostgresRecordRepository(
            database_url,
            "tasks",
            TaskRecord,
            (
                "id",
                "project_id",
                "title",
                "description",
                "status",
                "assigned_agent_id",
                "depends_on",
                "acceptance_criteria",
                "parent_task_id",
                "sequence",
                "result",
                "attempt_count",
                "max_attempts",
                "lease_owner_id",
                "lease_expires_at",
                "last_heartbeat_at",
                "retry_after_at",
                "dead_letter_reason",
                "dead_lettered_at",
                "created_at",
            ),
            frozenset({"result"}),
        ),
        events=PostgresRecordRepository(
            database_url,
            "events",
            EventRecord,
            ("id", "type", "source_agent_id", "target", "payload", "timestamp", "trace_id"),
            frozenset({"payload"}),
        ),
        services=PostgresRecordRepository(
            database_url,
            "services",
            ServiceDefinition,
            (
                "id",
                "name",
                "kind",
                "base_url",
                "health_endpoint",
                "capabilities",
                "credential_scopes",
                "owner_agent_id",
                "allowed_agent_ids",
                "allowed_divisions",
                "audit_required",
                "metadata",
                "enabled",
            ),
            frozenset({"metadata"}),
        ),
        skills=PostgresRecordRepository(
            database_url,
            "skills",
            SkillDefinition,
            (
                "id",
                "name",
                "description",
                "version",
                "required_tools",
                "owner_agent_id",
                "allowed_agent_ids",
                "allowed_divisions",
                "metadata",
                "enabled",
                "created_at",
                "updated_at",
            ),
            frozenset({"metadata"}),
        ),
        model_providers=PostgresRecordRepository(
            database_url,
            "model_providers",
            ModelProviderConfig,
            (
                "id",
                "name",
                "provider_type",
                "base_url",
                "api_key_env_var",
                "default_model_id",
                "enabled",
            ),
        ),
        model_definitions=PostgresRecordRepository(
            database_url,
            "model_definitions",
            ModelDefinition,
            (
                "id",
                "provider_id",
                "display_name",
                "context_window",
                "input_cost_per_million_tokens",
                "output_cost_per_million_tokens",
                "currency",
                "supports_tool_calling",
                "supports_structured_output",
                "enabled",
            ),
        ),
        model_policies=PostgresRecordRepository(
            database_url,
            "model_policies",
            ModelPolicy,
            (
                "id",
                "name",
                "default_model_id",
                "allowed_model_ids",
                "max_cost_per_task",
                "max_cost_per_day",
                "currency",
                "require_human_approval_above",
            ),
        ),
        cost_records=PostgresRecordRepository(
            database_url,
            "cost_records",
            CostRecord,
            (
                "id",
                "provider_id",
                "model_id",
                "agent_id",
                "project_id",
                "task_id",
                "trace_id",
                "input_tokens",
                "output_tokens",
                "total_cost",
                "currency",
                "recorded_at",
            ),
        ),
        audit_logs=PostgresRecordRepository(
            database_url,
            "audit_logs",
            AuditLogRecord,
            (
                "id",
                "actor_type",
                "actor_id",
                "action",
                "target_type",
                "target_id",
                "payload",
                "trace_id",
                "created_at",
            ),
            frozenset({"payload"}),
        ),
        agent_lifecycle_requests=PostgresRecordRepository(
            database_url,
            "agent_lifecycle_requests",
            AgentLifecycleRequest,
            (
                "id",
                "action",
                "requested_by_type",
                "requested_by_id",
                "reason",
                "proposed_agent",
                "target_agent_id",
                "status",
                "requires_human_approval",
                "created_at",
            ),
            frozenset({"proposed_agent"}),
        ),
    )
