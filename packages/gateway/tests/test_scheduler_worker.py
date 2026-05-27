import argparse
import json
from io import BytesIO
from typing import cast
from urllib.request import Request

import pytest

import synarch_gateway.scheduler_worker as scheduler_worker


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_run_scheduler_tick_posts_to_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 12.0
        return FakeResponse({"stop_reason": "no_ready_task", "runs": []})

    monkeypatch.setattr(scheduler_worker, "urlopen", fake_urlopen)

    result = scheduler_worker.run_scheduler_tick(
        gateway_url="http://gateway:8000",
        max_tasks=2,
        project_id="project_demo",
        trace_id="trace_scheduler_worker",
        timeout_seconds=12.0,
        worker_id="scheduler-worker-test",
    )

    request = seen_requests[0]
    assert request.full_url == (
        "http://gateway:8000/tasks/run-ready?max_tasks=2&project_id=project_demo"
    )
    assert request.get_method() == "POST"
    assert request.get_header("X-synarch-trace-id") == "trace_scheduler_worker"
    assert request.get_header("X-synarch-scheduler-worker-id") == "scheduler-worker-test"
    assert result["scheduler"]["worker_id"] == "scheduler-worker-test"
    assert result["scheduler"]["stop_reason"] == "no_ready_task"
    assert result["scheduler"]["run_count"] == 0


def test_run_loop_records_worker_heartbeat_after_transient_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0
    recorded_heartbeats: list[dict[str, object]] = []

    def fake_tick(**kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary gateway timeout")
        return {
            "scheduler": {
                "worker_id": kwargs["worker_id"],
                "gateway_url": kwargs["gateway_url"],
                "project_id": kwargs["project_id"],
                "max_tasks": kwargs["max_tasks"],
                "trace_id": kwargs["trace_id"],
                "stop_reason": "no_ready_task",
                "run_count": 0,
                "tool_result_count": 0,
                "failed_tool_result_count": 0,
                "failed_tool_names": [],
                "failed_tool_errors": [],
                "total_cost": 0.0,
            },
            "result": {"runs": []},
        }

    def fake_heartbeat(**kwargs: object) -> dict[str, object]:
        recorded_heartbeats.append(kwargs)
        return {
            "id": kwargs["worker_id"],
            "status": kwargs["status"],
            "heartbeat_count": len(recorded_heartbeats),
        }

    monkeypatch.setattr(scheduler_worker, "run_scheduler_tick", fake_tick)
    monkeypatch.setattr(scheduler_worker, "record_worker_heartbeat", fake_heartbeat)
    monkeypatch.setattr("synarch_gateway.scheduler_worker.time.sleep", lambda seconds: None)

    scheduler_worker.run_loop(
        argparse.Namespace(
            gateway_url="http://gateway:8000",
            worker_id="scheduler-worker-test",
            project_id="project_demo",
            max_tasks=2,
            trace_id="trace_static",
            timeout_seconds=1.0,
            loop=True,
            interval_seconds=1.0,
            max_ticks=2,
        )
    )

    lines = [json.loads(line) for line in BytesIO(capsys.readouterr().out.encode())]
    assert lines[0]["scheduler"]["status"] == "failed"
    assert lines[0]["error"]["type"] == "TimeoutError"
    assert lines[0]["worker_heartbeat"]["status"] == "failed"
    assert lines[1]["scheduler"]["status"] == "completed"
    assert lines[1]["scheduler"]["tick"] == 2
    assert lines[1]["worker_heartbeat"]["status"] == "completed"
    assert [heartbeat["status"] for heartbeat in recorded_heartbeats] == [
        "failed",
        "completed",
    ]
    assert recorded_heartbeats[1]["worker_kind"] == "scheduler"
    assert recorded_heartbeats[1]["target"] == "project_demo"
    last_tick_result = cast(dict[str, object], recorded_heartbeats[1]["last_tick_result"])
    assert last_tick_result["run_count"] == 0
