from __future__ import annotations

import json
from typing import Any, cast
from urllib.request import Request, urlopen

DEFAULT_STATE_SERVICE_URL = "http://localhost:8020"


def state_url(state_service_url: str, path: str) -> str:
    return f"{state_service_url.rstrip('/')}{path}"


def record_worker_heartbeat(
    *,
    state_service_url: str,
    worker_id: str,
    worker_kind: str,
    status: str,
    target: str | None,
    last_tick_result: dict[str, Any],
    last_error: str | None,
    trace_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    request = Request(
        state_url(state_service_url, f"/worker-heartbeats/{worker_id}"),
        data=json.dumps(
            {
                "worker_kind": worker_kind,
                "status": status,
                "target": target,
                "last_tick_result": last_tick_result,
                "last_error": last_error,
            }
        ).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Synarch-Trace-Id": trace_id,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("State-service heartbeat response must be a JSON object")
    return cast(dict[str, Any], payload)
