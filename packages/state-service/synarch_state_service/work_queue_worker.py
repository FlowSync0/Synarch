from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from typing import Any, cast
from urllib.request import Request, urlopen
from uuid import uuid4

DEFAULT_STATE_SERVICE_URL = "http://localhost:8020"
DEFAULT_QUEUE_NAME = "default"
DEFAULT_WORKER_ID = "work-queue-worker"
DEFAULT_LIMIT = 5
DEFAULT_LEASE_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_INTERVAL_SECONDS = 30.0


def state_url(state_service_url: str, path: str) -> str:
    return f"{state_service_url.rstrip('/')}{path}"


def post_json(
    url: str,
    payload: dict[str, Any] | None,
    *,
    timeout_seconds: float,
    headers: dict[str, str],
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            **headers,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload_data = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload_data, dict):
        raise ValueError("State-service response must be a JSON object")
    return cast(dict[str, Any], payload_data)


def execute_work_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Work item payload must be an object")
    action = payload.get("action", "noop")
    if action in {None, "noop"}:
        return {
            "action": "noop",
            "message": payload.get("message"),
        }
    if action == "log":
        return {
            "action": "log",
            "message": str(payload.get("message", "")),
        }
    raise ValueError(f"Unsupported work queue action: {action}")


def run_work_queue_tick(
    *,
    state_service_url: str,
    queue_name: str,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    trace_id: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_work_queue_{uuid4().hex[:12]}"
    headers = {
        "X-Synarch-Trace-Id": request_trace_id,
        "X-Synarch-Work-Queue-Worker-Id": worker_id,
    }
    recovery = post_json(
        state_url(state_service_url, "/work-queue/recover-expired-leases"),
        None,
        timeout_seconds=timeout_seconds,
        headers=headers,
    )
    claim = post_json(
        state_url(state_service_url, "/work-queue/claim"),
        {
            "queue_name": queue_name,
            "worker_id": worker_id,
            "limit": limit,
            "lease_seconds": lease_seconds,
        },
        timeout_seconds=timeout_seconds,
        headers=headers,
    )
    claimed_items = claim.get("claimed_items", [])
    if not isinstance(claimed_items, list):
        claimed_items = []

    completed_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    for item in claimed_items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        item_id = item["id"]
        try:
            result = execute_work_item(item)
            completed = post_json(
                state_url(state_service_url, f"/work-queue/items/{item_id}/complete"),
                {
                    "worker_id": worker_id,
                    "result": result,
                },
                timeout_seconds=timeout_seconds,
                headers=headers,
            )
            completed_items.append(completed)
        except Exception as error:
            failed = post_json(
                state_url(state_service_url, f"/work-queue/items/{item_id}/fail"),
                {
                    "worker_id": worker_id,
                    "error": str(error),
                    "dead_letter": isinstance(error, ValueError),
                },
                timeout_seconds=timeout_seconds,
                headers=headers,
            )
            failed_items.append(failed)

    return {
        "work_queue": {
            "worker_id": worker_id,
            "state_service_url": state_service_url,
            "queue_name": queue_name,
            "limit": limit,
            "lease_seconds": lease_seconds,
            "trace_id": request_trace_id,
            "recovered_item_count": len(recovery.get("recovered_item_ids", [])),
            "dead_lettered_recovery_count": len(
                recovery.get("dead_lettered_item_ids", [])
            ),
            "claimed_count": len(claimed_items),
            "completed_count": len(completed_items),
            "failed_count": len(failed_items),
        },
        "recovery": recovery,
        "claim": claim,
        "completed_items": completed_items,
        "failed_items": failed_items,
    }


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def optional_positive_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return positive_int(value)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Run bounded Synarch durable work queue ticks through state-service."
    )
    argument_parser.add_argument(
        "--state-service-url",
        default=os.getenv("STATE_SERVICE_URL", DEFAULT_STATE_SERVICE_URL),
    )
    argument_parser.add_argument(
        "--queue-name",
        default=os.getenv("SYNARCH_WORK_QUEUE_NAME", DEFAULT_QUEUE_NAME),
    )
    argument_parser.add_argument(
        "--worker-id",
        default=os.getenv("SYNARCH_WORK_QUEUE_WORKER_ID", DEFAULT_WORKER_ID),
    )
    argument_parser.add_argument(
        "--limit",
        type=positive_int,
        default=positive_int(os.getenv("SYNARCH_WORK_QUEUE_MAX_ITEMS", str(DEFAULT_LIMIT))),
    )
    argument_parser.add_argument(
        "--lease-seconds",
        type=positive_int,
        default=positive_int(
            os.getenv("SYNARCH_WORK_QUEUE_LEASE_SECONDS", str(DEFAULT_LEASE_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--trace-id",
        default=os.getenv("SYNARCH_WORK_QUEUE_TRACE_ID") or None,
    )
    argument_parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv("SYNARCH_WORK_QUEUE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running work queue ticks until interrupted or max ticks is reached.",
    )
    argument_parser.add_argument(
        "--interval-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv("SYNARCH_WORK_QUEUE_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--max-ticks",
        type=optional_positive_int,
        default=optional_positive_int(os.getenv("SYNARCH_WORK_QUEUE_MAX_TICKS")),
        help="Maximum loop iterations. Omit for an unbounded loop.",
    )
    return argument_parser


def run_loop(args: argparse.Namespace) -> None:
    tick_count = 0
    while True:
        tick_count += 1
        started_at = datetime.now(UTC)
        trace_id = args.trace_id or f"trace_work_queue_{uuid4().hex[:12]}"
        try:
            result = run_work_queue_tick(
                state_service_url=args.state_service_url,
                queue_name=args.queue_name,
                worker_id=args.worker_id,
                limit=args.limit,
                lease_seconds=args.lease_seconds,
                trace_id=trace_id,
                timeout_seconds=args.timeout_seconds,
            )
            result["work_queue"]["tick"] = tick_count
            result["work_queue"]["started_at"] = started_at.isoformat()
            result["work_queue"]["status"] = "completed"
            print(json.dumps(result, sort_keys=True), flush=True)
        except Exception as error:
            print(
                json.dumps(
                    {
                        "work_queue": {
                            "worker_id": args.worker_id,
                            "state_service_url": args.state_service_url,
                            "queue_name": args.queue_name,
                            "trace_id": trace_id,
                            "tick": tick_count,
                            "started_at": started_at.isoformat(),
                            "status": "failed",
                        },
                        "error": {
                            "type": type(error).__name__,
                            "message": str(error),
                        },
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        if not args.loop:
            return
        if args.max_ticks is not None and tick_count >= args.max_ticks:
            return
        time.sleep(args.interval_seconds)


def main() -> None:
    run_loop(parser().parse_args())


if __name__ == "__main__":
    main()
