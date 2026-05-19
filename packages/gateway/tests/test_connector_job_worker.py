import argparse
import json
from io import BytesIO
from urllib.request import Request

import pytest

import synarch_gateway.connector_job_worker as connector_job_worker


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_build_connector_jobs_run_ready_url_encodes_filters() -> None:
    url = connector_job_worker.build_connector_jobs_run_ready_url(
        "http://gateway:8000/",
        max_jobs=2,
        kind="cron",
        project_id="project demo",
        service_id="connector-supplier-web",
        owner_agent_id="agent-ops-sourcing",
    )

    assert url == (
        "http://gateway:8000/connector-jobs/run-ready?"
        "max_jobs=2&kind=cron&project_id=project+demo&"
        "service_id=connector-supplier-web&owner_agent_id=agent-ops-sourcing"
    )


def test_connector_job_result_summary_counts_statuses() -> None:
    summary = connector_job_worker.connector_job_result_summary(
        {
            "stop_reason": "max_jobs_reached",
            "runs": [
                {"run": {"status": "completed"}},
                {"run": {"status": "failed"}},
                {"run": {"status": "blocked"}},
                {"run": {"status": "skipped"}},
            ],
        }
    )

    assert summary == {
        "stop_reason": "max_jobs_reached",
        "run_count": 4,
        "completed_run_count": 1,
        "failed_run_count": 1,
        "blocked_run_count": 1,
        "skipped_run_count": 1,
    }


def test_run_connector_job_tick_posts_to_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 12.0
        return FakeResponse(
            {
                "stop_reason": "no_ready_connector_job",
                "runs": [],
            }
        )

    monkeypatch.setattr(connector_job_worker, "urlopen", fake_urlopen)

    result = connector_job_worker.run_connector_job_tick(
        gateway_url="http://gateway:8000",
        max_jobs=1,
        kind="cron",
        project_id="project_demo",
        service_id=None,
        owner_agent_id=None,
        trace_id="trace_connector_worker",
        timeout_seconds=12.0,
        worker_id="connector-worker-test",
    )

    request = seen_requests[0]
    assert request.full_url == (
        "http://gateway:8000/connector-jobs/run-ready?"
        "max_jobs=1&kind=cron&project_id=project_demo"
    )
    assert request.get_method() == "POST"
    assert request.get_header("X-synarch-trace-id") == "trace_connector_worker"
    assert request.get_header("X-synarch-connector-job-worker-id") == (
        "connector-worker-test"
    )
    assert result["connector_jobs"]["worker_id"] == "connector-worker-test"
    assert result["connector_jobs"]["stop_reason"] == "no_ready_connector_job"
    assert result["connector_jobs"]["run_count"] == 0


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
            "connector_jobs": {
                "worker_id": kwargs["worker_id"],
                "gateway_url": kwargs["gateway_url"],
                "project_id": kwargs["project_id"],
                "service_id": kwargs["service_id"],
                "owner_agent_id": kwargs["owner_agent_id"],
                "kind": kwargs["kind"],
                "max_jobs": kwargs["max_jobs"],
                "trace_id": kwargs["trace_id"],
                "stop_reason": "no_ready_connector_job",
                "run_count": 0,
                "completed_run_count": 0,
                "failed_run_count": 0,
                "skipped_run_count": 0,
            },
            "result": {"runs": []},
        }

    monkeypatch.setattr(connector_job_worker, "run_connector_job_tick", fake_tick)
    monkeypatch.setattr("synarch_gateway.connector_job_worker.time.sleep", lambda seconds: None)

    connector_job_worker.run_loop(
        argparse.Namespace(
            gateway_url="http://gateway:8000",
            worker_id="connector-worker-test",
            project_id=None,
            service_id=None,
            owner_agent_id=None,
            kind="cron",
            max_jobs=1,
            trace_id="trace_static",
            timeout_seconds=1.0,
            loop=True,
            interval_seconds=1.0,
            max_ticks=2,
        )
    )

    lines = [json.loads(line) for line in BytesIO(capsys.readouterr().out.encode())]
    assert lines[0]["connector_jobs"]["status"] == "failed"
    assert lines[0]["error"]["type"] == "TimeoutError"
    assert lines[1]["connector_jobs"]["status"] == "completed"
    assert lines[1]["connector_jobs"]["tick"] == 2
