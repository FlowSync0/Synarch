from fastapi import FastAPI

from synarch_models import HealthResponse, MemoryContext, MemoryItem

app = FastAPI(title="Synarch Memory Service", version="0.1.0")

MEMORY_ITEMS: dict[str, MemoryItem] = {}

GLOBAL_SCOPE = "global"


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="memory-service")


def reset_memory_items() -> None:
    MEMORY_ITEMS.clear()


@app.post("/memory-items", response_model=MemoryItem, status_code=201)
def create_memory_item(item: MemoryItem) -> MemoryItem:
    MEMORY_ITEMS[item.id] = item
    return item


@app.get("/memory-items", response_model=list[MemoryItem])
def list_memory_items(scope: str | None = None, agent_id: str | None = None) -> list[MemoryItem]:
    items = list(MEMORY_ITEMS.values())
    if scope is not None:
        items = [item for item in items if item.scope == scope]
    if agent_id is not None:
        items = [item for item in items if item.agent_id == agent_id]
    return items


@app.post("/context/assemble", response_model=MemoryContext)
def assemble_context(request: MemoryContext) -> MemoryContext:
    selected: list[MemoryItem] = []
    tokens_used = 0
    for item in sorted(
        (item for item in MEMORY_ITEMS.values() if is_visible(item, request)),
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
    allowed_scopes = set(request.allowed_scopes) or default_allowed_scopes(request)
    if item.scope not in allowed_scopes:
        return False
    if item.agent_id is not None and item.agent_id != request.agent_id:
        return False
    return item.project_id is None or item.project_id == request.project_id


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
