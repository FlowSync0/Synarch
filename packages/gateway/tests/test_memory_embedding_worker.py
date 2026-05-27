import argparse
import json
from io import BytesIO
from typing import cast
from urllib.request import Request

import pytest

import synarch_gateway.memory_embedding_worker as memory_embedding_worker


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_memory_embedding_backfill_payload_omits_empty_filters() -> None:
    payload = memory_embedding_worker.memory_embedding_backfill_payload(
        project_id=None,
        agent_id=None,
        scope=None,
        status="approved",
        max_items=10,
    )

    assert payload == {
        "status": "approved",
        "max_items": 10,
    }


def test_memory_embedding_backfill_summary_extracts_counts() -> None:
    assert memory_embedding_worker.memory_embedding_backfill_summary(
        {
            "inspected_count": 3,
            "backfilled_count": 1,
            "skipped_count": 2,
            "memory_ids": ["memory-a"],
        }
    ) == {
        "inspected_count": 3,
        "backfilled_count": 1,
        "skipped_count": 2,
        "memory_ids": ["memory-a"],
    }


def test_run_memory_embedding_backfill_tick_posts_to_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 12.0
        return FakeResponse(
            {
                "inspected_count": 2,
                "backfilled_count": 1,
                "skipped_count": 1,
                "memory_ids": ["memory-a"],
            }
        )

    monkeypatch.setattr(memory_embedding_worker, "urlopen", fake_urlopen)

    result = memory_embedding_worker.run_memory_embedding_backfill_tick(
        gateway_url="http://gateway:8000/",
        project_id="project_demo",
        agent_id="agent-dev",
        scope="project:project_demo",
        status="approved",
        max_items=5,
        trace_id="trace_memory_embedding_worker",
        timeout_seconds=12.0,
        worker_id="memory-embedding-worker-test",
    )

    request = seen_requests[0]
    assert isinstance(request.data, bytes)
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://gateway:8000/memory-items/embedding-backfill"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-synarch-trace-id") == "trace_memory_embedding_worker"
    assert request.get_header("X-synarch-actor-type") == "service"
    assert request.get_header("X-synarch-actor-id") == "memory-embedding-worker-test"
    assert body == {
        "status": "approved",
        "max_items": 5,
        "project_id": "project_demo",
        "agent_id": "agent-dev",
        "scope": "project:project_demo",
    }
    assert result["memory_embedding_backfill"]["worker_id"] == (
        "memory-embedding-worker-test"
    )
    assert result["memory_embedding_backfill"]["backfilled_count"] == 1
    assert result["memory_embedding_backfill"]["memory_ids"] == ["memory-a"]


def test_run_loop_continues_after_transient_error(
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
            "memory_embedding_backfill": {
                "worker_id": kwargs["worker_id"],
                "gateway_url": kwargs["gateway_url"],
                "scope": kwargs["scope"],
                "project_id": kwargs["project_id"],
                "agent_id": kwargs["agent_id"],
                "memory_status": kwargs["status"],
                "max_items": kwargs["max_items"],
                "trace_id": kwargs["trace_id"],
                "inspected_count": 2,
                "backfilled_count": 1,
                "skipped_count": 1,
                "memory_ids": ["memory-a"],
            },
            "result": {"backfilled_count": 1},
        }

    def fake_heartbeat(**kwargs: object) -> dict[str, object]:
        recorded_heartbeats.append(kwargs)
        return {
            "id": kwargs["worker_id"],
            "status": kwargs["status"],
            "heartbeat_count": len(recorded_heartbeats),
        }

    monkeypatch.setattr(
        memory_embedding_worker,
        "run_memory_embedding_backfill_tick",
        fake_tick,
    )
    monkeypatch.setattr(
        memory_embedding_worker,
        "record_worker_heartbeat",
        fake_heartbeat,
    )
    monkeypatch.setattr(
        "synarch_gateway.memory_embedding_worker.time.sleep",
        lambda seconds: None,
    )

    memory_embedding_worker.run_loop(
        argparse.Namespace(
            gateway_url="http://gateway:8000",
            worker_id="memory-embedding-worker-test",
            project_id=None,
            agent_id=None,
            scope=None,
            status="approved",
            max_items=10,
            trace_id="trace_static",
            timeout_seconds=1.0,
            loop=True,
            interval_seconds=1.0,
            max_ticks=2,
        )
    )

    lines = [json.loads(line) for line in BytesIO(capsys.readouterr().out.encode())]
    assert lines[0]["memory_embedding_backfill"]["status"] == "failed"
    assert lines[0]["error"]["type"] == "TimeoutError"
    assert lines[0]["worker_heartbeat"]["status"] == "failed"
    assert lines[1]["memory_embedding_backfill"]["status"] == "completed"
    assert lines[1]["memory_embedding_backfill"]["tick"] == 2
    assert lines[1]["worker_heartbeat"]["status"] == "completed"
    assert [heartbeat["status"] for heartbeat in recorded_heartbeats] == [
        "failed",
        "completed",
    ]
    assert recorded_heartbeats[1]["worker_kind"] == "memory_embedding"
    assert recorded_heartbeats[1]["target"] == "approved"
    last_tick_result = cast(dict[str, object], recorded_heartbeats[1]["last_tick_result"])
    assert last_tick_result["backfilled_count"] == 1
