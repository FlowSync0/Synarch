from collections.abc import Iterable

from fastapi.testclient import TestClient

from synarch_agent_runtime.main import app as agent_runtime_app
from synarch_control_plane.main import app as control_plane_app
from synarch_event_service.main import app as event_service_app
from synarch_gateway.main import app as gateway_app
from synarch_memory_service.main import app as memory_service_app
from synarch_state_service.main import app as state_service_app


def health_apps() -> Iterable[tuple[str, object]]:
    return [
        ("gateway", gateway_app),
        ("control-plane", control_plane_app),
        ("state-service", state_service_app),
        ("memory-service", memory_service_app),
        ("event-service", event_service_app),
        ("agent-runtime", agent_runtime_app),
    ]


def main() -> None:
    for name, app in health_apps():
        response = TestClient(app).get("/healthz")
        response.raise_for_status()
        print(f"{name}: {response.json()['status']}")


if __name__ == "__main__":
    main()
