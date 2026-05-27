from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from synarch_gateway.worker_heartbeat import DEFAULT_STATE_SERVICE_URL, record_worker_heartbeat

DEFAULT_GATEWAY_URL = "http://localhost:8000"
DEFAULT_MAX_TASKS = 3
DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_WORKER_ID = "scheduler-worker"


def build_run_ready_url(
    gateway_url: str,
    *,
    max_tasks: int,
    project_id: str | None = None,
) -> str:
    params: dict[str, str] = {"max_tasks": str(max_tasks)}
    if project_id:
        params["project_id"] = project_id
    return f"{gateway_url.rstrip('/')}/tasks/run-ready?{urlencode(params)}"


def run_scheduler_tick(
    *,
    gateway_url: str,
    max_tasks: int,
    project_id: str | None,
    trace_id: str | None,
    timeout_seconds: float,
    worker_id: str = DEFAULT_WORKER_ID,
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_scheduler_{uuid4().hex[:12]}"
    request = Request(
        build_run_ready_url(gateway_url, max_tasks=max_tasks, project_id=project_id),
        method="POST",
        headers={
            "X-Synarch-Trace-Id": request_trace_id,
            "X-Synarch-Scheduler-Worker-Id": worker_id,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "scheduler": {
            "worker_id": worker_id,
            "gateway_url": gateway_url,
            "project_id": project_id,
            "max_tasks": max_tasks,
            "trace_id": request_trace_id,
            **scheduler_result_summary(payload),
        },
        "result": payload,
    }


def scheduler_result_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "stop_reason": None,
            "run_count": 0,
            "tool_result_count": 0,
            "failed_tool_result_count": 0,
            "failed_tool_names": [],
            "failed_tool_errors": [],
            "total_cost": 0.0,
        }
    runs = payload.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    return {
        "stop_reason": payload.get("stop_reason"),
        "run_count": len(runs),
        "tool_result_count": tool_result_count(runs),
        "failed_tool_result_count": failed_tool_result_count(runs),
        "failed_tool_names": failed_tool_names(runs),
        "failed_tool_errors": failed_tool_errors(runs),
        "total_cost": round(total_run_cost(runs), 8),
    }


def tool_result_count(runs: list[Any]) -> int:
    return sum(len(tool_results_for_run(run)) for run in runs)


def failed_tool_result_count(runs: list[Any]) -> int:
    return sum(
        1
        for run in runs
        for tool_result in tool_results_for_run(run)
        if isinstance(tool_result, dict) and tool_result.get("status") == "failed"
    )


def failed_tool_names(runs: list[Any]) -> list[str]:
    names: list[str] = []
    for run in runs:
        for tool_result in tool_results_for_run(run):
            if not isinstance(tool_result, dict):
                continue
            if tool_result.get("status") != "failed":
                continue
            tool_name = tool_result.get("tool_name")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            if tool_name not in names:
                names.append(tool_name)
    return names


def failed_tool_errors(runs: list[Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for run in runs:
        for tool_result in tool_results_for_run(run):
            if not isinstance(tool_result, dict):
                continue
            if tool_result.get("status") != "failed":
                continue
            tool_name = tool_result.get("tool_name")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            raw_error = tool_result.get("error")
            error = raw_error if isinstance(raw_error, str) else ""
            key = (tool_name, error)
            if key in seen:
                continue
            seen.add(key)
            errors.append({"tool_name": tool_name, "error": error})
    return errors


def total_run_cost(runs: list[Any]) -> float:
    total = 0.0
    for run in runs:
        if not isinstance(run, dict):
            continue
        cost_records = run.get("cost_records", [])
        if not isinstance(cost_records, list):
            continue
        for cost_record in cost_records:
            if not isinstance(cost_record, dict):
                continue
            total += float(cost_record.get("total_cost") or 0)
    return total


def tool_results_for_run(run: Any) -> list[Any]:
    if not isinstance(run, dict):
        return []
    tool_results = run.get("tool_results", [])
    if not isinstance(tool_results, list):
        return []
    return tool_results


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
        description="Run bounded Synarch scheduler ticks through the gateway."
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
        default=os.getenv("SYNARCH_SCHEDULER_WORKER_ID", DEFAULT_WORKER_ID),
    )
    argument_parser.add_argument(
        "--project-id",
        default=os.getenv("SYNARCH_SCHEDULER_PROJECT_ID") or None,
    )
    argument_parser.add_argument(
        "--max-tasks",
        type=positive_int,
        default=positive_int(os.getenv("SYNARCH_SCHEDULER_MAX_TASKS", str(DEFAULT_MAX_TASKS))),
    )
    argument_parser.add_argument(
        "--trace-id",
        default=os.getenv("SYNARCH_SCHEDULER_TRACE_ID") or None,
    )
    argument_parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv("SYNARCH_SCHEDULER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running ticks until interrupted or max ticks is reached.",
    )
    argument_parser.add_argument(
        "--interval-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv("SYNARCH_SCHEDULER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--max-ticks",
        type=optional_positive_int,
        default=optional_positive_int(os.getenv("SYNARCH_SCHEDULER_MAX_TICKS")),
        help="Maximum loop iterations. Omit for an unbounded loop.",
    )
    return argument_parser


def run_loop(args: argparse.Namespace) -> None:
    tick_count = 0
    while True:
        tick_count += 1
        started_at = datetime.now(UTC)
        trace_id = args.trace_id or f"trace_scheduler_{uuid4().hex[:12]}"
        try:
            result = run_scheduler_tick(
                gateway_url=args.gateway_url,
                max_tasks=args.max_tasks,
                project_id=args.project_id,
                trace_id=trace_id,
                timeout_seconds=args.timeout_seconds,
                worker_id=args.worker_id,
            )
            result["scheduler"]["status"] = "completed"
        except Exception as error:
            if not args.loop:
                raise
            result = {
                "scheduler": {
                    "worker_id": args.worker_id,
                    "gateway_url": args.gateway_url,
                    "project_id": args.project_id,
                    "max_tasks": args.max_tasks,
                    "trace_id": trace_id,
                    "status": "failed",
                },
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

        finished_at = datetime.now(UTC)
        result["scheduler"]["tick"] = tick_count
        result["scheduler"]["started_at"] = started_at.isoformat()
        result["scheduler"]["finished_at"] = finished_at.isoformat()
        result["scheduler"]["duration_seconds"] = (
            finished_at - started_at
        ).total_seconds()
        try:
            result["worker_heartbeat"] = record_worker_heartbeat(
                state_service_url=getattr(args, "state_service_url", DEFAULT_STATE_SERVICE_URL),
                worker_id=args.worker_id,
                worker_kind="scheduler",
                status=result["scheduler"]["status"],
                target=args.project_id or "all",
                last_tick_result=result["scheduler"],
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
