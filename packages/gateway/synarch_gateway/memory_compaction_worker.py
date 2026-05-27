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
DEFAULT_MAX_SCOPES = 20
DEFAULT_MAX_SOURCE_ITEMS = 20
DEFAULT_MAX_SUMMARY_CHARS = 1200
DEFAULT_MIN_SOURCE_TOKENS = 1200
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_WORKER_ID = "memory-compaction-worker"


def memory_compaction_payload(
    *,
    scope: str,
    project_id: str | None,
    agent_id: str | None,
    min_source_tokens: int,
    max_source_items: int,
    max_summary_chars: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scope": scope,
        "status": "proposed",
        "min_source_tokens": min_source_tokens,
        "max_source_items": max_source_items,
        "max_summary_chars": max_summary_chars,
    }
    if project_id:
        payload["project_id"] = project_id
    if agent_id:
        payload["agent_id"] = agent_id
    return payload


def memory_compaction_plan_payload(
    *,
    project_id: str | None,
    agent_id: str | None,
    min_source_tokens: int,
    max_source_items: int,
    max_summary_chars: int,
    max_scopes: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "proposed",
        "min_source_tokens": min_source_tokens,
        "max_source_items": max_source_items,
        "max_summary_chars": max_summary_chars,
        "max_scopes": max_scopes,
    }
    if project_id:
        payload["project_id"] = project_id
    if agent_id:
        payload["agent_id"] = agent_id
    return payload


