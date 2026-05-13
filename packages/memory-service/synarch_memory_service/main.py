from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg import rows
from pydantic_settings import BaseSettings

from synarch_models import (
    HealthResponse,
    MemoryCompactionPolicyRequest,
    MemoryCompactionPolicyResult,
    MemoryCompactionRequest,
    MemoryCompactionResult,
    MemoryContext,
    MemoryItem,
    MemoryStatus,
    MemoryStatusUpdate,
)

app = FastAPI(title="Synarch Memory Service", version="0.1.0")

GLOBAL_SCOPE = "global"


class Settings(BaseSettings):
    database_url: str | None = None


settings = Settings()


class MemoryStore(Protocol):
    def create(self, item: MemoryItem) -> MemoryItem: ...

    def update_status(self, item_id: str, status: MemoryStatus) -> MemoryItem | None: ...

    def list_items(self) -> list[MemoryItem]: ...

    def reset(self) -> None: ...


@dataclass
class InMemoryMemoryStore:
    items: dict[str, MemoryItem] = field(default_factory=dict)

    def create(self, item: MemoryItem) -> MemoryItem:
        self.items[item.id] = item
        return item

    def update_status(self, item_id: str, status: MemoryStatus) -> MemoryItem | None:
        item = self.items.get(item_id)
        if item is None:
            return None
        updated = item.model_copy(update={"status": status})
        self.items[item_id] = updated
        return updated

    def list_items(self) -> list[MemoryItem]:
        return list(self.items.values())

    def reset(self) -> None:
        self.items.clear()


@dataclass(frozen=True)
class PostgresMemoryStore:
    database_url: str

    def create(self, item: MemoryItem) -> MemoryItem:
        with psycopg.connect(normalize_postgres_dsn(self.database_url)) as connection:
            connection.execute(
                """
                INSERT INTO memory_items (
                  id, scope, agent_id, project_id, content,
                  status, embedding, created_at, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  scope = EXCLUDED.scope,
                  agent_id = EXCLUDED.agent_id,
                  project_id = EXCLUDED.project_id,
                  content = EXCLUDED.content,
                  status = EXCLUDED.status,
                  embedding = EXCLUDED.embedding,
                  created_at = EXCLUDED.created_at,
                  expires_at = EXCLUDED.expires_at
                """,
                [
                    item.id,
                    item.scope,
                    item.agent_id,
                    item.project_id,
                    item.content,
                    item.status,
                    vector_literal(item.embedding),
                    item.created_at,
                    item.expires_at,
                ],
            )
        return item

    def update_status(self, item_id: str, status: MemoryStatus) -> MemoryItem | None:
        with psycopg.connect(
            normalize_postgres_dsn(self.database_url),
            row_factory=rows.dict_row,
        ) as connection:
            record = connection.execute(
                """
                UPDATE memory_items
                SET status = %s
                WHERE id = %s
                RETURNING
                  id,
                  scope,
                  agent_id,
                  project_id,
                  content,
                  status,
                  embedding::text AS embedding,
                  created_at,
                  expires_at
                """,
                [status, item_id],
            ).fetchone()
        if record is None:
            return None
        return MemoryItem.model_validate(deserialize_memory_row(record))

    def list_items(self) -> list[MemoryItem]:
        with psycopg.connect(
            normalize_postgres_dsn(self.database_url),
            row_factory=rows.dict_row,
        ) as connection:
            records = connection.execute(
                """
                SELECT
                  id,
                  scope,
                  agent_id,
                  project_id,
                  content,
                  status,
                  embedding::text AS embedding,
                  created_at,
                  expires_at
                FROM memory_items
                ORDER BY created_at, id
                """
            ).fetchall()
        return [MemoryItem.model_validate(deserialize_memory_row(record)) for record in records]

    def reset(self) -> None:
        with psycopg.connect(normalize_postgres_dsn(self.database_url)) as connection:
            connection.execute("DELETE FROM memory_items")


def build_memory_store() -> MemoryStore:
    if settings.database_url:
        return PostgresMemoryStore(settings.database_url)
    return InMemoryMemoryStore()


STORE: MemoryStore = build_memory_store()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="memory-service")


def reset_memory_items() -> None:
    STORE.reset()


@app.post("/memory-items", response_model=MemoryItem, status_code=201)
def create_memory_item(item: MemoryItem) -> MemoryItem:
    return STORE.create(item)


@app.patch("/memory-items/{item_id}/status", response_model=MemoryItem)
def update_memory_item_status(item_id: str, update: MemoryStatusUpdate) -> MemoryItem:
    item = STORE.update_status(item_id, update.status)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return item


@app.get("/memory-items", response_model=list[MemoryItem])
def list_memory_items(
    scope: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    status: MemoryStatus | None = None,
) -> list[MemoryItem]:
    items = STORE.list_items()
    if scope is not None:
        items = [item for item in items if item.scope == scope]
    if agent_id is not None:
        items = [item for item in items if item.agent_id == agent_id]
    if project_id is not None:
        items = [item for item in items if item.project_id == project_id]
    if status is not None:
        items = [item for item in items if item.status == status]
    return items


@app.post("/memory-items/compact", response_model=MemoryCompactionResult, status_code=201)
def compact_memory_items(request: MemoryCompactionRequest) -> MemoryCompactionResult:
    source_items = compactable_memory_items(request)
    if not source_items:
        raise HTTPException(
            status_code=404,
            detail="No approved memory items match compaction request",
        )
    return create_compaction_result(source_items, request)


