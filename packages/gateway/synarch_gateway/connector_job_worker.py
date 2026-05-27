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
DEFAULT_MAX_JOBS = 3
DEFAULT_KIND = "cron"
DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_WORKER_ID = "connector-job-worker"


def build_connector_jobs_run_ready_url(
    gateway_url: str,
    *,
    max_jobs: int,
    kind: str = DEFAULT_KIND,
    project_id: str | None = None,
    service_id: str | None = None,
    owner_agent_id: str | None = None,
) -> str:
    params: dict[str, str] = {"max_jobs": str(max_jobs), "kind": kind}
    if project_id:
        params["project_id"] = project_id
    if service_id:
        params["service_id"] = service_id
    if owner_agent_id:
        params["owner_agent_id"] = owner_agent_id
    return f"{gateway_url.rstrip('/')}/connector-jobs/run-ready?{urlencode(params)}"


def run_connector_job_tick(
    *,
    gateway_url: str,
    max_jobs: int,
    kind: str,
    project_id: str | None,
    service_id: str | None,
    owner_agent_id: str | None,
    trace_id: str | None,
    timeout_seconds: float,
    worker_id: str = DEFAULT_WORKER_ID,
) -> dict[str, Any]:
    request_trace_id = trace_id or f"trace_connector_jobs_{uuid4().hex[:12]}"
    request = Request(
        build_connector_jobs_run_ready_url(
            gateway_url,
            max_jobs=max_jobs,
            kind=kind,
            project_id=project_id,
            service_id=service_id,
            owner_agent_id=owner_agent_id,
        ),
        method="POST",
        headers={
            "X-Synarch-Trace-Id": request_trace_id,
            "X-Synarch-Connector-Job-Worker-Id": worker_id,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "connector_jobs": {
            "worker_id": worker_id,
            "gateway_url": gateway_url,
            "project_id": project_id,
            "service_id": service_id,
            "owner_agent_id": owner_agent_id,
            "kind": kind,
            "max_jobs": max_jobs,
            "trace_id": request_trace_id,
            **connector_job_result_summary(payload),
        },
        "result": payload,
    }


def connector_job_result_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "stop_reason": None,
            "run_count": 0,
            "completed_run_count": 0,
            "failed_run_count": 0,
            "blocked_run_count": 0,
            "skipped_run_count": 0,
        }
    runs = payload.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    statuses = [connector_job_run_status(run) for run in runs]
    return {
        "stop_reason": payload.get("stop_reason"),
        "run_count": len(runs),
        "completed_run_count": statuses.count("completed"),
        "failed_run_count": statuses.count("failed"),
        "blocked_run_count": statuses.count("blocked"),
        "skipped_run_count": statuses.count("skipped"),
    }


def connector_job_run_status(run: Any) -> str | None:
    if not isinstance(run, dict):
        return None
    run_record = run.get("run")
    if not isinstance(run_record, dict):
        return None
    status = run_record.get("status")
    return status if isinstance(status, str) else None


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
        description="Run bounded Synarch connector job batches through the gateway."
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
        default=os.getenv("SYNARCH_CONNECTOR_JOB_WORKER_ID", DEFAULT_WORKER_ID),
    )
    argument_parser.add_argument(
        "--project-id",
        default=os.getenv("SYNARCH_CONNECTOR_JOB_PROJECT_ID") or None,
    )
    argument_parser.add_argument(
        "--service-id",
        default=os.getenv("SYNARCH_CONNECTOR_JOB_SERVICE_ID") or None,
    )
    argument_parser.add_argument(
        "--owner-agent-id",
        default=os.getenv("SYNARCH_CONNECTOR_JOB_OWNER_AGENT_ID") or None,
    )
    argument_parser.add_argument(
        "--kind",
        default=os.getenv("SYNARCH_CONNECTOR_JOB_KIND", DEFAULT_KIND),
    )
    argument_parser.add_argument(
        "--max-jobs",
        type=positive_int,
        default=positive_int(
            os.getenv("SYNARCH_CONNECTOR_JOB_MAX_JOBS", str(DEFAULT_MAX_JOBS))
        ),
    )
    argument_parser.add_argument(
        "--trace-id",
        default=os.getenv("SYNARCH_CONNECTOR_JOB_TRACE_ID") or None,
    )
    argument_parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv("SYNARCH_CONNECTOR_JOB_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running connector job batches until interrupted or max ticks is reached.",
    )
    argument_parser.add_argument(
        "--interval-seconds",
        type=positive_float,
        default=positive_float(
            os.getenv("SYNARCH_CONNECTOR_JOB_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
        ),
    )
    argument_parser.add_argument(
        "--max-ticks",
        type=optional_positive_int,
        default=optional_positive_int(os.getenv("SYNARCH_CONNECTOR_JOB_MAX_TICKS")),
        help="Maximum loop iterations. Omit for an unbounded loop.",
    )
    return argument_parser


def run_loop(args: argparse.Namespace) -> None:
    tick_count = 0
    while True:
        tick_count += 1
        started_at = datetime.now(UTC)
        trace_id = args.trace_id or f"trace_connector_jobs_{uuid4().hex[:12]}"
        try:
            result = run_connector_job_tick(
                gateway_url=args.gateway_url,
                max_jobs=args.max_jobs,
                kind=args.kind,
                project_id=args.project_id,
                service_id=args.service_id,
                owner_agent_id=args.owner_agent_id,
                trace_id=trace_id,
                timeout_seconds=args.timeout_seconds,
                worker_id=args.worker_id,
            )
            result["connector_jobs"]["status"] = "completed"
        except Exception as error:
            if not args.loop:
                raise
            result = {
                "connector_jobs": {
                    "worker_id": args.worker_id,
                    "gateway_url": args.gateway_url,
                    "project_id": args.project_id,
                    "service_id": args.service_id,
                    "owner_agent_id": args.owner_agent_id,
                    "kind": args.kind,
                    "max_jobs": args.max_jobs,
                    "trace_id": trace_id,
                    "status": "failed",
                },
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

        finished_at = datetime.now(UTC)
        result["connector_jobs"]["tick"] = tick_count
        result["connector_jobs"]["started_at"] = started_at.isoformat()
        result["connector_jobs"]["finished_at"] = finished_at.isoformat()
        result["connector_jobs"]["duration_seconds"] = (
            finished_at - started_at
        ).total_seconds()
        try:
            result["worker_heartbeat"] = record_worker_heartbeat(
                state_service_url=getattr(args, "state_service_url", DEFAULT_STATE_SERVICE_URL),
                worker_id=args.worker_id,
                worker_kind="connector_job",
                status=result["connector_jobs"]["status"],
                target=connector_job_worker_target(
                    args.kind,
                    project_id=args.project_id,
                    service_id=args.service_id,
                    owner_agent_id=args.owner_agent_id,
                ),
                last_tick_result=result["connector_jobs"],
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


def connector_job_worker_target(
    kind: str,
    *,
    project_id: str | None,
    service_id: str | None,
    owner_agent_id: str | None,
) -> str:
    parts = [kind]
    if project_id:
        parts.append(f"project:{project_id}")
    if service_id:
        parts.append(f"service:{service_id}")
    if owner_agent_id:
        parts.append(f"owner:{owner_agent_id}")
    return "/".join(parts)


if __name__ == "__main__":
    main()
