from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from synarch_models import (
    AgentDefinition,
    AgentLifecycleRequest,
    AgentProjectAssignment,
    AgentSoul,
    AuditLogRecord,
    ConnectorJobRecord,
    ConnectorJobRunRecord,
    CostRecord,
    CredentialAccessRequest,
    CredentialGrant,
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


class RecordRepository[RecordT](Protocol):
    def create(self, record_id: str, record: RecordT) -> RecordT: ...

    def update(self, record_id: str, record: RecordT) -> RecordT: ...

    def update_if(
        self,
        record_id: str,
        record: RecordT,
        expected: dict[str, object],
    ) -> RecordT | None: ...

    def exists(self, record_id: str) -> bool: ...

    def get(self, record_id: str) -> RecordT | None: ...

    def list_records(self) -> list[RecordT]: ...


@dataclass
class InMemoryRecordRepository[RecordT]:
    records: dict[str, RecordT] = field(default_factory=dict)

    def create(self, record_id: str, record: RecordT) -> RecordT:
        self.records[record_id] = record
        return record

    def update(self, record_id: str, record: RecordT) -> RecordT:
        self.records[record_id] = record
        return record

    def update_if(
        self,
        record_id: str,
        record: RecordT,
        expected: dict[str, object],
    ) -> RecordT | None:
        current = self.records.get(record_id)
        if current is None:
            return None
        for field_name, expected_value in expected.items():
            if getattr(current, field_name) != expected_value:
                return None
        self.records[record_id] = record
        return record

    def exists(self, record_id: str) -> bool:
        return record_id in self.records

    def get(self, record_id: str) -> RecordT | None:
        return self.records.get(record_id)

    def list_records(self) -> list[RecordT]:
        return list(self.records.values())


@dataclass
class StateRepositories:
    divisions: RecordRepository[DivisionRecord]
    agents: RecordRepository[AgentDefinition]
    agent_souls: RecordRepository[AgentSoul]
    projects: RecordRepository[ProjectRecord]
    project_workspaces: RecordRepository[ProjectWorkspace]
    agent_project_assignments: RecordRepository[AgentProjectAssignment]
    project_complexity_reports: RecordRepository[ProjectComplexityReport]
    project_split_requests: RecordRepository[ProjectSplitRequest]
    tasks: RecordRepository[TaskRecord]
    events: RecordRepository[EventRecord]
    services: RecordRepository[ServiceDefinition]
    skills: RecordRepository[SkillDefinition]
    model_providers: RecordRepository[ModelProviderConfig]
    model_definitions: RecordRepository[ModelDefinition]
    model_policies: RecordRepository[ModelPolicy]
    cost_records: RecordRepository[CostRecord]
    audit_logs: RecordRepository[AuditLogRecord]
    agent_lifecycle_requests: RecordRepository[AgentLifecycleRequest]
    credential_access_requests: RecordRepository[CredentialAccessRequest]
    credential_grants: RecordRepository[CredentialGrant]
    connector_jobs: RecordRepository[ConnectorJobRecord]
    connector_job_runs: RecordRepository[ConnectorJobRunRecord]

    @classmethod
    def in_memory(cls) -> StateRepositories:
        return cls(
            divisions=InMemoryRecordRepository(),
            agents=InMemoryRecordRepository(),
            agent_souls=InMemoryRecordRepository(),
            projects=InMemoryRecordRepository(),
            project_workspaces=InMemoryRecordRepository(),
            agent_project_assignments=InMemoryRecordRepository(),
            project_complexity_reports=InMemoryRecordRepository(),
            project_split_requests=InMemoryRecordRepository(),
            tasks=InMemoryRecordRepository(),
            events=InMemoryRecordRepository(),
            services=InMemoryRecordRepository(),
            skills=InMemoryRecordRepository(),
            model_providers=InMemoryRecordRepository(),
            model_definitions=InMemoryRecordRepository(),
            model_policies=InMemoryRecordRepository(),
            cost_records=InMemoryRecordRepository(),
            audit_logs=InMemoryRecordRepository(),
            agent_lifecycle_requests=InMemoryRecordRepository(),
            credential_access_requests=InMemoryRecordRepository(),
            credential_grants=InMemoryRecordRepository(),
            connector_jobs=InMemoryRecordRepository(),
            connector_job_runs=InMemoryRecordRepository(),
        )

    @classmethod
    def postgres(cls, database_url: str) -> StateRepositories:
        from synarch_state_service.postgres_repositories import build_postgres_repositories

        return build_postgres_repositories(database_url)
