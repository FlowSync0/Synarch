from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

DEFAULT_GATEWAY_URL = "http://localhost:8000"
DEFAULT_MAX_TASKS = 3
DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 60.0


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
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_scheduler_{uuid4().hex[:12]}"
    request = Request(
        build_run_ready_url(gateway_url, max_tasks=max_tasks, project_id=project_id),
        method="POST",
        headers={"X-Synarch-Trace-Id": request_trace_id},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "scheduler": {
            "gateway_url": gateway_url,
            "project_id": project_id,
            "max_tasks": max_tasks,
            "trace_id": request_trace_id,
        },
        "result": payload,
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
    if value in {None, ""}:
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
        result = run_scheduler_tick(
            gateway_url=args.gateway_url,
            max_tasks=args.max_tasks,
            project_id=args.project_id,
            trace_id=args.trace_id,
            timeout_seconds=args.timeout_seconds,
        )
        result["scheduler"]["tick"] = tick_count
        print(json.dumps(result, separators=(",", ":")), flush=True)
        if not args.loop or (args.max_ticks is not None and tick_count >= args.max_ticks):
            return
        time.sleep(args.interval_seconds)


def main() -> None:
    run_loop(parser().parse_args())


if __name__ == "__main__":
    main()