def run_memory_compaction_tick(
    *,
    gateway_url: str,
    scope: str,
    project_id: str | None,
    agent_id: str | None,
    min_source_tokens: int,
    max_source_items: int,
    max_summary_chars: int,
    trace_id: str | None,
    timeout_seconds: float,
    worker_id: str = DEFAULT_WORKER_ID,
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_memory_compaction_{uuid4().hex[:12]}"
    payload = memory_compaction_payload(
        scope=scope,
        project_id=project_id,
        agent_id=agent_id,
        min_source_tokens=min_source_tokens,
        max_source_items=max_source_items,
        max_summary_chars=max_summary_chars,
    )
    request = Request(
        f"{gateway_url.rstrip('/')}/memory-items/compact-if-needed",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Synarch-Trace-Id": request_trace_id,
            "X-Synarch-Memory-Compaction-Worker-Id": worker_id,
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": worker_id,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    return {
        "memory_compaction": {
            "worker_id": worker_id,
            "gateway_url": gateway_url,
            "scope": scope,
            "project_id": project_id,
            "agent_id": agent_id,
            "trace_id": request_trace_id,
            **memory_compaction_summary(response_payload),
        },
        "result": response_payload,
    }


def run_memory_compaction_plan_tick(
    *,
    gateway_url: str,
    project_id: str | None,
    agent_id: str | None,
    min_source_tokens: int,
    max_source_items: int,
    max_summary_chars: int,
    max_scopes: int,
    trace_id: str | None,
    timeout_seconds: float,
    worker_id: str = DEFAULT_WORKER_ID,
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_memory_compaction_{uuid4().hex[:12]}"
    payload = memory_compaction_plan_payload(
        project_id=project_id,
        agent_id=agent_id,
        min_source_tokens=min_source_tokens,
        max_source_items=max_source_items,
        max_summary_chars=max_summary_chars,
        max_scopes=max_scopes,
    )
    request = Request(
        f"{gateway_url.rstrip('/')}/memory-items/compaction-plan",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Synarch-Trace-Id": request_trace_id,
            "X-Synarch-Memory-Compaction-Worker-Id": worker_id,
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": worker_id,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        plan_payload = json.loads(response.read().decode("utf-8"))

    executions = []
    for item in planned_items(plan_payload):
        executions.append(
            run_memory_compaction_tick(
                gateway_url=gateway_url,
                scope=item["scope"],
                project_id=item.get("project_id"),
                agent_id=item.get("agent_id"),
                min_source_tokens=min_source_tokens,
                max_source_items=max_source_items,
                max_summary_chars=max_summary_chars,
                trace_id=request_trace_id,
                timeout_seconds=timeout_seconds,
                worker_id=worker_id,
            )
        )

    return {
        "memory_compaction": {
            "worker_id": worker_id,
            "gateway_url": gateway_url,
            "scope": None,
            "project_id": project_id,
            "agent_id": agent_id,
            "trace_id": request_trace_id,
            **memory_compaction_plan_summary(plan_payload, executions),
        },
        "plan": plan_payload,
        "executions": executions,
    }


def memory_compaction_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "compaction_needed": False,
            "reason": None,
            "source_count": 0,
            "source_tokens": 0,
            "compacted_memory_id": None,
            "existing_compacted_memory_id": None,
        }
    compaction = payload.get("compaction")
    compacted_item = (
        compaction.get("compacted_item")
        if isinstance(compaction, dict)
        else None
    )
    existing_compacted_item = payload.get("existing_compacted_item")
    return {
        "compaction_needed": bool(payload.get("compaction_needed")),
        "reason": payload.get("reason"),
        "source_count": int(payload.get("source_count") or 0),
        "source_tokens": int(payload.get("source_tokens") or 0),
        "compacted_memory_id": memory_item_id(compacted_item),
        "existing_compacted_memory_id": memory_item_id(existing_compacted_item),
    }


def memory_item_id(value: Any) -> str | None:
    if isinstance(value, dict):
        item_id = value.get("id")
        return item_id if isinstance(item_id, str) else None
    return None


def planned_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def memory_compaction_plan_summary(
    payload: Any,
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "planned_scope_count": 0,
            "executed_scope_count": 0,
            "compacted_scope_count": 0,
            "existing_scope_count": 0,
            "inspected_scope_count": 0,
        }
    execution_summaries = [
        execution.get("memory_compaction", {})
        for execution in executions
        if isinstance(execution.get("memory_compaction"), dict)
    ]
    return {
        "planned_scope_count": int(payload.get("planned_scope_count") or 0),
        "executed_scope_count": len(executions),
        "compacted_scope_count": sum(
            1
            for summary in execution_summaries
            if summary.get("compacted_memory_id") is not None
        ),
        "existing_scope_count": sum(
            1
            for summary in execution_summaries
            if summary.get("existing_compacted_memory_id") is not None
        ),
        "inspected_scope_count": int(payload.get("inspected_scope_count") or 0),
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
        description="Run Synarch memory compaction policy ticks through the gateway."
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
        default=os.getenv("SYNARCH_MEMORY_COMPACTION_WORKER_ID", DEFAULT_WORKER_ID),
    )
    argument_parser.add_argument(
        "--scope",
        default=os.getenv("SYNARCH_MEMORY_COMPACTION_SCOPE") or None,
    )
    argument_parser.add_argument(
        "--project-id",
        default=os.getenv("SYNARCH_MEMORY_COMPACTION_PROJECT_ID") or None,
    )
    argument_parser.add_argument(
        "--agent-id",
        default=os.getenv("SYNARCH_MEMORY_COMPACTION_AGENT_ID") or None,
    )
    argument_parser.add_argument(
        "--min-source-tokens",
        type=positive_int,
        default=positive_int(
            os.getenv(
                "SYNARCH_MEMORY_COMPACTION_MIN_SOURCE_TOKENS",
                str(DEFAULT_MIN_SOURCE_TOKENS),
            )
        ),
    )
    argument_parser.add_argument(
        "--max-source-items",
        type=positive_int,
        default=positive_int(
            os.getenv(
                "SYNARCH_MEMORY_COMPACTION_MAX_SOURCE_ITEMS",
                str(DEFAULT_MAX_SOURCE_ITEMS),
            )
        ),
    )
    argument_parser.add_argument(
        "--max-summary-chars",
        type=positive_int,
        default=positive_int(
            os.getenv(
                "SYNARCH_MEMORY_COMPACTION_MAX_SUMMARY_CHARS",
                str(DEFAULT_MAX_SUMMARY_CHARS),
            )
        ),
    )
    argument_parser.add_argument(
        "--max-scopes",
        type=positive_int,
        default=positive_int(
            os.getenv(
                "SYNARCH_MEMORY_COMPACTION_MAX_SCOPES",
                str(DEFAULT_MAX_SCOPES),
            )
        ),
    )
    argument_parser.add_argument(
        "--trace-id",
        default=os.getenv("SYNARCH_MEMORY_COMPACTION_TRACE_ID") or None,
    )
    argument_parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv(
                "SYNARCH_MEMORY_COMPACTION_TIMEOUT_SECONDS",
                str(DEFAULT_TIMEOUT_SECONDS),
            )
        ),
    )
    argument_parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running memory compaction ticks until interrupted or max ticks is reached.",
    )
    argument_parser.add_argument(
        "--interval-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv(
                "SYNARCH_MEMORY_COMPACTION_INTERVAL_SECONDS",
                str(DEFAULT_INTERVAL_SECONDS),
            )
        ),
    )
    argument_parser.add_argument(
        "--max-ticks",
        type=optional_positive_int,
        default=optional_positive_int(os.getenv("SYNARCH_MEMORY_COMPACTION_MAX_TICKS")),
        help="Maximum loop iterations. Omit for an unbounded loop.",
    )
    return argument_parser


