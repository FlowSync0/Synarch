from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from synarch_models import (
    AgentDefinition,
    AgentLifecycleRequest,
    AuditLogRecord,
    CostRecord,
    DivisionRecord,
    EventRecord,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ProjectRecord,
    ServiceDefinition,
    TaskRecord,
)


class RecordRepository[RecordT](Protocol):
    def create(self, record_id: str, record: RecordT) -> RecordT: ...

    def update(self, record_id: str, record: RecordT) -> RecordT: ...

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
    projects: RecordRepository[ProjectRecord]
    tasks: RecordRepository[TaskRecord]
    events: RecordRepository[EventRecord]
    services: RecordRepository[ServiceDefinition]
    model_providers: RecordRepository[ModelProviderConfig]
    model_definitions: RecordRepository[ModelDefinition]
    model_policies: RecordRepository[ModelPolicy]
    cost_records: RecordRepository[CostRecord]
    audit_logs: RecordRepository[AuditLogRecord]
    agent_lifecycle_requests: RecordRepository[AgentLifecycleRequest]

    @classmethod
    def in_memory(cls) -> StateRepositories:
        return cls(
            divisions=InMemoryRecordRepository(),
            agents=InMemoryRecordRepository(),
            projects=InMemoryRecordRepository(),
            tasks=InMemoryRecordRepository(),
            events=InMemoryRecordRepository(),
            services=InMemoryRecordRepository(),
            model_providers=InMemoryRecordRepository(),
            model_definitions=InMemoryRecordRepository(),
            model_policies=InMemoryRecordRepository(),
            cost_records=InMemoryRecordRepository(),
            audit_logs=InMemoryRecordRepository(),
            agent_lifecycle_requests=InMemoryRecordRepository(),
        )

    @classmethod
    def postgres(cls, database_url: str) -> StateRepositories:
        from synarch_state_service.postgres_repositories import build_postgres_repositories

        return build_postgres_repositories(database_url)
