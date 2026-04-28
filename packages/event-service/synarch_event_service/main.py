from fastapi import FastAPI

from synarch_models import EventRecord, HealthResponse

app = FastAPI(title="Synarch Event Service", version="0.1.0")

EVENTS: list[EventRecord] = []


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(service="event-service")


@app.post("/events", response_model=EventRecord, status_code=202)
def emit_event(event: EventRecord) -> EventRecord:
    EVENTS.append(event)
    return event


@app.get("/events", response_model=list[EventRecord])
def list_events(event_type: str | None = None) -> list[EventRecord]:
    if event_type is None:
        return EVENTS
    return [event for event in EVENTS if event.type == event_type]