def run_loop(args: argparse.Namespace) -> None:
    tick_count = 0
    while True:
        tick_count += 1
        started_at = datetime.now(UTC)
        trace_id = args.trace_id or f"trace_memory_compaction_{uuid4().hex[:12]}"
        try:
            if args.scope:
                result = run_memory_compaction_tick(
                    gateway_url=args.gateway_url,
                    scope=args.scope,
                    project_id=args.project_id,
                    agent_id=args.agent_id,
                    min_source_tokens=args.min_source_tokens,
                    max_source_items=args.max_source_items,
                    max_summary_chars=args.max_summary_chars,
                    trace_id=trace_id,
                    timeout_seconds=args.timeout_seconds,
                    worker_id=args.worker_id,
                )
            else:
                result = run_memory_compaction_plan_tick(
                    gateway_url=args.gateway_url,
                    project_id=args.project_id,
                    agent_id=args.agent_id,
                    min_source_tokens=args.min_source_tokens,
                    max_source_items=args.max_source_items,
                    max_summary_chars=args.max_summary_chars,
                    max_scopes=args.max_scopes,
                    trace_id=trace_id,
                    timeout_seconds=args.timeout_seconds,
                    worker_id=args.worker_id,
                )
            result["memory_compaction"]["status"] = "completed"
        except Exception as error:
            if not args.loop:
                raise
            result = {
                "memory_compaction": {
                    "worker_id": args.worker_id,
                    "gateway_url": args.gateway_url,
                    "scope": args.scope,
                    "project_id": args.project_id,
                    "agent_id": args.agent_id,
                    "trace_id": trace_id,
                    "status": "failed",
                },
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

        finished_at = datetime.now(UTC)
        result["memory_compaction"]["tick"] = tick_count
        result["memory_compaction"]["started_at"] = started_at.isoformat()
        result["memory_compaction"]["finished_at"] = finished_at.isoformat()
        result["memory_compaction"]["duration_seconds"] = (
            finished_at - started_at
        ).total_seconds()
        try:
            result["worker_heartbeat"] = record_worker_heartbeat(
                state_service_url=getattr(args, "state_service_url", DEFAULT_STATE_SERVICE_URL),
                worker_id=args.worker_id,
                worker_kind="memory_compaction",
                status=result["memory_compaction"]["status"],
                target=args.scope or args.project_id or args.agent_id or "all",
                last_tick_result=result["memory_compaction"],
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
