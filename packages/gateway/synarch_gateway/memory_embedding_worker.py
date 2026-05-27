from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

from synarch_gateway.worker_heartbeat import DEFAULT_STATE_SERVICE_URL, record_worker_heartbeat

DEFAULT_GATEWAY_URL = "http://localhost:8000"
DEFAULT_INTERVAL_SECONDS = 300.0
DEFAULT_MAX_ITEMS = 10
DEFAULT_STATUS = "approved"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_WORKER_ID = "memory-embedding-worker"


def memory_embedding_backfill_payload(
    *,
    project_id: str | None,
    agent_id: str | None,
    scope: str | None,
    status: str,
    max_items: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "max_items": max_items,
    }
    if project_id:
        payload["project_id"] = project_id
    if agent_id:
        payload["agent_id"] = agent_id
    if scope:
        payload["scope"] = scope
    return payload


def run_memory_embedding_backfill_tick(
    *,
    gateway_url: str,
    project_id: str | None,
    agent_id: str | None,
    scope: str | None,
    status: str,
    max_items: int,
    trace_id: str | None,
    timeout_seconds: float,
    worker_id: str = DEFAULT_WORKER_ID,
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_memory_embedding_{uuid4().hex[:12]}"
    payload = memory_embedding_backfill_payload(
        project_id=project_id,
        agent_id=agent_id,
        scope=scope,
        status=status,
        max_items=max_items,
    )
    request = Request(
        f"{gateway_url.rstrip('/')}/memory-items/embedding-backfill",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Synarch-Trace-Id": request_trace_id,
            "X-Synarch-Memory-Embedding-Worker-Id": worker_id,
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": worker_id,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    return {
        "memory_embedding_backfill": {
            "worker_id": worker_id,
            "gateway_url": gateway_url,
            "scope": scope,
            "project_id": project_id,
            "agent_id": agent_id,
            "memory_status": status,
            "max_items": max_items,
            "trace_id": request_trace_id,
            **memory_embedding_backfill_summary(response_payload),
        },
        "result": response_payload,
    }


def memory_embedding_backfill_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "inspected_count": 0,
            "backfilled_count": 0,
            "skipped_count": 0,
            "memory_ids": [],
        }
    memory_ids = payload.get("memory_ids", [])
    return {
        "inspected_count": int(payload.get("inspected_count") or 0),
        "backfilled_count": int(payload.get("backfilled_count") or 0),
        "skipped_count": int(payload.get("skipped_count") or 0),
        "memory_ids": memory_ids if isinstance(memory_ids, list) else [],
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
        description="Run Synarch memory embedding backfill ticks through the gateway."
    )
    argument_parser.add_argument(
        "--gateway-url",
        default=os.getenv("GATEWAY_URL", DEFAULT_GATEWAY_URL),
    )
    argument_parser.add_argument(
        "--state-service-url",
        default=os.getenv("STATE_SERVICE_URL", DEFAULT_STATE_SERVICE_URL),
    )
    argument_parser.add_argument(
        "--worker-id",
        default=os.getenv("SYNARCH_MEMORY_EMBEDDING_WORKER_ID", DEFAULT_WORKER_ID),
    )
    argument_parser.add_argument(
        "--project-id",
        default=os.getenv("SYNARCH_MEMORY_EMBEDDING_PROJECT_ID") or None,
    )
    argument_parser.add_argument(
        "--agent-id",
        default=os.getenv("SYNARCH_MEMORY_EMBEDDING_AGENT_ID") or None,
    )
    argument_parser.add_argument(
        "--scope",
        default=os.getenv("SYNARCH_MEMORY_EMBEDDING_SCOPE") or None,
    )
    argument_parser.add_argument(
        "--status",
        default=os.getenv("SYNARCH_MEMORY_EMBEDDING_STATUS", DEFAULT_STATUS),
    )
    argument_parser.add_argument(
        "--max-items",
        type=positive_int,
        default=positive_int(
            os.getenv("SYNARCH_MEMORY_EMBEDDING_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))
        ),
    )
    argument_parser.add_argument(
        "--trace-id",
        default=os.getenv("SYNARCH_MEMORY_EMBEDDING_TRACE_ID") or None,
    )
    argument_parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv(
                "SYNARCH_MEMORY_EMBEDDING_TIMEOUT_SECONDS",
                str(DEFAULT_TIMEOUT_SECONDS),
            )
        ),
    )
    argument_parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running memory embedding backfill ticks until interrupted.",
    )
    argument_parser.add_argument(
        "--interval-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv(
                "SYNARCH_MEMORY_EMBEDDING_INTERVAL_SECONDS",
                str(DEFAULT_INTERVAL_SECONDS),
            )
        ),
    )
    argument_parser.add_argument(
        "--max-ticks",
        type=optional_positive_int,
        default=optional_positive_int(os.getenv("SYNARCH_MEMORY_EMBEDDING_MAX_TICKS")),
        help="Maximum loop iterations. Omit for an unbounded loop.",
    )
    return argument_parser


def run_loop(args: argparse.Namespace) -> None:
    tick_count = 0
    while True:
        tick_count += 1
        started_at = datetime.now(UTC)
        trace_id = args.trace_id or f"trace_memory_embedding_{uuid4().hex[:12]}"
        try:
            result = run_memory_embedding_backfill_tick(
                gateway_url=args.gateway_url,
                project_id=args.project_id,
                agent_id=args.agent_id,
                scope=args.scope,
                status=args.status,
                max_items=args.max_items,
                trace_id=trace_id,
                timeout_seconds=args.timeout_seconds,
                worker_id=args.worker_id,
            )
            result["memory_embedding_backfill"]["status"] = "completed"
        except Exception as error:
            if not args.loop:
                raise
            result = {
                "memory_embedding_backfill": {
                    "worker_id": args.worker_id,
                    "gateway_url": args.gateway_url,
                    "scope": args.scope,
                    "project_id": args.project_id,
                    "agent_id": args.agent_id,
                    "memory_status": args.status,
                    "status": "failed",
                    "trace_id": trace_id,
                },
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

        finished_at = datetime.now(UTC)
        result["memory_embedding_backfill"]["tick"] = tick_count
        result["memory_embedding_backfill"]["started_at"] = started_at.isoformat()
        result["memory_embedding_backfill"]["finished_at"] = finished_at.isoformat()
        result["memory_embedding_backfill"]["duration_seconds"] = (
            finished_at - started_at
        ).total_seconds()
        try:
            result["worker_heartbeat"] = record_worker_heartbeat(
                state_service_url=getattr(args, "state_service_url", DEFAULT_STATE_SERVICE_URL),
                worker_id=args.worker_id,
                worker_kind="memory_embedding",
                status=result["memory_embedding_backfill"]["status"],
                target=args.scope or args.project_id or args.agent_id or args.status,
                last_tick_result=result["memory_embedding_backfill"],
                last_error=result.get("error", {}).get("message")
                if isinstance(result.get("error"), dict)
                else None,
                trace_id=trace_id,
                timeout_seconds=args.timeout_seconds,
            )
        except Exception as heartbeat_error:
            result["worker_heartbeat_error"] = {
                "type": type(heartbeat_error).__name__,
                "message": str(heartbeat_error),
            }
        print(json.dumps(result, separators=(",", ":")), flush=True)
        if not args.loop or (args.max_ticks is not None and tick_count >= args.max_ticks):
            return
        time.sleep(args.interval_seconds)


def main() -> None:
    run_loop(parser().parse_args())


if __name__ == "__main__":
    main()
