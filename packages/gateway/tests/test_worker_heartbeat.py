import json
from urllib.request import Request

import pytest

import synarch_gateway.worker_heartbeat as worker_heartbeat


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def request_payload(request: Request) -> dict[str, object]:
    data = request.data or b"{}"
    assert isinstance(data, bytes)
    payload = json.loads(data.decode("utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_record_worker_heartbeat_posts_to_state_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 7.0
        return FakeResponse(
            {
                "id": "scheduler-worker-test",
                "worker_kind": "scheduler",
                "status": "completed",
                "heartbeat_count": 1,
            }
        )

    monkeypatch.setattr(worker_heartbeat, "urlopen", fake_urlopen)

    result = worker_heartbeat.record_worker_heartbeat(
        state_service_url="http://state-service:8020/",
        worker_id="scheduler-worker-test",
        worker_kind="scheduler",
        status="completed",
        target="project_demo",
        last_tick_result={"run_count": 0},
        last_error=None,
        trace_id="trace_worker_heartbeat",
        timeout_seconds=7.0,
    )

    request = seen_requests[0]
    assert request.full_url == "http://state-service:8020/worker-heartbeats/scheduler-worker-test"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-synarch-trace-id") == "trace_worker_heartbeat"
    assert request_payload(request) == {
        "worker_kind": "scheduler",
        "status": "completed",
        "target": "project_demo",
        "last_tick_result": {"run_count": 0},
        "last_error": None,
    }
    assert result["heartbeat_count"] == 1
