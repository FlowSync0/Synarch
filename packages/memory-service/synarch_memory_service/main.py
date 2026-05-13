from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg import rows
from psycopg.types.json import Jsonb
from pydantic_settings import BaseSettings

from synarch_models import (
    HealthResponse,
    MemoryCompactionPlanItem,
    MemoryCompactionPlanRequest,
    MemoryCompactionPlanResult,
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
EMBEDDING_DIMENSIONS = 1536


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
                  status, embedding, metadata, created_at, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  scope = EXCLUDED.scope,
                  agent_id = EXCLUDED.agent_id,
                  project_id = EXCLUDED.project_id,
                  content = EXCLUDED.content,
                  status = EXCLUDED.status,
                  embedding = EXCLUDED.embedding,
                  metadata = EXCLUDED.metadata,
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
                    Jsonb(item.metadata),
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
                  metadata,
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
                  metadata,
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
    validate_embedding_dimensions(item.embedding, label="Memory embedding")
    try:
        return STORE.create(item)
    except psycopg.errors.ForeignKeyViolation as error:
        raise HTTPException(
            status_code=400,
            detail="Memory item references an unknown project or agent",
        ) from error


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
    existing_compacted_item = matching_compacted_item(source_memory_ids, request)
    if existing_compacted_item is not None:
        return MemoryCompactionPolicyResult(
            compaction_needed=False,
            reason="matching_compaction_exists",
            threshold_tokens=request.min_source_tokens,
            source_memory_ids=source_memory_ids,
            source_count=len(source_items),
            source_tokens=source_tokens,
            existing_compacted_item=existing_compacted_item,
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


@app.post("/memory-items/compaction-plan", response_model=MemoryCompactionPlanResult)
def plan_memory_compaction(
    request: MemoryCompactionPlanRequest,
) -> MemoryCompactionPlanResult:
    groups = compactable_memory_groups(request)
    planned_items: list[MemoryCompactionPlanItem] = []
    for group in groups:
        source_items = group[: request.max_source_items]
        source_tokens = sum(estimated_tokens(item.content) for item in source_items)
        if source_tokens <= request.min_source_tokens:
            continue
        source_memory_ids = [item.id for item in source_items]
        compaction_request = MemoryCompactionRequest(
            scope=source_items[0].scope,
            project_id=source_items[0].project_id,
            agent_id=source_items[0].agent_id,
            status=request.status,
            max_source_items=request.max_source_items,
            max_summary_chars=request.max_summary_chars,
        )
        if matching_compacted_item(source_memory_ids, compaction_request) is not None:
            continue
        planned_items.append(
            MemoryCompactionPlanItem(
                scope=compaction_request.scope,
                project_id=compaction_request.project_id,
                agent_id=compaction_request.agent_id,
                source_memory_ids=source_memory_ids,
                source_count=len(source_items),
                source_tokens=source_tokens,
            )
        )
        if len(planned_items) >= request.max_scopes:
            break
    return MemoryCompactionPlanResult(
        threshold_tokens=request.min_source_tokens,
        inspected_scope_count=len(groups),
        planned_scope_count=len(planned_items),
        items=planned_items,
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
            metadata=compaction_metadata(source_items),
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
    validate_embedding_dimensions(request.query_embedding, label="Query embedding")
    selected: list[MemoryItem] = []
    selected_ids: set[str] = set()
    tokens_used = 0
    related_items_used = 0
    visible_items = {
        item.id: item for item in STORE.list_items() if is_visible(item, request)
    }
    for item in sorted(visible_items.values(), key=lambda item: memory_rank(item, request)):
        added, tokens_used = add_context_item(
            item,
            selected=selected,
            selected_ids=selected_ids,
            tokens_used=tokens_used,
            token_budget=request.token_budget,
        )
        if not added:
            continue
        for related_item in related_memory_items(item, visible_items):
            if related_items_used >= request.max_related_items:
                break
            added_related, tokens_used = add_context_item(
                related_item,
                selected=selected,
                selected_ids=selected_ids,
                tokens_used=tokens_used,
                token_budget=request.token_budget,
            )
            if added_related:
                related_items_used += 1

    ranking = "semantic vector ranking" if request.query_embedding is not None else "scope ranking"
    summary = (
        "Deterministic context assembly selected "
        f"{len(selected)} memory items using {tokens_used}/{request.token_budget} "
        f"estimated tokens with {ranking} and {related_items_used} graph-related items."
    )
    return request.model_copy(
        update={"items": selected, "summary": summary, "tokens_used": tokens_used}
    )


def add_context_item(
    item: MemoryItem,
    *,
    selected: list[MemoryItem],
    selected_ids: set[str],
    tokens_used: int,
    token_budget: int,
) -> tuple[bool, int]:
    if item.id in selected_ids:
        return False, tokens_used
    item_tokens = estimated_tokens(item.content)
    if tokens_used + item_tokens > token_budget:
        return False, tokens_used
    selected.append(item)
    selected_ids.add(item.id)
    return True, tokens_used + item_tokens


def related_memory_items(
    item: MemoryItem,
    visible_items: dict[str, MemoryItem],
) -> list[MemoryItem]:
    return [
        visible_items[memory_id]
        for memory_id in related_memory_ids(item)
        if memory_id in visible_items
    ]


def related_memory_ids(item: MemoryItem) -> list[str]:
    value = item.metadata.get("related_memory_ids")
    if not isinstance(value, list):
        return []
    return [memory_id for memory_id in value if isinstance(memory_id, str) and memory_id]


def is_visible(item: MemoryItem, request: MemoryContext) -> bool:
    if item.status != MemoryStatus.approved:
        return False
    allowed_scopes = set(request.allowed_scopes) or default_allowed_scopes(request)
    if item.scope not in allowed_scopes:
        return False
    if item.agent_id is not None and item.agent_id != request.agent_id:
        return False
    return item.project_id is None or item.project_id in allowed_project_ids(request)


def compactable_memory_items(request: MemoryCompactionRequest) -> list[MemoryItem]:
    items = [
        item
        for item in STORE.list_items()
        if item.status == MemoryStatus.approved and item.scope == request.scope
        and item.metadata.get("kind") != "compaction"
    ]
    if request.project_id is not None:
        items = [item for item in items if item.project_id == request.project_id]
    if request.agent_id is not None:
        items = [item for item in items if item.agent_id == request.agent_id]
    return sorted(items, key=lambda item: (item.created_at, item.id))[
        : request.max_source_items
    ]


def compactable_memory_groups(
    request: MemoryCompactionPlanRequest,
) -> list[list[MemoryItem]]:
    grouped: dict[tuple[str, str | None, str | None], list[MemoryItem]] = {}
    allowed_scopes = set(request.scopes) if request.scopes is not None else None
    for item in STORE.list_items():
        if item.status != MemoryStatus.approved:
            continue
        if item.metadata.get("kind") == "compaction":
            continue
        if allowed_scopes is not None and item.scope not in allowed_scopes:
            continue
        if request.project_id is not None and item.project_id != request.project_id:
            continue
        if request.agent_id is not None and item.agent_id != request.agent_id:
            continue
        key = (item.scope, item.project_id, item.agent_id)
        grouped.setdefault(key, []).append(item)
    groups = [
        sorted(items, key=lambda item: (item.created_at, item.id))
        for _, items in sorted(grouped.items())
    ]
    return groups


def matching_compacted_item(
    source_memory_ids: list[str],
    request: MemoryCompactionRequest,
) -> MemoryItem | None:
    for item in sorted(STORE.list_items(), key=lambda item: (item.created_at, item.id)):
        if item.scope != request.scope:
            continue
        if item.project_id != request.project_id:
            continue
        if item.agent_id != request.agent_id:
            continue
        if item.status not in {MemoryStatus.approved, MemoryStatus.proposed}:
            continue
        if item.metadata.get("kind") != "compaction":
            continue
        if item.metadata.get("source_memory_ids") == source_memory_ids:
            return item
    return None


def compaction_metadata(source_items: list[MemoryItem]) -> dict[str, object]:
    source_memory_ids = [item.id for item in source_items]
    return {
        "kind": "compaction",
        "source_memory_ids": source_memory_ids,
        "source_count": len(source_items),
        "source_tokens": sum(estimated_tokens(item.content) for item in source_items),
    }


def default_allowed_scopes(request: MemoryContext) -> set[str]:
    scopes = {GLOBAL_SCOPE, f"agent:{request.agent_id}"}
    if request.project_id is not None:
        scopes.add(f"project:{request.project_id}")
    return scopes


def allowed_project_ids(request: MemoryContext) -> set[str]:
    project_ids = set(request.allowed_project_ids)
    if request.project_id is not None:
        project_ids.add(request.project_id)
    return project_ids


def scope_rank(item: MemoryItem, request: MemoryContext) -> int:
    if request.project_id is not None and item.scope == f"project:{request.project_id}":
        return 0
    if item.scope == f"agent:{request.agent_id}":
        return 1
    if (
        item.project_id in allowed_project_ids(request)
        and item.scope == f"project:{item.project_id}"
    ):
        return 2
    if item.scope.startswith("division:"):
        return 3
    if item.scope == GLOBAL_SCOPE:
        return 4
    return 5


def memory_rank(item: MemoryItem, request: MemoryContext) -> tuple[int, float, int, datetime, str]:
    similarity = cosine_similarity(request.query_embedding, item.embedding)
    if similarity is None:
        return (1, 0.0, scope_rank(item, request), item.created_at, item.id)
    return (0, -similarity, scope_rank(item, request), item.created_at, item.id)


def cosine_similarity(
    query_embedding: list[float] | None,
    item_embedding: list[float] | None,
) -> float | None:
    if query_embedding is None or item_embedding is None:
        return None
    if len(query_embedding) == 0 or len(query_embedding) != len(item_embedding):
        return None

    dot_product = sum(
        query * item
        for query, item in zip(query_embedding, item_embedding, strict=True)
    )
    query_norm = math.sqrt(sum(value * value for value in query_embedding))
    item_norm = math.sqrt(sum(value * value for value in item_embedding))
    if query_norm == 0.0 or item_norm == 0.0:
        return None
    return dot_product / (query_norm * item_norm)


def validate_embedding_dimensions(embedding: list[float] | None, *, label: str) -> None:
    if embedding is not None and len(embedding) != EMBEDDING_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must have {EMBEDDING_DIMENSIONS} dimensions",
        )


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
    metadata = record.get("metadata")
    if metadata is None:
        record["metadata"] = {}
    elif isinstance(metadata, str):
        record["metadata"] = json.loads(metadata)
    return record