@app.post("/memory-items/compact-if-needed", response_model=MemoryCompactionPolicyResult)
def compact_memory_items_if_needed(
    request: MemoryCompactionPolicyRequest,
) -> MemoryCompactionPolicyResult:
    source_items = compactable_memory_items(request)
    source_tokens = sum(estimated_tokens(item.content) for item in source_items)
    source_memory_ids = [item.id for item in source_items]
    if not source_items:
        return MemoryCompactionPolicyResult(
            compaction_needed=False,
            reason="no_approved_memory_items",
            threshold_tokens=request.min_source_tokens,
        )
    if source_tokens <= request.min_source_tokens:
        return MemoryCompactionPolicyResult(
            compaction_needed=False,
            reason="source_tokens_within_threshold",
            threshold_tokens=request.min_source_tokens,
            source_memory_ids=source_memory_ids,
            source_count=len(source_items),
            source_tokens=source_tokens,
        )
    compaction = create_compaction_result(source_items, request)
    return MemoryCompactionPolicyResult(
        compaction_needed=True,
        reason="source_tokens_exceed_threshold",
        threshold_tokens=request.min_source_tokens,
        source_memory_ids=source_memory_ids,
        source_count=len(source_items),
        source_tokens=source_tokens,
        compaction=compaction,
    )


def create_compaction_result(
    source_items: list[MemoryItem],
    request: MemoryCompactionRequest,
) -> MemoryCompactionResult:
    compacted_item = STORE.create(
        MemoryItem(
            scope=request.scope,
            content=compacted_memory_content(source_items, request),
            status=request.status,
            agent_id=request.agent_id,
            project_id=request.project_id,
        )
    )
    return MemoryCompactionResult(
        compacted_item=compacted_item,
        source_memory_ids=[item.id for item in source_items],
        source_count=len(source_items),
        source_tokens=sum(estimated_tokens(item.content) for item in source_items),
    )


@app.post("/context/assemble", response_model=MemoryContext)
def assemble_context(request: MemoryContext) -> MemoryContext:
    selected: list[MemoryItem] = []
    tokens_used = 0
    for item in sorted(
        (item for item in STORE.list_items() if is_visible(item, request)),
        key=lambda item: (scope_rank(item, request), item.created_at),
    ):
        item_tokens = estimated_tokens(item.content)
        if tokens_used + item_tokens > request.token_budget:
            continue
        selected.append(item)
        tokens_used += item_tokens

    summary = (
        "Deterministic context assembly selected "
        f"{len(selected)} memory items using {tokens_used}/{request.token_budget} estimated tokens."
    )
    return request.model_copy(
        update={"items": selected, "summary": summary, "tokens_used": tokens_used}
    )


def is_visible(item: MemoryItem, request: MemoryContext) -> bool:
    if item.status != MemoryStatus.approved:
        return False
    allowed_scopes = set(request.allowed_scopes) or default_allowed_scopes(request)
    if item.scope not in allowed_scopes:
        return False
    if item.agent_id is not None and item.agent_id != request.agent_id:
        return False
    return item.project_id is None or item.project_id == request.project_id


def compactable_memory_items(request: MemoryCompactionRequest) -> list[MemoryItem]:
    items = [
        item
        for item in STORE.list_items()
        if item.status == MemoryStatus.approved and item.scope == request.scope
    ]
    if request.project_id is not None:
        items = [item for item in items if item.project_id == request.project_id]
    if request.agent_id is not None:
        items = [item for item in items if item.agent_id == request.agent_id]
    return sorted(items, key=lambda item: (item.created_at, item.id))[
        : request.max_source_items
    ]


def default_allowed_scopes(request: MemoryContext) -> set[str]:
    scopes = {GLOBAL_SCOPE, f"agent:{request.agent_id}"}
    if request.project_id is not None:
        scopes.add(f"project:{request.project_id}")
    return scopes


def scope_rank(item: MemoryItem, request: MemoryContext) -> int:
    if request.project_id is not None and item.scope == f"project:{request.project_id}":
        return 0
    if item.scope == f"agent:{request.agent_id}":
        return 1
    if item.scope.startswith("division:"):
        return 2
    if item.scope == GLOBAL_SCOPE:
        return 3
    return 4


def estimated_tokens(content: str) -> int:
    return max(1, (len(content) + 3) // 4)


def compacted_memory_content(
    source_items: list[MemoryItem],
    request: MemoryCompactionRequest,
) -> str:
    lines = [
        f"Compacted memory for scope {request.scope}.",
        "Source memory ids: " + ", ".join(item.id for item in source_items),
        "Source facts:",
    ]
    lines.extend(
        f"- [{item.id}] {single_line(item.content)}" for item in source_items
    )
    content = "\n".join(lines)
    if len(content) <= request.max_summary_chars:
        return content
    return content[: request.max_summary_chars - 3].rstrip() + "..."


def single_line(content: str) -> str:
    return " ".join(content.split())


def normalize_postgres_dsn(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


def vector_literal(embedding: list[float] | None) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def deserialize_memory_row(record: dict[str, object]) -> dict[str, object]:
    embedding = record.get("embedding")
    if isinstance(embedding, str):
        stripped = embedding.strip("[]")
        record["embedding"] = (
            [float(value) for value in stripped.split(",") if value.strip()]
            if stripped
            else []
        )
    return record
