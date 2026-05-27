import argparse
import json
from io import BytesIO
from typing import cast
from urllib.request import Request

import pytest

import synarch_state_service.work_queue_worker as work_queue_worker


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
    return cast(dict[str, object], json.loads(data.decode("utf-8")))


def test_run_work_queue_tick_claims_and_completes_supported_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        assert timeout == 9.0
        if request.full_url.endswith("/work-queue/recover-expired-leases"):
            return FakeResponse(
                {
                    "recovered_item_ids": [],
                    "dead_lettered_item_ids": [],
                    "inspected_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/claim"):
            assert request_payload(request)["queue_name"] == "reminders"
            return FakeResponse(
                {
                    "queue_name": "reminders",
                    "worker_id": "worker-test",
                    "claimed_items": [
                        {
                            "id": "work-log-1",
                            "queue_name": "reminders",
                            "payload": {"action": "log", "message": "hello"},
                        }
                    ],
                    "claimed_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/items/work-log-1/complete"):
            assert request_payload(request)["result"] == {
                "action": "log",
                "message": "hello",
            }
            return FakeResponse({"id": "work-log-1", "status": "completed"})
        raise AssertionError(f"Unexpected request: {request.full_url}")

    monkeypatch.setattr(work_queue_worker, "urlopen", fake_urlopen)

    result = work_queue_worker.run_work_queue_tick(
        state_service_url="http://state-service:8020",
        queue_name="reminders",
        worker_id="worker-test",
        limit=1,
        lease_seconds=30,
        trace_id="trace_work_queue_test",
        timeout_seconds=9.0,
    )

    assert [request.get_method() for request in seen_requests] == ["POST", "POST", "POST"]
    assert seen_requests[0].get_header("X-synarch-trace-id") == "trace_work_queue_test"
    assert result["work_queue"]["claimed_count"] == 1
    assert result["work_queue"]["completed_count"] == 1
    assert result["work_queue"]["failed_count"] == 0


def test_run_work_queue_tick_emits_project_reminder_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        seen_requests.append(request)
        if request.full_url.endswith("/work-queue/recover-expired-leases"):
            return FakeResponse(
                {
                    "recovered_item_ids": [],
                    "dead_lettered_item_ids": [],
                    "inspected_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/claim"):
            return FakeResponse(
                {
                    "queue_name": "reminders",
                    "worker_id": "worker-test",
                    "claimed_items": [
                        {
                            "id": "work-reminder-1",
                            "queue_name": "reminders",
                            "payload": {
                                "action": "project.reminder.emit",
                                "project_id": "project_demo",
                                "message": "Relancer le fournisseur mardi matin.",
                            },
                        }
                    ],
                    "claimed_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/events"):
            assert request_payload(request) == {
                "type": "project.reminder",
                "target": "project_demo",
                "payload": {
                    "project_id": "project_demo",
                    "message": "Relancer le fournisseur mardi matin.",
                    "source_work_queue_item_id": "work-reminder-1",
                },
                "trace_id": "trace_work_queue_reminder",
            }
            return FakeResponse(
                {
                    "id": "event-reminder-1",
                    "type": "project.reminder",
                    "target": "project_demo",
                    "payload": {
                        "project_id": "project_demo",
                        "message": "Relancer le fournisseur mardi matin.",
                        "source_work_queue_item_id": "work-reminder-1",
                    },
                    "trace_id": "trace_work_queue_reminder",
                }
            )
        if request.full_url.endswith("/work-queue/items/work-reminder-1/complete"):
            assert request_payload(request)["result"] == {
                "action": "project.reminder.emit",
                "project_id": "project_demo",
                "message": "Relancer le fournisseur mardi matin.",
                "event_id": "event-reminder-1",
                "event_type": "project.reminder",
                "emitted": True,
            }
            return FakeResponse({"id": "work-reminder-1", "status": "completed"})
        raise AssertionError(f"Unexpected request: {request.full_url}")

    monkeypatch.setattr(work_queue_worker, "urlopen", fake_urlopen)

    result = work_queue_worker.run_work_queue_tick(
        state_service_url="http://state-service:8020",
        queue_name="reminders",
        worker_id="worker-test",
        limit=1,
        lease_seconds=30,
        trace_id="trace_work_queue_reminder",
        timeout_seconds=9.0,
    )

    assert [request.full_url for request in seen_requests] == [
        "http://state-service:8020/work-queue/recover-expired-leases",
        "http://state-service:8020/work-queue/claim",
        "http://state-service:8020/events",
        "http://state-service:8020/work-queue/items/work-reminder-1/complete",
    ]
    assert result["work_queue"]["completed_count"] == 1
    assert result["work_queue"]["failed_count"] == 0


def test_run_work_queue_tick_dead_letters_invalid_project_reminder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_payloads: list[dict[str, object]] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        if request.full_url.endswith("/work-queue/recover-expired-leases"):
            return FakeResponse(
                {
                    "recovered_item_ids": [],
                    "dead_lettered_item_ids": [],
                    "inspected_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/claim"):
            return FakeResponse(
                {
                    "queue_name": "reminders",
                    "worker_id": "worker-test",
                    "claimed_items": [
                        {
                            "id": "work-reminder-invalid",
                            "queue_name": "reminders",
                            "payload": {
                                "action": "project.reminder.emit",
                                "project_id": "project_demo",
                            },
                        }
                    ],
                    "claimed_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/items/work-reminder-invalid/fail"):
            failed_payloads.append(request_payload(request))
            return FakeResponse({"id": "work-reminder-invalid", "status": "dead_lettered"})
        raise AssertionError(f"Unexpected request: {request.full_url}")

    monkeypatch.setattr(work_queue_worker, "urlopen", fake_urlopen)

    result = work_queue_worker.run_work_queue_tick(
        state_service_url="http://state-service:8020",
        queue_name="reminders",
        worker_id="worker-test",
        limit=1,
        lease_seconds=30,
        trace_id="trace_work_queue_invalid_reminder",
        timeout_seconds=9.0,
    )

    assert result["work_queue"]["completed_count"] == 0
    assert result["work_queue"]["failed_count"] == 1
    assert failed_payloads[0]["dead_letter"] is True
    assert "project.reminder.emit requires non-empty message" in str(
        failed_payloads[0]["error"]
    )


def test_run_work_queue_tick_fails_unsupported_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_payloads: list[dict[str, object]] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        if request.full_url.endswith("/work-queue/recover-expired-leases"):
            return FakeResponse(
                {
                    "recovered_item_ids": [],
                    "dead_lettered_item_ids": [],
                    "inspected_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/claim"):
            return FakeResponse(
                {
                    "queue_name": "pdf-ingestion",
                    "worker_id": "worker-test",
                    "claimed_items": [
                        {
                            "id": "work-pdf-1",
                            "queue_name": "pdf-ingestion",
                            "payload": {"action": "extract_pdf"},
                        }
                    ],
                    "claimed_at": "2026-01-01T00:00:00Z",
                }
            )
        if request.full_url.endswith("/work-queue/items/work-pdf-1/fail"):
            failed_payloads.append(request_payload(request))
            return FakeResponse({"id": "work-pdf-1", "status": "dead_lettered"})
        raise AssertionError(f"Unexpected request: {request.full_url}")

    monkeypatch.setattr(work_queue_worker, "urlopen", fake_urlopen)

    result = work_queue_worker.run_work_queue_tick(
        state_service_url="http://state-service:8020",
        queue_name="pdf-ingestion",
        worker_id="worker-test",
        limit=1,
        lease_seconds=30,
        trace_id="trace_work_queue_unsupported",
        timeout_seconds=9.0,
    )

    assert result["work_queue"]["completed_count"] == 0
    assert result["work_queue"]["failed_count"] == 1
    assert failed_payloads[0]["dead_letter"] is True
    assert "Unsupported work queue action" in str(failed_payloads[0]["error"])


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
            raise TimeoutError("temporary state timeout")
        return {
            "work_queue": {
                "worker_id": kwargs["worker_id"],
                "state_service_url": kwargs["state_service_url"],
                "queue_name": kwargs["queue_name"],
                "limit": kwargs["limit"],
                "lease_seconds": kwargs["lease_seconds"],
                "trace_id": kwargs["trace_id"],
                "recovered_item_count": 0,
                "dead_lettered_recovery_count": 0,
                "claimed_count": 0,
                "completed_count": 0,
                "failed_count": 0,
            },
            "recovery": {},
            "claim": {"claimed_items": []},
            "completed_items": [],
            "failed_items": [],
        }

    def fake_heartbeat(**kwargs: object) -> dict[str, object]:
        recorded_heartbeats.append(kwargs)
        return {
            "id": kwargs["worker_id"],
            "status": kwargs["status"],
            "heartbeat_count": len(recorded_heartbeats),
        }

    monkeypatch.setattr(work_queue_worker, "run_work_queue_tick", fake_tick)
    monkeypatch.setattr(work_queue_worker, "record_worker_heartbeat", fake_heartbeat)
    monkeypatch.setattr(
        "synarch_state_service.work_queue_worker.time.sleep",
        lambda seconds: None,
    )

    work_queue_worker.run_loop(
        argparse.Namespace(
            state_service_url="http://state-service:8020",
            queue_name="reminders",
            worker_id="worker-test",
            limit=1,
            lease_seconds=30,
            trace_id="trace_static",
            timeout_seconds=1.0,
            loop=True,
            interval_seconds=1.0,
            max_ticks=2,
        )
    )

    lines = [json.loads(line) for line in BytesIO(capsys.readouterr().out.encode())]
    assert lines[0]["work_queue"]["status"] == "failed"
    assert lines[0]["error"]["type"] == "TimeoutError"
    assert lines[0]["worker_heartbeat"]["status"] == "failed"
    assert lines[1]["work_queue"]["status"] == "completed"
    assert lines[1]["work_queue"]["tick"] == 2
    assert lines[1]["worker_heartbeat"]["status"] == "completed"
    assert [heartbeat["status"] for heartbeat in recorded_heartbeats] == [
        "failed",
        "completed",
    ]
    last_tick_result = cast(dict[str, object], recorded_heartbeats[1]["last_tick_result"])
    assert last_tick_result["claimed_count"] == 0
