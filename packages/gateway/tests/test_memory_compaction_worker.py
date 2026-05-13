import argparse
import json
from io import BytesIO
from urllib.request import Request

import pytest

import synarch_gateway.memory_compaction_worker as memory_compaction_worker


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_memory_compaction_payload_omits_empty_filters() -> None:
    payload = memory_compaction_worker.memory_compaction_payload(
        scope="project:demo",
        project_id=None,
        agent_id=None,
        min_source_tokens=1200,
        max_source_items=20,
        max_summary_chars=1200,
    )

    assert payload == {
        "scope": "project:demo",
        "status": "proposed",
        "min_source_tokens": 1200,
        "max_source_items": 20,
        "max_summary_chars": 1200,
    }


def test_memory_compaction_plan_payload_omits_empty_filters() -> None:
    payload = memory_compaction_worker.memory_compaction_plan_payload(
        project_id=None,
        agent_id=None,
        min_source_tokens=1200,
        max_source_items=20,
        max_summary_chars=1200,
        max_scopes=5,
    )

    assert payload == {
        "status": "proposed",
        "min_source_tokens": 1200,
        "max_source_items": 20,
        "max_summary_chars": 1200,
        "max_scopes": 5,
    }


def test_memory_compaction_summary_extracts_created_and_existing_ids() -> None:
    assert memory_compaction_worker.memory_compaction_summary(
        {
            "compaction_needed": True,
            "reason": "source_tokens_exceed_threshold",
            "source_count": 2,
            "source_tokens": 3000,
            "compaction": {"compacted_item": {"id": "memory-new"}},
            "existing_compacted_item": None,
        }
    ) == {
        "compaction_needed": True,
        "reason": "source_tokens_exceed_threshold",
        "source_count": 2,
        "source_tokens": 3000,
        "compacted_memory_id": "memory-new",
        "existing_compacted_memory_id": None,
    }

    assert memory_compaction_worker.memory_compaction_summary(
        {
            "compaction_needed": False,
            "reason": "matching_compaction_exists",
            "source_count": 2,
            "source_tokens": 3000,
            "compaction": None,
            "existing_compacted_item": {"id": "memory-existing"},
        }
    )["existing_compacted_memory_id"] == "memory-existing"


def test_run_memory_compaction_tick_posts_to_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 12.0
        return FakeResponse(
            {
                "compaction_needed": False,
                "reason": "matching_compaction_exists",
                "source_count": 2,
                "source_tokens": 3000,
                "existing_compacted_item": {"id": "memory-existing"},
                "compaction": None,
            }
        )

    monkeypatch.setattr(memory_compaction_worker, "urlopen", fake_urlopen)

    result = memory_compaction_worker.run_memory_compaction_tick(
        gateway_url="http://gateway:8000/",
        scope="project:demo",
        project_id="project_demo",
        agent_id="agent-ops-sourcing",
        min_source_tokens=1200,
        max_source_items=20,
        max_summary_chars=1200,
        trace_id="trace_memory_worker",
        timeout_seconds=12.0,
        worker_id="memory-worker-test",
    )

    request = seen_requests[0]
    assert isinstance(request.data, bytes)
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://gateway:8000/memory-items/compact-if-needed"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-synarch-trace-id") == "trace_memory_worker"
    assert request.get_header("X-synarch-actor-type") == "service"
    assert request.get_header("X-synarch-actor-id") == "memory-worker-test"
    assert body == {
        "scope": "project:demo",
        "status": "proposed",
        "min_source_tokens": 1200,
        "max_source_items": 20,
        "max_summary_chars": 1200,
        "project_id": "project_demo",
        "agent_id": "agent-ops-sourcing",
    }
    assert result["memory_compaction"]["worker_id"] == "memory-worker-test"
    assert result["memory_compaction"]["reason"] == "matching_compaction_exists"
    assert result["memory_compaction"]["existing_compacted_memory_id"] == (
        "memory-existing"
    )


def test_run_memory_compaction_plan_tick_executes_planned_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 12.0
        if request.full_url.endswith("/memory-items/compaction-plan"):
            return FakeResponse(
                {
                    "threshold_tokens": 1200,
                    "inspected_scope_count": 1,
                    "planned_scope_count": 1,
                    "items": [
                        {
                            "scope": "project:demo",
                            "project_id": "project_demo",
                            "agent_id": "agent-ops-sourcing",
                            "source_memory_ids": ["memory-a", "memory-b"],
                            "source_count": 2,
                            "source_tokens": 3000,
                        }
                    ],
                }
            )
        return FakeResponse(
            {
                "compaction_needed": True,
                "reason": "source_tokens_exceed_threshold",
                "source_count": 2,
                "source_tokens": 3000,
                "compaction": {"compacted_item": {"id": "memory-new"}},
                "existing_compacted_item": None,
            }
        )

    monkeypatch.setattr(memory_compaction_worker, "urlopen", fake_urlopen)

    result = memory_compaction_worker.run_memory_compaction_plan_tick(
        gateway_url="http://gateway:8000/",
        project_id="project_demo",
        agent_id=None,
        min_source_tokens=1200,
        max_source_items=20,
        max_summary_chars=1200,
        max_scopes=5,
        trace_id="trace_memory_plan_worker",
        timeout_seconds=12.0,
        worker_id="memory-worker-test",
    )

    assert [request.full_url for request in seen_requests] == [
        "http://gateway:8000/memory-items/compaction-plan",
        "http://gateway:8000/memory-items/compact-if-needed",
    ]
    assert result["memory_compaction"]["planned_scope_count"] == 1
    assert result["memory_compaction"]["executed_scope_count"] == 1
    assert result["memory_compaction"]["compacted_scope_count"] == 1
    assert result["executions"][0]["memory_compaction"]["scope"] == "project:demo"


def test_run_loop_continues_after_transient_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def fake_tick(**kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary gateway timeout")
        return {
            "memory_compaction": {
                "worker_id": kwargs["worker_id"],
                "gateway_url": kwargs["gateway_url"],
                "scope": kwargs["scope"],
                "project_id": kwargs["project_id"],
                "agent_id": kwargs["agent_id"],
                "trace_id": kwargs["trace_id"],
                "compaction_needed": False,
                "reason": "source_tokens_within_threshold",
                "source_count": 1,
                "source_tokens": 20,
                "compacted_memory_id": None,
                "existing_compacted_memory_id": None,
            },
            "result": {"compaction_needed": False},
        }

    monkeypatch.setattr(
        memory_compaction_worker,
        "run_memory_compaction_tick",
        fake_tick,
    )
    monkeypatch.setattr(
        "synarch_gateway.memory_compaction_worker.time.sleep",
        lambda seconds: None,
    )

    memory_compaction_worker.run_loop(
        argparse.Namespace(
            gateway_url="http://gateway:8000",
            worker_id="memory-worker-test",
            scope="project:demo",
            project_id=None,
            agent_id=None,
            min_source_tokens=1200,
            max_source_items=20,
            max_summary_chars=1200,
            max_scopes=20,
            trace_id="trace_static",
            timeout_seconds=1.0,
            loop=True,
            interval_seconds=1.0,
            max_ticks=2,
        )
    )

    lines = [json.loads(line) for line in BytesIO(capsys.readouterr().out.encode())]
    assert lines[0]["memory_compaction"]["status"] == "failed"
    assert lines[0]["error"]["type"] == "TimeoutError"
    assert lines[1]["memory_compaction"]["status"] == "completed"
    assert lines[1]["memory_compaction"]["tick"] == 2
