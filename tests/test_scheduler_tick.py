import json
from types import SimpleNamespace
from typing import Any

from synarch_gateway import scheduler_worker as scheduler_tick


def test_build_run_ready_url_encodes_project_filter() -> None:
    url = scheduler_tick.build_run_ready_url(
        "http://localhost:8000/",
        max_tasks=2,
        project_id="project supplier/fr",
    )

    assert url == (
        "http://localhost:8000/tasks/run-ready?"
        "max_tasks=2&project_id=project+supplier%2Ffr"
    )


def test_scheduler_tick_posts_to_gateway_with_trace(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "trace_id": "trace_scheduler_test",
                    "max_tasks": 2,
                    "project_id": "project_demo",
                    "stop_reason": "no_ready_task",
                    "runs": [
                        {
                            "tool_results": [
                                {"tool_name": "web.fetch", "status": "completed"}
                            ],
                            "cost_records": [{"total_cost": 0.0001}],
                        }
                    ],
                }
            ).encode()

    def fake_urlopen(request: Any, *, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["trace_id"] = request.headers["X-synarch-trace-id"]
        captured["worker_id"] = request.headers["X-synarch-scheduler-worker-id"]
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(scheduler_tick, "urlopen", fake_urlopen)

    result = scheduler_tick.run_scheduler_tick(
        gateway_url="http://gateway:8000",
        max_tasks=2,
        project_id="project_demo",
        trace_id="trace_scheduler_test",
        timeout_seconds=12.0,
        worker_id="worker-test",
    )

    assert captured == {
        "url": "http://gateway:8000/tasks/run-ready?max_tasks=2&project_id=project_demo",
        "trace_id": "trace_scheduler_test",
        "worker_id": "worker-test",
        "method": "POST",
        "timeout": 12.0,
    }
    assert result["scheduler"]["worker_id"] == "worker-test"
    assert result["scheduler"]["max_tasks"] == 2
    assert result["scheduler"]["run_count"] == 1
    assert result["scheduler"]["tool_result_count"] == 1
    assert result["scheduler"]["failed_tool_result_count"] == 0
    assert result["scheduler"]["failed_tool_names"] == []
    assert result["scheduler"]["total_cost"] == 0.0001
    assert result["result"]["stop_reason"] == "no_ready_task"


def test_scheduler_summary_counts_tool_results() -> None:
    summary = scheduler_tick.scheduler_result_summary(
        {
            "stop_reason": "max_tasks_reached",
            "runs": [
                {
                    "tool_results": [
                        {"tool_name": "web.fetch", "status": "completed"},
                        {"tool_name": "event.emit", "status": "failed"},
                    ],
                    "cost_records": [{"total_cost": 0.10}],
                },
                {
                    "tool_results": [],
                    "cost_records": [{"total_cost": 0.05}],
                },
            ],
        }
    )

    assert summary == {
        "stop_reason": "max_tasks_reached",
        "run_count": 2,
        "tool_result_count": 2,
        "failed_tool_result_count": 1,
        "failed_tool_names": ["event.emit"],
        "total_cost": 0.15,
    }


def test_run_loop_stops_at_max_ticks(monkeypatch: Any, capsys: Any) -> None:
    ticks: list[str | None] = []

    def fake_run_scheduler_tick(**kwargs: object) -> dict[str, Any]:
        ticks.append(kwargs["trace_id"])  # type: ignore[index]
        return {
            "scheduler": {
                "worker_id": kwargs["worker_id"],
                "gateway_url": kwargs["gateway_url"],
                "project_id": kwargs["project_id"],
                "max_tasks": kwargs["max_tasks"],
                "trace_id": kwargs["trace_id"],
            },
            "result": {"runs": [], "stop_reason": "no_ready_task"},
        }

    monkeypatch.setattr(scheduler_tick, "run_scheduler_tick", fake_run_scheduler_tick)
    monkeypatch.setattr(scheduler_tick.time, "sleep", lambda _seconds: None)

    scheduler_tick.run_loop(
        SimpleNamespace(
            gateway_url="http://gateway:8000",
            worker_id="worker-loop",
            project_id=None,
            max_tasks=1,
            trace_id="trace_loop",
            timeout_seconds=5.0,
            loop=True,
            interval_seconds=0.01,
            max_ticks=2,
        )
    )

    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert ticks == ["trace_loop", "trace_loop"]
    assert [item["scheduler"]["tick"] for item in output] == [1, 2]
    assert [item["scheduler"]["worker_id"] for item in output] == [
        "worker-loop",
        "worker-loop",
    ]
    assert [item["scheduler"]["status"] for item in output] == ["completed", "completed"]


def test_run_loop_logs_tick_failure_and_continues(monkeypatch: Any, capsys: Any) -> None:
    attempts = 0

    def fake_run_scheduler_tick(**kwargs: object) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("gateway timed out")
        return {
            "scheduler": {
                "worker_id": kwargs["worker_id"],
                "gateway_url": kwargs["gateway_url"],
                "project_id": kwargs["project_id"],
                "max_tasks": kwargs["max_tasks"],
                "trace_id": kwargs["trace_id"],
            },
            "result": {"runs": [], "stop_reason": "no_ready_task"},
        }

    monkeypatch.setattr(scheduler_tick, "run_scheduler_tick", fake_run_scheduler_tick)
    monkeypatch.setattr(scheduler_tick.time, "sleep", lambda _seconds: None)

    scheduler_tick.run_loop(
        SimpleNamespace(
            gateway_url="http://gateway:8000",
            worker_id="worker-resilient",
            project_id=None,
            max_tasks=1,
            trace_id="trace_resilient",
            timeout_seconds=5.0,
            loop=True,
            interval_seconds=0.01,
            max_ticks=2,
        )
    )

    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["scheduler"]["status"] for item in output] == ["failed", "completed"]
    assert output[0]["error"] == {
        "type": "TimeoutError",
        "message": "gateway timed out",
    }
