from fastapi import FastAPI

from synarch_models import HealthResponse, MemoryContext, MemoryItem

app = FastAPI(title="Synarch Memory Service", version="0.1.0")

MEMORY_ITEMS: dict[str, MemoryItem] = {}


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="memory-service")


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
    scoped_items = [
        item
        for item in MEMORY_ITEMS.values()
        if item.agent_id in {None, request.agent_id}
        and item.project_id in {None, request.project_id}
    ]
    selected = scoped_items[: min(len(scoped_items), 12)]
    summary = "Baseline context assembly: scoped memory items plus current world view."
    return request.model_copy(update={"items": selected, "summary": summary})
