from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from synarch_state_service.main import app, reset_repositories


@pytest.fixture(autouse=True)
def clean_state_service() -> None:
    reset_repositories()


def task_payload(
    project_id: str,
    title: str,
    assigned_agent_id: str = "agent-dev",
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": project_id,
        "title": title,
        "assigned_agent_id": assigned_agent_id,
        "acceptance_criteria": [f"{title} has a recorded outcome."],
    }
    payload.update(overrides)
    return payload


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_work_queue_claims_and_completes_durable_item() -> None:
    client = TestClient(app)
    trace_id = "trace_work_queue_complete"

    create_response = client.post(
        "/work-queue/items",
        headers={"X-Synarch-Actor-Id": "local-user", "X-Synarch-Trace-Id": trace_id},
        json={
            "id": "work-reminder-1",
            "queue_name": "reminders",
            "payload": {"project_id": "project-demo", "task": "send reminder"},
            "priority": 10,
        },
    )
    assert create_response.status_code == 201

    claim_response = client.post(
        "/work-queue/claim",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "queue_name": "reminders",
            "worker_id": "worker-reminders",
            "limit": 1,
            "lease_seconds": 120,
        },
    )

    assert claim_response.status_code == 200
    claimed_items = claim_response.json()["claimed_items"]
    assert [item["id"] for item in claimed_items] == ["work-reminder-1"]
    assert claimed_items[0]["status"] == "running"
    assert claimed_items[0]["lease_owner_id"] == "worker-reminders"
    assert claimed_items[0]["attempt_count"] == 1

    complete_response = client.post(
        "/work-queue/items/work-reminder-1/complete",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "worker_id": "worker-reminders",
            "result": {"sent": True},
        },
    )

    assert complete_response.status_code == 200
    completed_item = complete_response.json()
    assert completed_item["status"] == "completed"
    assert completed_item["lease_owner_id"] is None
    assert completed_item["result"] == {"sent": True}
    assert completed_item["completed_at"] is not None

    audit_actions = [
        audit["action"] for audit in client.get("/audit-logs", params={"trace_id": trace_id}).json()
    ]
    assert audit_actions == [
        "work_queue.item_created",
        "work_queue.claimed",
        "work_queue.completed",
    ]


def test_work_queue_failure_dead_letters_after_max_attempts() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/work-queue/items",
        json={
            "id": "work-pdf-1",
            "queue_name": "pdf-ingestion",
            "payload": {"document_id": "doc-1"},
            "max_attempts": 1,
        },
    )
    assert create_response.status_code == 201

    claim_response = client.post(
        "/work-queue/claim",
        json={
            "queue_name": "pdf-ingestion",
            "worker_id": "worker-pdf",
            "limit": 1,
        },
    )
    assert claim_response.status_code == 200

    fail_response = client.post(
        "/work-queue/items/work-pdf-1/fail",
        json={
            "worker_id": "worker-pdf",
            "error": "PDF encrypted; human password required.",
        },
    )

    assert fail_response.status_code == 200
    failed_item = fail_response.json()
    assert failed_item["status"] == "dead_lettered"
    assert failed_item["last_error"] == "PDF encrypted; human password required."
    assert failed_item["completed_at"] is not None


def test_work_queue_review_retry_requeues_dead_lettered_item() -> None:
    client = TestClient(app)
    trace_id = "trace_work_queue_review_retry"

    assert client.post(
        "/work-queue/items",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "id": "work-review-retry-1",
            "queue_name": "pdf-ingestion",
            "payload": {"action": "log", "message": "retry me"},
            "max_attempts": 1,
        },
    ).status_code == 201
    assert client.post(
        "/work-queue/claim",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "queue_name": "pdf-ingestion",
            "worker_id": "worker-pdf",
            "limit": 1,
        },
    ).status_code == 200
    assert client.post(
        "/work-queue/items/work-review-retry-1/fail",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "worker_id": "worker-pdf",
            "error": "Needs human review.",
        },
    ).json()["status"] == "dead_lettered"

    retry_response = client.post(
        "/work-queue/items/work-review-retry-1/review-decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "action": "retry",
            "reviewed_by_type": "user",
            "reviewed_by_id": "local-user",
            "reason": "Human provided the missing information.",
        },
    )

    assert retry_response.status_code == 200
    retried_item = retry_response.json()
    assert retried_item["status"] == "queued"
    assert retried_item["lease_owner_id"] is None
    assert retried_item["completed_at"] is None
    assert retried_item["last_error"] is None
    assert retried_item["max_attempts"] == 2

    audit_actions = [
        audit["action"] for audit in client.get("/audit-logs", params={"trace_id": trace_id}).json()
    ]
    assert audit_actions[-1] == "work_queue.reviewed"

    retry_claim = client.post(
        "/work-queue/claim",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "queue_name": "pdf-ingestion",
            "worker_id": "worker-pdf-retry",
            "limit": 1,
        },
    ).json()
    assert retry_claim["claimed_items"][0]["id"] == "work-review-retry-1"
    assert retry_claim["claimed_items"][0]["attempt_count"] == 2


def test_work_queue_review_dead_letters_queued_item() -> None:
    client = TestClient(app)
    trace_id = "trace_work_queue_review_dead_letter"

    assert client.post(
        "/work-queue/items",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "id": "work-review-dead-letter-1",
            "queue_name": "webhooks",
            "payload": {"action": "log", "message": "bad target"},
        },
    ).status_code == 201

    decision_response = client.post(
        "/work-queue/items/work-review-dead-letter-1/review-decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "action": "dead_letter",
            "reviewed_by_type": "user",
            "reviewed_by_id": "local-user",
            "reason": "Invalid webhook target.",
        },
    )

    assert decision_response.status_code == 200
    item = decision_response.json()
    assert item["status"] == "dead_lettered"
    assert item["last_error"] == "Invalid webhook target."
    assert item["completed_at"] is not None

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert audits[-1]["action"] == "work_queue.reviewed"
    assert audits[-1]["payload"]["action"] == "dead_letter"

    claim_response = client.post(
        "/work-queue/claim",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "queue_name": "webhooks",
            "worker_id": "worker-webhooks",
            "limit": 1,
        },
    )
    assert claim_response.json()["claimed_items"] == []


def test_work_queue_summary_groups_operational_queue_state() -> None:
    client = TestClient(app)
    now = datetime.now(UTC)

    work_items = [
        {
            "id": "work-reminder-ready",
            "queue_name": "reminders",
            "status": "queued",
            "payload": {"action": "project.reminder.emit"},
            "priority": 10,
            "created_at": (now - timedelta(minutes=10)).isoformat(),
        },
        {
            "id": "work-reminder-delayed",
            "queue_name": "reminders",
            "status": "queued",
            "payload": {"action": "project.reminder.emit"},
            "run_after_at": (now + timedelta(hours=2)).isoformat(),
        },
        {
            "id": "work-reminder-running",
            "queue_name": "reminders",
            "status": "running",
            "payload": {"action": "project.reminder.emit"},
            "lease_owner_id": "worker-reminders",
            "lease_expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
        {
            "id": "work-pdf-dead",
            "queue_name": "pdf-ingestion",
            "status": "dead_lettered",
            "payload": {"action": "pdf.extract"},
            "last_error": "PDF password required.",
            "completed_at": now.isoformat(),
        },
        {
            "id": "work-pdf-failed",
            "queue_name": "pdf-ingestion",
            "status": "failed",
            "payload": {"action": "pdf.extract"},
            "last_error": "OCR provider failed.",
        },
    ]
    for item in work_items:
        assert client.post("/work-queue/items", json=item).status_code == 201

    response = client.get("/work-queue/summary")

    assert response.status_code == 200
    summaries = {item["queue_name"]: item for item in response.json()}
    assert list(summaries) == ["pdf-ingestion", "reminders"]
    assert summaries["reminders"]["item_count"] == 3
    assert summaries["reminders"]["status_counts"] == {"queued": 2, "running": 1}
    assert summaries["reminders"]["ready_count"] == 1
    assert summaries["reminders"]["delayed_count"] == 1
    assert summaries["reminders"]["running_count"] == 1
    assert summaries["reminders"]["failed_count"] == 0
    assert summaries["reminders"]["dead_lettered_count"] == 0
    assert summaries["reminders"]["oldest_queued_at"] is not None
    assert summaries["reminders"]["next_run_after_at"] is not None
    assert summaries["pdf-ingestion"]["item_count"] == 2
    assert summaries["pdf-ingestion"]["failed_count"] == 1
    assert summaries["pdf-ingestion"]["dead_lettered_count"] == 1
    assert summaries["pdf-ingestion"]["latest_error"] == "OCR provider failed."


def test_worker_heartbeat_upsert_tracks_durable_worker_status() -> None:
    client = TestClient(app)
    trace_id = "trace_worker_heartbeat"

    first_response = client.post(
        "/worker-heartbeats/work-queue-worker-1",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "worker_kind": "work_queue",
            "status": "completed",
            "target": "reminders",
            "last_tick_result": {
                "tick": 1,
                "claimed_count": 1,
                "completed_count": 1,
                "failed_count": 0,
            },
        },
    )

    assert first_response.status_code == 200
    first_heartbeat = first_response.json()
    assert first_heartbeat["id"] == "work-queue-worker-1"
    assert first_heartbeat["worker_kind"] == "work_queue"
    assert first_heartbeat["status"] == "completed"
    assert first_heartbeat["target"] == "reminders"
    assert first_heartbeat["heartbeat_count"] == 1
    assert first_heartbeat["last_error"] is None

    second_response = client.post(
        "/worker-heartbeats/work-queue-worker-1",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "worker_kind": "work_queue",
            "status": "failed",
            "target": "reminders",
            "last_tick_result": {"tick": 2, "claimed_count": 0},
            "last_error": "state timeout",
        },
    )

    assert second_response.status_code == 200
    second_heartbeat = second_response.json()
    assert second_heartbeat["heartbeat_count"] == 2
    assert second_heartbeat["status"] == "failed"
    assert second_heartbeat["last_error"] == "state timeout"
    assert second_heartbeat["started_at"] == first_heartbeat["started_at"]
    assert second_heartbeat["last_seen_at"] >= first_heartbeat["last_seen_at"]

    listed = client.get("/worker-heartbeats", params={"worker_kind": "work_queue"}).json()
    assert [heartbeat["id"] for heartbeat in listed] == ["work-queue-worker-1"]
    assert listed[0]["last_tick_result"]["tick"] == 2

    audit_actions = [
        audit["action"] for audit in client.get("/audit-logs", params={"trace_id": trace_id}).json()
    ]
    assert audit_actions == ["worker.heartbeat", "worker.heartbeat"]


def test_work_queue_recover_expired_lease_requeues_item() -> None:
    client = TestClient(app)
    expired_at = datetime.now(UTC) - timedelta(minutes=5)

    create_response = client.post(
        "/work-queue/items",
        json={
            "id": "work-webhook-1",
            "queue_name": "webhook-delivery",
            "status": "running",
            "payload": {"event": "supplier.reply"},
            "lease_owner_id": "worker-webhook",
            "lease_expires_at": expired_at.isoformat(),
            "attempt_count": 1,
            "max_attempts": 3,
        },
    )
    assert create_response.status_code == 201

    recovery_response = client.post("/work-queue/recover-expired-leases")

    assert recovery_response.status_code == 200
    assert recovery_response.json()["recovered_item_ids"] == ["work-webhook-1"]
    recovered_item = client.get(
        "/work-queue/items",
        params={"queue_name": "webhook-delivery"},
    ).json()[0]
    assert recovered_item["status"] == "queued"
    assert recovered_item["lease_owner_id"] is None
    assert recovered_item["last_error"] == "lease_expired"


def test_service_and_skill_registry_capture_access_rules() -> None:
    client = TestClient(app)

    service_response = client.post(
        "/services",
        json={
            "id": "connector-github-test",
            "name": "GitHub",
            "kind": "tool_provider",
            "capabilities": ["git.read", "git.write"],
            "credential_scopes": ["github:contents:read", "github:contents:write"],
            "allowed_divisions": ["dev"],
            "audit_required": True,
            "metadata": {"connector_type": "source_control"},
        },
    )
    assert service_response.status_code == 201

    skill_response = client.post(
        "/skills",
        json={
            "id": "implementation-test",
            "name": "Implementation",
            "description": "Make scoped code changes.",
            "required_tools": ["git.read", "git.write"],
            "allowed_divisions": ["dev"],
        },
    )
    assert skill_response.status_code == 201

    services_response = client.get("/services", params={"kind": "tool_provider"})
    skills_response = client.get("/skills", params={"enabled": True})

    assert services_response.status_code == 200
    assert services_response.json()[0]["allowed_divisions"] == ["dev"]
    assert services_response.json()[0]["credential_scopes"] == [
        "github:contents:read",
        "github:contents:write",
    ]
    assert services_response.json()[0]["metadata"] == {"connector_type": "source_control"}
    assert skills_response.status_code == 200
    assert skills_response.json()[0]["required_tools"] == ["git.read", "git.write"]


def test_service_registry_rejects_unknown_agent_access_rules() -> None:
    client = TestClient(app)

    response = client.post(
        "/services",
        json={
            "id": "connector-private-test",
            "name": "Private Connector",
            "kind": "tool_provider",
            "allowed_agent_ids": ["agent-missing"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown access agents: ['agent-missing']"


def test_project_then_task_flow() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Gateway API phase 1",
            "goal": "Create the first gateway route",
            "owner_agent_id": "agent-direction",
        },
    )

    assert project_response.status_code == 201
    project = project_response.json()

    task_response = client.post(
        "/tasks",
        json=task_payload(project["id"], "Implement route"),
    )

    assert task_response.status_code == 201
    assert task_response.json()["project_id"] == project["id"]
    assert task_response.json()["acceptance_criteria"] == [
        "Implement route has a recorded outcome."
    ]


def test_project_rejects_inactive_owner() -> None:
    client = TestClient(app)

    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-retired-owner",
            "name": "IA Retired Owner",
            "role": "Former project owner",
            "division": "direction",
            "status": "inactive",
        },
    )
    assert agent_response.status_code == 201

    project_response = client.post(
        "/projects",
        json={
            "title": "Inactive owner project",
            "goal": "This project should not be owned by an inactive agent.",
            "owner_agent_id": "agent-retired-owner",
        },
    )

    assert project_response.status_code == 400
    assert project_response.json()["detail"] == (
        "Project owner is not active: agent-retired-owner"
    )
    assert client.get("/projects").json() == []


def test_project_workspace_rejects_inactive_allowed_agent() -> None:
    client = TestClient(app)
    for agent_id, status in [
        ("agent-direction", "active"),
        ("agent-retired-worker", "inactive"),
    ]:
        response = client.post(
            "/agents",
            json={
                "id": agent_id,
                "name": agent_id,
                "role": "Project participant",
                "division": "dev",
                "status": status,
            },
        )
        assert response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "id": "project-inactive-workspace-agent",
            "title": "Inactive workspace agent",
            "goal": "Workspace active access must exclude inactive agents.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    workspace_response = client.post(
        "/project-workspaces",
        json={
            "id": "workspace-inactive-agent",
            "project_id": "project-inactive-workspace-agent",
            "name": "Inactive agent workspace",
            "memory_scope": "project:project-inactive-workspace-agent",
            "allowed_agent_ids": ["agent-direction", "agent-retired-worker"],
        },
    )

    assert workspace_response.status_code == 400
    assert workspace_response.json()["detail"] == (
        "Workspace agents are not active: ['agent-retired-worker']"
    )
    assert client.get("/project-workspaces").json() == []


def test_task_credential_scopes_must_reference_required_tools() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Scoped credential task",
            "goal": "Reject inconsistent credential scope declarations.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Fetch private page",
            required_tools=["web.fetch"],
            required_tool_scopes={"git.read": ["github:contents:read"]},
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Credential scopes reference non-required tools: ['git.read']"
    )


def test_credential_access_request_records_event_and_audit() -> None:
    client = TestClient(app)
    trace_id = "trace_credential_access_request"
    project_response = client.post(
        "/projects",
        json={
            "title": "Credential request",
            "goal": "Request missing connector credentials",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Fetch supplier portal",
            assigned_agent_id="agent-ops-sourcing",
            required_tools=["web.fetch"],
        ),
    )
    assert task_response.status_code == 201

    access_response = client.post(
        "/credential-access-requests",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-scheduler",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "credential-access-test",
            "task_id": task_response.json()["id"],
            "project_id": project_response.json()["id"],
            "agent_id": "agent-ops-sourcing",
            "tool_name": "web.fetch",
            "requested_scopes": ["browser:authenticated_fetch"],
            "candidate_service_ids": ["connector-supplier-web"],
            "reason": "Credential scopes missing for required tool: web.fetch",
        },
    )

    assert access_response.status_code == 201
    access_request = access_response.json()
    assert access_request["status"] == "requested"
    assert access_request["requested_by_id"] == "gateway-scheduler"

    list_response = client.get(
        "/credential-access-requests",
        params={"project_id": project_response.json()["id"], "status": "requested"},
    )
    assert list_response.status_code == 200
    assert [request["id"] for request in list_response.json()] == [
        "credential-access-test"
    ]

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == ["approval.requested"]
    assert events[0]["payload"]["request_type"] == "credential_access"
    assert events[0]["payload"]["tool_name"] == "web.fetch"

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [audit["action"] for audit in audits] == [
        "credential_access_request.created"
    ]
    assert audits[0]["target_id"] == "credential-access-test"


def test_human_assistance_request_records_event_audit_and_resolution() -> None:
    client = TestClient(app)
    trace_id = "trace_human_assistance_request"
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier CAPTCHA",
            "goal": "Escalate human-only supplier portal steps.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Inspect supplier portal",
            assigned_agent_id="agent-ops-sourcing",
            required_tools=["web.extract"],
        ),
    )
    assert task_response.status_code == 201

    assistance_response = client.post(
        "/human-assistance-requests",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-ops-sourcing",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "human-assistance-captcha-test",
            "project_id": project_response.json()["id"],
            "task_id": task_response.json()["id"],
            "agent_id": "agent-ops-sourcing",
            "kind": "captcha",
            "title": "CAPTCHA on supplier portal",
            "description": "Human verification is required before extraction can continue.",
            "urgency": "high",
            "evidence": {"url": "https://supplier.example/login"},
            "requested_by_id": "agent-ops-sourcing",
        },
    )

    assert assistance_response.status_code == 201
    assistance_request = assistance_response.json()
    assert assistance_request["status"] == "requested"
    assert assistance_request["kind"] == "captcha"

    list_response = client.get(
        "/human-assistance-requests",
        params={"project_id": project_response.json()["id"], "status": "requested"},
    )
    assert list_response.status_code == 200
    assert [request["id"] for request in list_response.json()] == [
        "human-assistance-captcha-test"
    ]

    resolution_response = client.post(
        "/human-assistance-requests/human-assistance-captcha-test/resolutions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "request_id": "human-assistance-captcha-test",
            "status": "answered",
            "response": "Manual verification completed. Retry the portal extraction.",
            "resolved_by_type": "user",
            "resolved_by_id": "local-user",
        },
    )
    assert resolution_response.status_code == 201
    assert resolution_response.json()["events_emitted"][0]["type"] == (
        "human_assistance.resolved"
    )

    request_response = client.get(
        "/human-assistance-requests/human-assistance-captcha-test"
    )
    assert request_response.status_code == 200
    assert request_response.json()["status"] == "answered"
    assert request_response.json()["response"] == (
        "Manual verification completed. Retry the portal extraction."
    )

    repeat_response = client.post(
        "/human-assistance-requests/human-assistance-captcha-test/resolutions",
        json={
            "request_id": "human-assistance-captcha-test",
            "status": "dismissed",
            "response": "Duplicate.",
            "resolved_by_type": "user",
            "resolved_by_id": "local-user",
        },
    )
    assert repeat_response.status_code == 409

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "human_assistance.requested",
        "human_assistance.resolved",
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert "human_assistance_request.created" in [
        audit["action"] for audit in audits
    ]
    assert "human_assistance_request.answered" in [
        audit["action"] for audit in audits
    ]


def test_human_assistance_request_rejects_unknown_agent_without_task() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Manual escalation",
            "goal": "Validate human assistance request input boundaries.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    assistance_response = client.post(
        "/human-assistance-requests",
        json={
            "id": "human-assistance-unknown-agent-test",
            "project_id": project_response.json()["id"],
            "task_id": None,
            "agent_id": "agent-does-not-exist",
            "kind": "manual_action",
            "title": "Manual gate",
            "description": "Should fail before hitting the database foreign key.",
            "urgency": "medium",
            "requested_by_type": "system",
            "requested_by_id": "test-suite",
        },
    )

    assert assistance_response.status_code == 400
    assert assistance_response.json()["detail"] == "Unknown agent: agent-does-not-exist"


def test_human_assistance_answer_requeues_blocked_task() -> None:
    client = TestClient(app)
    trace_id = "trace_human_assistance_requeue_task"
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier CAPTCHA",
            "goal": "Resume work after a human completes a CAPTCHA.",
            "owner_agent_id": "agent-direction",
        },
    )
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Resume supplier portal extraction",
            assigned_agent_id="agent-ops-sourcing",
            status="blocked",
            attempt_count=3,
            max_attempts=3,
            result={
                "summary": "Blocked by CAPTCHA.",
                "blocked_reason": "human_assistance_requested",
            },
        ),
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    assistance_response = client.post(
        "/human-assistance-requests",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-ops-sourcing",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "human-assistance-requeue-test",
            "project_id": project_response.json()["id"],
            "task_id": task_id,
            "agent_id": "agent-ops-sourcing",
            "kind": "captcha",
            "title": "CAPTCHA on supplier portal",
            "description": "Human verification is required before extraction can continue.",
            "urgency": "high",
            "evidence": {"url": "https://supplier.example/login"},
            "requested_by_id": "agent-ops-sourcing",
        },
    )
    assert assistance_response.status_code == 201

    resolution_response = client.post(
        "/human-assistance-requests/human-assistance-requeue-test/resolutions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "request_id": "human-assistance-requeue-test",
            "status": "answered",
            "response": "CAPTCHA completed. Retry extraction.",
            "resolved_by_type": "user",
            "resolved_by_id": "local-user",
        },
    )
    assert resolution_response.status_code == 201
    assert [event["type"] for event in resolution_response.json()["events_emitted"]] == [
        "human_assistance.resolved",
        "task.reviewed",
    ]

    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "queued"
    assert task["max_attempts"] == 4
    assert task["dead_letter_reason"] is None
    task_resolution = task["result"]["last_human_assistance_resolution"]
    assert parse_timestamp(task_resolution.pop("resolved_at")) == parse_timestamp(
        resolution_response.json()["resolved_at"]
    )
    assert task_resolution == {
        "human_assistance_request_id": "human-assistance-requeue-test",
        "task_id": task_id,
        "project_id": project_response.json()["id"],
        "kind": "captcha",
        "status": "answered",
        "response": "CAPTCHA completed. Retry extraction.",
        "resolved_by_type": "user",
        "resolved_by_id": "local-user",
        "next_status": "queued",
    }

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "human_assistance.requested",
        "human_assistance.resolved",
        "task.reviewed",
    ]
    assert events[-1]["payload"]["previous_status"] == "blocked"
    assert events[-1]["payload"]["next_status"] == "queued"

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert "task.human_assistance_applied" in [
        audit["action"] for audit in audits
    ]


def test_human_assistance_dismiss_keeps_blocked_task_in_review() -> None:
    client = TestClient(app)
    trace_id = "trace_human_assistance_dismiss_task"
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier CAPTCHA",
            "goal": "Keep unresolved human blockers reviewable.",
            "owner_agent_id": "agent-direction",
        },
    )
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Inspect supplier portal",
            assigned_agent_id="agent-ops-sourcing",
            status="blocked",
            result={"blocked_reason": "human_assistance_requested"},
        ),
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    assert (
        client.post(
            "/human-assistance-requests",
            json={
                "id": "human-assistance-dismiss-test",
                "project_id": project_response.json()["id"],
                "task_id": task_id,
                "agent_id": "agent-ops-sourcing",
                "kind": "manual_action",
                "title": "Manual login required",
                "description": "The user needs to decide whether to log in.",
                "requested_by_id": "agent-ops-sourcing",
            },
        ).status_code
        == 201
    )

    resolution_response = client.post(
        "/human-assistance-requests/human-assistance-dismiss-test/resolutions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "request_id": "human-assistance-dismiss-test",
            "status": "dismissed",
            "response": "Do not continue this supplier portal.",
            "resolved_by_type": "user",
            "resolved_by_id": "local-user",
        },
    )
    assert resolution_response.status_code == 201

    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "needs_review"
    assert task["dead_letter_reason"] == "human_assistance_dismissed"
    assert task["result"]["last_human_assistance_resolution"]["status"] == "dismissed"
    assert task["result"]["last_human_assistance_resolution"]["next_status"] == (
        "needs_review"
    )


def test_credential_access_decision_updates_request_and_records_event() -> None:
    client = TestClient(app)
    trace_id = "trace_credential_access_decision"
    project_response = client.post(
        "/projects",
        json={
            "title": "Credential decision",
            "goal": "Approve or reject missing connector credentials",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Read private repository",
            assigned_agent_id="agent-dev",
            required_tools=["git.read"],
        ),
    )
    assert task_response.status_code == 201
    access_response = client.post(
        "/credential-access-requests",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-scheduler",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "credential-access-decision-test",
            "task_id": task_response.json()["id"],
            "project_id": project_response.json()["id"],
            "agent_id": "agent-dev",
            "tool_name": "git.read",
            "candidate_service_ids": ["connector-github"],
            "reason": "No credential-ready service for required tool: git.read",
        },
    )
    assert access_response.status_code == 201

    decision_response = client.post(
        "/credential-access-requests/credential-access-decision-test/decisions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "request_id": "credential-access-decision-test",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Approved for a scoped repository read.",
        },
    )

    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert [event["type"] for event in decision["events_emitted"]] == [
        "approval.decided"
    ]
    assert decision["events_emitted"][0]["payload"]["request_type"] == "credential_access"
    request_response = client.get(
        "/credential-access-requests/credential-access-decision-test"
    )
    assert request_response.json()["status"] == "approved"

    repeat_response = client.post(
        "/credential-access-requests/credential-access-decision-test/decisions",
        json={
            "request_id": "credential-access-decision-test",
            "status": "rejected",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Duplicate decision.",
        },
    )
    assert repeat_response.status_code == 409

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "approval.requested",
        "approval.decided",
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert "credential_access_request.approved" in [
        audit["action"] for audit in audits
    ]


def test_credential_grant_application_updates_service_and_request() -> None:
    client = TestClient(app)
    trace_id = "trace_credential_grant_application"
    service_response = client.post(
        "/services",
        json={
            "id": "connector-supplier-web-test",
            "name": "Supplier Web",
            "kind": "tool_provider",
            "capabilities": ["web.fetch"],
            "credential_scopes": [],
            "allowed_divisions": ["ops-sourcing"],
        },
    )
    assert service_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "title": "Credential grant",
            "goal": "Apply approved connector credentials",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Fetch authenticated supplier page",
            assigned_agent_id="agent-ops-sourcing",
            required_tools=["web.fetch"],
        ),
    )
    assert task_response.status_code == 201
    access_response = client.post(
        "/credential-access-requests",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-scheduler",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "credential-access-grant-test",
            "task_id": task_response.json()["id"],
            "project_id": project_response.json()["id"],
            "agent_id": "agent-ops-sourcing",
            "tool_name": "web.fetch",
            "requested_scopes": ["browser:authenticated_fetch"],
            "candidate_service_ids": ["connector-supplier-web-test"],
            "reason": "Credential scopes missing for required tool: web.fetch",
        },
    )
    assert access_response.status_code == 201
    decision_response = client.post(
        "/credential-access-requests/credential-access-grant-test/decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "request_id": "credential-access-grant-test",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Approved for supplier sourcing.",
        },
    )
    assert decision_response.status_code == 201

    apply_response = client.post(
        "/credential-access-requests/credential-access-grant-test/grant-applications",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "request_id": "credential-access-grant-test",
            "service_id": "connector-supplier-web-test",
            "applied_by_type": "user",
            "applied_by_id": "local-user",
            "rationale": "Apply the approved credential grant.",
        },
    )

    assert apply_response.status_code == 201
    application = apply_response.json()
    assert application["access_request"]["status"] == "applied"
    assert application["grant"]["scopes"] == ["browser:authenticated_fetch"]
    assert application["service"]["credential_scopes"] == [
        "browser:authenticated_fetch"
    ]
    assert [event["type"] for event in application["events_emitted"]] == [
        "credential_grant.applied"
    ]
    assert client.get("/credential-access-requests/credential-access-grant-test").json()[
        "status"
    ] == "applied"
    assert client.get("/services/connector-supplier-web-test").json()[
        "credential_scopes"
    ] == ["browser:authenticated_fetch"]
    grants = client.get(
        "/credential-grants",
        params={"request_id": "credential-access-grant-test"},
    ).json()
    assert grants[0]["service_id"] == "connector-supplier-web-test"

    duplicate_response = client.post(
        "/credential-access-requests/credential-access-grant-test/grant-applications",
        json={
            "request_id": "credential-access-grant-test",
            "service_id": "connector-supplier-web-test",
            "applied_by_type": "user",
            "applied_by_id": "local-user",
            "rationale": "Duplicate application.",
        },
    )
    assert duplicate_response.status_code == 409

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert "credential_grant.applied" in [event["type"] for event in events]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert "credential_access_request.applied" in [
        audit["action"] for audit in audits
    ]


def test_connector_connection_records_secret_ref_without_secret_value() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_connection"
    service_response = client.post(
        "/services",
        json={
            "id": "connector-firecrawl-test",
            "name": "Firecrawl",
            "kind": "tool_provider",
            "capabilities": ["web.extract"],
            "credential_scopes": [],
            "allowed_divisions": ["ops-sourcing"],
            "metadata": {
                "connector_type": "web_extraction",
                "requires_api_key": True,
                "api_key_env_var": "FIRECRAWL_API_KEY",
            },
        },
    )
    assert service_response.status_code == 201

    connection_response = client.post(
        "/connector-connections",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "service_id": "connector-firecrawl-test",
            "mode": "api_key",
            "credential_scopes": ["firecrawl:api_key"],
            "secret_ref": "local://connector/connector-firecrawl-test/fp_secret",
            "secret_fingerprint": "fp_secret",
            "connected_by_type": "user",
            "connected_by_id": "local-user",
            "rationale": "Connect Firecrawl for web extraction.",
        },
    )

    assert connection_response.status_code == 201
    payload = connection_response.json()
    assert payload["connection"]["status"] == "active"
    assert payload["connection"]["secret_ref"] == (
        "local://connector/connector-firecrawl-test/fp_secret"
    )
    assert "secret_value" not in str(payload)
    assert payload["service"]["credential_scopes"] == ["firecrawl:api_key"]
    assert payload["service"]["metadata"]["configured"] is True

    connections = client.get(
        "/connector-connections",
        params={"service_id": "connector-firecrawl-test"},
    ).json()
    assert [connection["id"] for connection in connections] == [
        payload["connection"]["id"]
    ]
    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert events[0]["type"] == "connector_connection.created"
    assert events[0]["payload"]["secret_ref_configured"] is True
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert audits[0]["action"] == "connector_connection.created"


def test_connector_connection_rejects_no_key_for_credential_scoped_service() -> None:
    client = TestClient(app)
    assert client.post(
        "/services",
        json={
            "id": "connector-github-no-key-rejected",
            "name": "GitHub",
            "kind": "tool_provider",
            "capabilities": ["git.read"],
            "credential_scopes": ["github:contents:read"],
            "metadata": {"manual_connection_url": "https://github.com/settings/tokens"},
        },
    ).status_code == 201

    response = client.post(
        "/connector-connections",
        json={
            "service_id": "connector-github-no-key-rejected",
            "mode": "no_key",
            "credential_scopes": [],
            "connected_by_type": "user",
            "connected_by_id": "local-user",
            "rationale": "No-key should not bypass declared credential scopes.",
        },
    )

    assert response.status_code == 400
    assert "credential scopes" in response.json()["detail"]


def test_connector_connection_disable_clears_active_secret_reference() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_disable"
    assert client.post(
        "/services",
        json={
            "id": "connector-browserless-disable-test",
            "name": "Browserless",
            "kind": "tool_provider",
            "capabilities": ["web.extract"],
            "credential_scopes": [],
            "metadata": {"connector_type": "cloud_browser", "requires_api_key": True},
        },
    ).status_code == 201
    connection_payload = client.post(
        "/connector-connections",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "service_id": "connector-browserless-disable-test",
            "mode": "api_key",
            "credential_scopes": ["browserless:api_key"],
            "secret_ref": "local-file://connectors/connector-browserless-disable-test/fp_secret",
            "secret_fingerprint": "fp_secret",
            "connected_by_type": "user",
            "connected_by_id": "local-user",
            "rationale": "Connect Browserless.",
        },
    ).json()
    connection_id = connection_payload["connection"]["id"]

    response = client.post(
        f"/connector-connections/{connection_id}/disable",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "disabled_by_type": "user",
            "disabled_by_id": "local-user",
            "rationale": "Rotate Browserless credentials.",
            "secret_deleted": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"]["status"] == "disabled"
    assert payload["connection"]["secret_ref"] is None
    assert payload["connection"]["secret_fingerprint"] == "fp_secret"
    assert payload["service"]["metadata"]["configured"] is False
    assert payload["service"]["metadata"]["secret_ref"] is None
    assert payload["service"]["metadata"]["disabled_connection_id"] == connection_id
    assert "local-file://connectors" not in str(payload["event"])
    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "connector_connection.created",
        "connector_connection.disabled",
    ]
    assert events[-1]["payload"]["secret_ref_configured_before"] is True
    assert events[-1]["payload"]["secret_deleted"] is True
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert audits[-1]["action"] == "connector_connection.disabled"


def test_connector_connection_disable_preserves_newer_active_connection() -> None:
    client = TestClient(app)
    assert client.post(
        "/services",
        json={
            "id": "connector-browserless-rotation-test",
            "name": "Browserless Rotation",
            "kind": "tool_provider",
            "capabilities": ["web.extract"],
            "credential_scopes": [],
            "metadata": {"connector_type": "cloud_browser", "requires_api_key": True},
        },
    ).status_code == 201

    first_connection = client.post(
        "/connector-connections",
        json={
            "service_id": "connector-browserless-rotation-test",
            "mode": "api_key",
            "credential_scopes": ["browserless:api_key"],
            "secret_ref": "local-file://connectors/connector-browserless-rotation-test/fp_old",
            "secret_fingerprint": "fp_old",
            "connected_by_type": "user",
            "connected_by_id": "local-user",
            "rationale": "Connect old Browserless credential.",
        },
    ).json()["connection"]
    second_connection_result = client.post(
        "/connector-connections",
        json={
            "service_id": "connector-browserless-rotation-test",
            "mode": "api_key",
            "credential_scopes": ["browserless:api_key"],
            "secret_ref": "local-file://connectors/connector-browserless-rotation-test/fp_new",
            "secret_fingerprint": "fp_new",
            "connected_by_type": "user",
            "connected_by_id": "local-user",
            "rationale": "Rotate Browserless credential.",
        },
    ).json()
    second_connection = second_connection_result["connection"]
    assert second_connection_result["service"]["metadata"]["connector_connection_id"] == (
        second_connection["id"]
    )

    response = client.post(
        f"/connector-connections/{first_connection['id']}/disable",
        json={
            "disabled_by_type": "user",
            "disabled_by_id": "local-user",
            "rationale": "Disable old Browserless credential after rotation.",
            "secret_deleted": True,
        },
    )

    assert response.status_code == 200
    service_metadata = response.json()["service"]["metadata"]
    assert service_metadata["configured"] is True
    assert service_metadata["connector_connection_id"] == second_connection["id"]
    assert service_metadata["secret_ref"] == second_connection["secret_ref"]
    assert service_metadata["secret_fingerprint"] == "fp_new"
    assert service_metadata["disabled_connection_id"] == first_connection["id"]


def test_connector_oauth_connection_can_complete_from_callback() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_oauth_callback"
    service_response = client.post(
        "/services",
        json={
            "id": "connector-oauth-state-test",
            "name": "OAuth state test",
            "kind": "tool_provider",
            "capabilities": ["mail.read"],
            "credential_scopes": [],
            "metadata": {
                "connector_type": "oauth_demo",
                "requires_oauth": True,
            },
        },
    )
    assert service_response.status_code == 201

    connection_response = client.post(
        "/connector-connections",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "service_id": "connector-oauth-state-test",
            "mode": "oauth",
            "credential_scopes": ["mail:read"],
            "setup_url": "https://auth.example.com/authorize?state=oauth_state_test",
            "callback_url": "http://localhost:8000/connectors/connector-oauth-state-test/oauth/callback",
            "external_state": "oauth_state_test",
            "connected_by_type": "user",
            "connected_by_id": "local-user",
            "rationale": "Start OAuth connector setup.",
        },
    )
    assert connection_response.status_code == 201
    created_payload = connection_response.json()
    connection_id = created_payload["connection"]["id"]
    assert created_payload["connection"]["status"] == "needs_oauth"
    assert created_payload["connection"]["setup_url"] is not None
    assert created_payload["service"]["metadata"]["configured"] is False

    callback_response = client.post(
        f"/connector-connections/{connection_id}/oauth-callback",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "oauth_state": "oauth_state_test",
            "secret_ref": "local://connector/oauth/fp_oauth",
            "secret_fingerprint": "fp_oauth",
            "credential_scopes": ["mail:read"],
            "completed_by_type": "user",
            "completed_by_id": "local-user",
            "rationale": "Complete OAuth callback.",
        },
    )

    assert callback_response.status_code == 200
    payload = callback_response.json()
    assert payload["connection"]["status"] == "active"
    assert payload["connection"]["secret_ref"] == "local://connector/oauth/fp_oauth"
    assert payload["service"]["metadata"]["configured"] is True
    assert "oauth_state_test" in payload["connection"]["external_state"]
    assert "oauth_code" not in str(payload)
    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "connector_connection.created",
        "connector_connection.completed",
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [audit["action"] for audit in audits] == [
        "connector_connection.created",
        "connector_connection.completed",
    ]


def test_connector_job_lifecycle_records_events_and_audits() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_job_lifecycle"
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-ops-sourcing-live",
            "name": "IA Ops Live",
            "role": "Supplier follow-up",
            "division": "ops-sourcing",
        },
    )
    assert agent_response.status_code == 201
    service_response = client.post(
        "/services",
        json={
            "id": "connector-supplier-followup",
            "name": "Supplier Follow-up",
            "kind": "tool_provider",
            "capabilities": ["web.fetch"],
            "allowed_divisions": ["ops-sourcing"],
        },
    )
    assert service_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier follow-up",
            "goal": "Follow suppliers until a bounded stop condition.",
            "owner_agent_id": "agent-ops-sourcing-live",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Follow supplier replies",
            assigned_agent_id="agent-ops-sourcing-live",
            required_tools=["web.fetch"],
        ),
    )
    assert task_response.status_code == 201

    job_response = client.post(
        "/connector-jobs",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-ops-sourcing-live",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "connector-job-supplier-followup",
            "service_id": "connector-supplier-followup",
            "project_id": project_response.json()["id"],
            "task_id": task_response.json()["id"],
            "owner_agent_id": "agent-ops-sourcing-live",
            "kind": "cron",
            "schedule": "0 */6 * * *",
            "purpose": "Relance supplier every six hours until reply.",
            "created_by_type": "agent",
            "created_by_id": "agent-ops-sourcing-live",
            "metadata": {"stop_condition": "supplier replied", "cooldown_seconds": 120},
        },
    )

    assert job_response.status_code == 201
    job_result = job_response.json()
    assert job_result["job"]["status"] == "active"
    assert job_result["job"]["next_run_at"] is None
    assert job_result["event"]["type"] == "connector_job.created"
    assert job_result["audit_log"]["action"] == "connector_job.created"

    jobs = client.get(
        "/connector-jobs",
        params={"task_id": task_response.json()["id"], "status": "active"},
    ).json()
    assert [job["id"] for job in jobs] == ["connector-job-supplier-followup"]
    due_jobs = client.get(
        "/connector-jobs",
        params={"status": "active", "due_before": datetime.now(UTC).isoformat()},
    ).json()
    assert [job["id"] for job in due_jobs] == ["connector-job-supplier-followup"]

    run_response = client.post(
        "/connector-jobs/connector-job-supplier-followup/runs",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "connector-job-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "status": "completed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {"attempt": 1, "result": "no supplier reply yet"},
        },
    )

    assert run_response.status_code == 201
    run_result = run_response.json()
    assert run_result["run"]["status"] == "completed"
    assert run_result["run"]["service_id"] == "connector-supplier-followup"
    assert run_result["event"]["type"] == "connector_job.run_recorded"
    assert run_result["audit_log"]["action"] == "connector_job.run_recorded"
    expected_next_run_at = parse_timestamp(run_result["run"]["completed_at"]) + timedelta(
        seconds=120
    )
    refreshed_job = client.get("/connector-jobs/connector-job-supplier-followup").json()
    assert parse_timestamp(refreshed_job["next_run_at"]) == expected_next_run_at
    not_due_jobs = client.get(
        "/connector-jobs",
        params={"status": "active", "due_before": datetime.now(UTC).isoformat()},
    ).json()
    assert [job["id"] for job in not_due_jobs] == []
    future_due_jobs = client.get(
        "/connector-jobs",
        params={
            "status": "active",
            "due_before": (expected_next_run_at + timedelta(seconds=1)).isoformat(),
        },
    ).json()
    assert [job["id"] for job in future_due_jobs] == ["connector-job-supplier-followup"]

    runs = client.get(
        "/connector-job-runs",
        params={"job_id": "connector-job-supplier-followup"},
    ).json()
    assert [run["id"] for run in runs] == [run_result["run"]["id"]]

    stop_response = client.post(
        "/connector-jobs/connector-job-supplier-followup/stop",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-ops-sourcing-live",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "stopped_by_type": "agent",
            "stopped_by_id": "agent-ops-sourcing-live",
            "reason": "Supplier replied; stop follow-up loop.",
        },
    )

    assert stop_response.status_code == 200
    stopped = stop_response.json()
    assert stopped["job"]["status"] == "stopped"
    assert stopped["event"]["type"] == "connector_job.stopped"
    assert stopped["audit_log"]["action"] == "connector_job.stopped"

    repeat_run = client.post(
        "/connector-jobs/connector-job-supplier-followup/runs",
        json={
            "status": "completed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
        },
    )
    assert repeat_run.status_code == 409

    resume_response = client.post(
        "/connector-jobs/connector-job-supplier-followup/resume",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "resumed_by_type": "user",
            "resumed_by_id": "local-user",
            "reason": "Manual resume for another controlled follow-up.",
        },
    )

    assert resume_response.status_code == 200
    resumed = resume_response.json()
    assert resumed["job"]["status"] == "active"
    assert resumed["job"]["stopped_at"] is None
    assert resumed["job"]["next_run_at"] is not None
    assert resumed["event"]["type"] == "connector_job.resumed"
    assert resumed["audit_log"]["action"] == "connector_job.resumed"

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [
        event["type"]
        for event in events
        if event["type"].startswith("connector_job.")
    ] == [
        "connector_job.created",
        "connector_job.run_recorded",
        "connector_job.stopped",
        "connector_job.resumed",
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert {
        "connector_job.created",
        "connector_job.run_recorded",
        "connector_job.stopped",
        "connector_job.resumed",
    }.issubset({audit["action"] for audit in audits})


def test_connector_job_run_policy_stops_on_output_or_max_runs() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_job_run_policy"
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-ops-policy",
            "name": "IA Ops Policy",
            "role": "Supplier follow-up policy",
            "division": "ops-sourcing",
        },
    )
    assert agent_response.status_code == 201
    service_response = client.post(
        "/services",
        json={
            "id": "connector-supplier-policy",
            "name": "Supplier Policy Connector",
            "kind": "tool_provider",
            "capabilities": ["web.fetch"],
            "allowed_divisions": ["ops-sourcing"],
        },
    )
    assert service_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier policy",
            "goal": "Stop connector jobs when their objective or attempt limit is reached.",
            "owner_agent_id": "agent-ops-policy",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    def create_policy_job(
        job_id: str,
        task_title: str,
        metadata: dict[str, object],
    ) -> None:
        task_response = client.post(
            "/tasks",
            json=task_payload(
                project_id,
                task_title,
                assigned_agent_id="agent-ops-policy",
                required_tools=["web.fetch"],
            ),
        )
        assert task_response.status_code == 201
        job_response = client.post(
            "/connector-jobs",
            headers={
                "X-Synarch-Actor-Type": "agent",
                "X-Synarch-Actor-Id": "agent-ops-policy",
                "X-Synarch-Trace-Id": trace_id,
            },
            json={
                "id": job_id,
                "service_id": "connector-supplier-policy",
                "project_id": project_id,
                "task_id": task_response.json()["id"],
                "owner_agent_id": "agent-ops-policy",
                "kind": "cron",
                "schedule": "*/15 * * * *",
                "purpose": f"Run policy job {job_id}.",
                "created_by_type": "agent",
                "created_by_id": "agent-ops-policy",
                "metadata": metadata,
            },
        )
        assert job_response.status_code == 201

    create_policy_job(
        "connector-job-output-stop",
        "Stop when supplier replied",
        {"stop_condition": "supplier replied", "cooldown_seconds": 60},
    )
    output_stop_response = client.post(
        "/connector-jobs/connector-job-output-stop/runs",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "connector-job-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "status": "completed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {
                "stop_condition_met": True,
                "stop_reason": "Supplier replied on WhatsApp.",
            },
        },
    )
    assert output_stop_response.status_code == 201
    output_job = client.get("/connector-jobs/connector-job-output-stop").json()
    assert output_job["status"] == "stopped"
    assert output_job["next_run_at"] is None
    assert output_job["stopped_at"] is not None

    create_policy_job(
        "connector-job-max-runs",
        "Stop after first attempt",
        {"max_runs": 1, "cooldown_seconds": 60},
    )
    max_runs_response = client.post(
        "/connector-jobs/connector-job-max-runs/runs",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "connector-job-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "status": "completed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {"attempt": 1, "result": "no supplier reply"},
        },
    )
    assert max_runs_response.status_code == 201
    max_runs_job = client.get("/connector-jobs/connector-job-max-runs").json()
    assert max_runs_job["status"] == "stopped"
    assert max_runs_job["next_run_at"] is None
    assert max_runs_job["stopped_at"] is not None

    active_jobs = client.get(
        "/connector-jobs",
        params={"project_id": project_id, "status": "active"},
    ).json()
    assert active_jobs == []
    repeat_run = client.post(
        "/connector-jobs/connector-job-output-stop/runs",
        json={
            "status": "completed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
        },
    )
    assert repeat_run.status_code == 409

    events = client.get("/events", params={"trace_id": trace_id}).json()
    stopped_events = [
        event for event in events if event["type"] == "connector_job.stopped"
    ]
    assert [event["payload"]["reason"] for event in stopped_events] == [
        "Supplier replied on WhatsApp.",
        "Connector job reached max_runs=1.",
    ]
    assert [event["payload"]["stopped_by_run_id"] for event in stopped_events]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    stopped_audits = [
        audit for audit in audits if audit["action"] == "connector_job.stopped"
    ]
    assert [audit["payload"]["reason"] for audit in stopped_audits] == [
        "Supplier replied on WhatsApp.",
        "Connector job reached max_runs=1.",
    ]


def test_connector_job_failure_policy_backs_off_and_stops_after_max_failures() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_job_failure_policy"
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-ops-failure-policy",
            "name": "IA Ops Failure Policy",
            "role": "Supplier retry owner",
            "division": "ops-sourcing",
        },
    )
    assert agent_response.status_code == 201
    service_response = client.post(
        "/services",
        json={
            "id": "connector-supplier-failure-policy",
            "name": "Supplier Failure Connector",
            "kind": "tool_provider",
            "capabilities": ["web.fetch"],
            "allowed_divisions": ["ops-sourcing"],
        },
    )
    assert service_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier failure policy",
            "goal": "Back off failed connector jobs and stop after bounded failures.",
            "owner_agent_id": "agent-ops-failure-policy",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_id,
            "Retry supplier fetch failures",
            assigned_agent_id="agent-ops-failure-policy",
            required_tools=["web.fetch"],
        ),
    )
    assert task_response.status_code == 201
    job_response = client.post(
        "/connector-jobs",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-ops-failure-policy",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "connector-job-failure-policy",
            "service_id": "connector-supplier-failure-policy",
            "project_id": project_id,
            "task_id": task_response.json()["id"],
            "owner_agent_id": "agent-ops-failure-policy",
            "kind": "cron",
            "schedule": "*/5 * * * *",
            "purpose": "Retry failed supplier fetches with a bounded failure budget.",
            "created_by_type": "agent",
            "created_by_id": "agent-ops-failure-policy",
            "metadata": {
                "cooldown_seconds": 300,
                "failure_cooldown_seconds": 45,
                "max_failures": 2,
            },
        },
    )
    assert job_response.status_code == 201

    first_failure = client.post(
        "/connector-jobs/connector-job-failure-policy/runs",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "connector-job-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "status": "failed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {"attempt": 1, "retryable": True},
            "error": "Supplier site timed out.",
        },
    )
    assert first_failure.status_code == 201
    first_run = first_failure.json()["run"]
    expected_retry_at = parse_timestamp(first_run["completed_at"]) + timedelta(seconds=45)
    retrying_job = client.get("/connector-jobs/connector-job-failure-policy").json()
    assert retrying_job["status"] == "active"
    assert parse_timestamp(retrying_job["next_run_at"]) == expected_retry_at

    not_due_jobs = client.get(
        "/connector-jobs",
        params={
            "project_id": project_id,
            "status": "active",
            "due_before": datetime.now(UTC).isoformat(),
        },
    ).json()
    assert not_due_jobs == []
    future_due_jobs = client.get(
        "/connector-jobs",
        params={
            "project_id": project_id,
            "status": "active",
            "due_before": (expected_retry_at + timedelta(seconds=1)).isoformat(),
        },
    ).json()
    assert [job["id"] for job in future_due_jobs] == ["connector-job-failure-policy"]

    second_failure = client.post(
        "/connector-jobs/connector-job-failure-policy/runs",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "connector-job-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "status": "failed",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {"attempt": 2, "retryable": False},
            "error": "Supplier site still times out.",
        },
    )
    assert second_failure.status_code == 201
    stopped_job = client.get("/connector-jobs/connector-job-failure-policy").json()
    assert stopped_job["status"] == "stopped"
    assert stopped_job["next_run_at"] is None
    assert stopped_job["stopped_at"] is not None

    events = client.get("/events", params={"trace_id": trace_id}).json()
    stopped_events = [
        event for event in events if event["type"] == "connector_job.stopped"
    ]
    assert [event["payload"]["reason"] for event in stopped_events] == [
        "Connector job reached max_failures=2."
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    stopped_audits = [
        audit for audit in audits if audit["action"] == "connector_job.stopped"
    ]
    assert [audit["payload"]["reason"] for audit in stopped_audits] == [
        "Connector job reached max_failures=2."
    ]


def test_connector_job_blocked_run_stops_for_human_review() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_job_blocked_policy"
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-ops-blocked-policy",
            "name": "IA Ops Blocked Policy",
            "role": "Supplier blocked-run owner",
            "division": "ops-sourcing",
        },
    )
    assert agent_response.status_code == 201
    service_response = client.post(
        "/services",
        json={
            "id": "connector-supplier-blocked-policy",
            "name": "Supplier Blocked Connector",
            "kind": "tool_provider",
            "capabilities": ["web.extract"],
            "allowed_divisions": ["ops-sourcing"],
        },
    )
    assert service_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier blocked policy",
            "goal": "Stop connector jobs that require human review.",
            "owner_agent_id": "agent-ops-blocked-policy",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_id,
            "Review supplier protection page",
            assigned_agent_id="agent-ops-blocked-policy",
            required_tools=["web.extract"],
        ),
    )
    assert task_response.status_code == 201
    job_response = client.post(
        "/connector-jobs",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-ops-blocked-policy",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "connector-job-blocked-policy",
            "service_id": "connector-supplier-blocked-policy",
            "project_id": project_id,
            "task_id": task_response.json()["id"],
            "owner_agent_id": "agent-ops-blocked-policy",
            "kind": "cron",
            "schedule": "*/5 * * * *",
            "purpose": "Retry supplier extraction unless human review is required.",
            "created_by_type": "agent",
            "created_by_id": "agent-ops-blocked-policy",
            "metadata": {"cooldown_seconds": 60},
        },
    )
    assert job_response.status_code == 201

    missing_error_response = client.post(
        "/connector-jobs/connector-job-blocked-policy/runs",
        json={
            "status": "blocked",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {"requires_human_review": True},
        },
    )
    assert missing_error_response.status_code == 400
    assert missing_error_response.json()["detail"] == (
        "Blocked connector job runs require error"
    )

    blocked_response = client.post(
        "/connector-jobs/connector-job-blocked-policy/runs",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "connector-job-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "status": "blocked",
            "triggered_by_type": "service",
            "triggered_by_id": "connector-job-runner",
            "output": {
                "requires_human_review": True,
                "blocked_reason": "captcha_or_human_verification",
            },
            "error": "captcha_or_human_verification",
        },
    )
    assert blocked_response.status_code == 201
    run = blocked_response.json()["run"]
    assert run["status"] == "blocked"
    blocked_job = client.get("/connector-jobs/connector-job-blocked-policy").json()
    assert blocked_job["status"] == "stopped"
    assert blocked_job["next_run_at"] is None
    assert blocked_job["stopped_at"] is not None
    blocked_jobs = client.get(
        "/connector-jobs",
        params={"project_id": project_id, "last_run_status": "blocked"},
    ).json()
    assert [job["id"] for job in blocked_jobs] == ["connector-job-blocked-policy"]
    failed_jobs = client.get(
        "/connector-jobs",
        params={"project_id": project_id, "last_run_status": "failed"},
    ).json()
    assert failed_jobs == []

    events = client.get("/events", params={"trace_id": trace_id}).json()
    stopped_events = [
        event for event in events if event["type"] == "connector_job.stopped"
    ]
    assert [event["payload"]["reason"] for event in stopped_events] == [
        "Connector job blocked and requires human review."
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    stopped_audits = [
        audit for audit in audits if audit["action"] == "connector_job.stopped"
    ]
    assert [audit["payload"]["reason"] for audit in stopped_audits] == [
        "Connector job blocked and requires human review."
    ]


def test_connector_job_tick_records_bounded_skipped_runs_and_audits() -> None:
    client = TestClient(app)
    trace_id = "trace_connector_job_tick"
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-ops-tick",
            "name": "IA Ops Tick",
            "role": "Connector job owner",
            "division": "ops-sourcing",
        },
    )
    assert agent_response.status_code == 201
    service_response = client.post(
        "/services",
        json={
            "id": "connector-supplier-tick",
            "name": "Supplier Tick Connector",
            "kind": "tool_provider",
            "capabilities": ["web.fetch"],
            "allowed_divisions": ["ops-sourcing"],
        },
    )
    assert service_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "title": "Supplier tick",
            "goal": "Record bounded connector ticks without fake adapter execution.",
            "owner_agent_id": "agent-ops-tick",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    task_ids = []
    for title in ["Follow supplier A", "Follow supplier B", "Receive webhook"]:
        task_response = client.post(
            "/tasks",
            json=task_payload(
                project_id,
                title,
                assigned_agent_id="agent-ops-tick",
                required_tools=["web.fetch"],
            ),
        )
        assert task_response.status_code == 201
        task_ids.append(task_response.json()["id"])

    for job_payload in [
        {
            "id": "connector-job-cron-a",
            "task_id": task_ids[0],
            "kind": "cron",
            "schedule": "*/15 * * * *",
            "purpose": "Check supplier A replies.",
        },
        {
            "id": "connector-job-cron-b",
            "task_id": task_ids[1],
            "kind": "cron",
            "schedule": "*/30 * * * *",
            "purpose": "Check supplier B replies.",
        },
        {
            "id": "connector-job-webhook",
            "task_id": task_ids[2],
            "kind": "webhook",
            "webhook_path": "/webhooks/supplier",
            "purpose": "Receive supplier webhook replies.",
        },
    ]:
        job_response = client.post(
            "/connector-jobs",
            headers={
                "X-Synarch-Actor-Type": "agent",
                "X-Synarch-Actor-Id": "agent-ops-tick",
                "X-Synarch-Trace-Id": trace_id,
            },
            json={
                "service_id": "connector-supplier-tick",
                "project_id": project_id,
                "owner_agent_id": "agent-ops-tick",
                "created_by_type": "agent",
                "created_by_id": "agent-ops-tick",
                **job_payload,
            },
        )
        assert job_response.status_code == 201

    tick_response = client.post(
        "/connector-jobs/tick",
        headers={"X-Synarch-Trace-Id": trace_id},
        params={"max_jobs": 1, "kind": "cron"},
    )

    assert tick_response.status_code == 200
    tick = tick_response.json()
    assert tick["trace_id"] == trace_id
    assert tick["max_jobs"] == 1
    assert tick["kind"] == "cron"
    assert tick["stop_reason"] == "max_jobs_reached"
    assert len(tick["runs"]) == 1
    run = tick["runs"][0]["run"]
    assert run["job_id"] in {"connector-job-cron-a", "connector-job-cron-b"}
    assert run["status"] == "skipped"
    assert run["triggered_by_type"] == "service"
    assert run["triggered_by_id"] == "connector-job-runner"
    assert run["output"]["executed"] is False
    assert run["output"]["adapter_required"] is True
    assert run["output"]["reason"] == "connector adapter execution is not wired yet"
    assert tick["tick_event"]["type"] == "connector_job.tick"
    assert tick["tick_audit_log"]["action"] == "connector_job.tick"
    assert tick["tick_event"]["payload"]["connector_job_ids"] == [run["job_id"]]
    assert tick["tick_event"]["payload"]["run_statuses"] == ["skipped"]
    assert tick["tick_event"]["payload"]["completed_run_count"] == 0
    assert tick["tick_event"]["payload"]["failed_run_count"] == 0
    assert tick["tick_event"]["payload"]["blocked_run_count"] == 0
    assert tick["tick_event"]["payload"]["skipped_run_count"] == 1

    runs = client.get("/connector-job-runs", params={"status": "skipped"}).json()
    assert [record["id"] for record in runs] == [run["id"]]
    assert runs[0]["job_id"] != "connector-job-webhook"

    events = client.get("/events", params={"trace_id": trace_id}).json()
    connector_event_types = [
        event["type"] for event in events if event["type"].startswith("connector_job.")
    ]
    assert "connector_job.run_recorded" in connector_event_types
    assert connector_event_types[-1] == "connector_job.tick"
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert "connector_job.tick" in {audit["action"] for audit in audits}


def test_task_requires_acceptance_criteria() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Reject vague task",
            "goal": "Tasks must be debuggable units",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    task_response = client.post(
        "/tasks",
        json={
            "project_id": project_response.json()["id"],
            "title": "Do everything",
            "assigned_agent_id": "agent-dev",
        },
    )

    assert task_response.status_code == 400
    assert task_response.json()["detail"] == "Task requires at least one acceptance criterion"


def test_task_start_updates_status_and_writes_event_and_audit() -> None:
    client = TestClient(app)
    trace_id = "trace_task_started"
    project_response = client.post(
        "/projects",
        json={
            "title": "Start queued task",
            "goal": "Move a task from queued to running",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(project_response.json()["id"], "Run this task"),
    )
    assert task_response.status_code == 201
    task = task_response.json()

    start_response = client.post(
        f"/tasks/{task['id']}/start",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-task-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
    )

    assert start_response.status_code == 200
    started_task = start_response.json()
    assert started_task["status"] == "running"
    assert started_task["attempt_count"] == 1
    assert started_task["lease_owner_id"] == "gateway-task-runner"
    assert started_task["lease_expires_at"] is not None
    assert started_task["last_heartbeat_at"] is not None

    events_response = client.get("/events", params={"trace_id": trace_id})
    assert events_response.status_code == 200
    events = events_response.json()
    assert [event["type"] for event in events] == ["task.started"]
    assert events[0]["payload"]["task_id"] == task["id"]

    audit_response = client.get("/audit-logs", params={"trace_id": trace_id})
    assert audit_response.status_code == 200
    audit = audit_response.json()[0]
    assert audit["actor_type"] == "service"
    assert audit["action"] == "task.started"
    assert audit["target_id"] == task["id"]


def test_task_heartbeat_extends_running_task_lease() -> None:
    client = TestClient(app)
    trace_id = "trace_task_heartbeat"
    project_response = client.post(
        "/projects",
        json={
            "title": "Heartbeat running task",
            "goal": "Extend a running task lease.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(project_response.json()["id"], "Heartbeat me"),
    )
    assert task_response.status_code == 201
    task = task_response.json()
    headers = {
        "X-Synarch-Actor-Type": "service",
        "X-Synarch-Actor-Id": "gateway-task-runner",
        "X-Synarch-Trace-Id": trace_id,
        "X-Synarch-Task-Lease-Seconds": "60",
    }
    start_response = client.post(f"/tasks/{task['id']}/start", headers=headers)
    assert start_response.status_code == 200
    first_lease_expires_at = start_response.json()["lease_expires_at"]

    heartbeat_response = client.post(
        f"/tasks/{task['id']}/heartbeat",
        headers={**headers, "X-Synarch-Task-Lease-Seconds": "120"},
    )

    assert heartbeat_response.status_code == 200
    heartbeat_task = heartbeat_response.json()
    assert heartbeat_task["status"] == "running"
    assert heartbeat_task["lease_owner_id"] == "gateway-task-runner"
    assert heartbeat_task["lease_expires_at"] > first_lease_expires_at

    events = client.get("/events", params={"trace_id": trace_id}).json()
    audit_logs = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == ["task.started", "task.heartbeat"]
    assert [audit["action"] for audit in audit_logs] == ["task.started", "task.heartbeat"]


def test_task_start_conflict_does_not_write_duplicate_event_or_audit() -> None:
    client = TestClient(app)
    trace_id = "trace_task_start_conflict"
    project_response = client.post(
        "/projects",
        json={
            "title": "Start conflict",
            "goal": "Only one scheduler should claim a task.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(project_response.json()["id"], "Claim once"),
    )
    assert task_response.status_code == 201
    task = task_response.json()

    headers = {
        "X-Synarch-Actor-Type": "service",
        "X-Synarch-Actor-Id": "gateway-task-runner",
        "X-Synarch-Trace-Id": trace_id,
    }
    first_start = client.post(f"/tasks/{task['id']}/start", headers=headers)
    second_start = client.post(f"/tasks/{task['id']}/start", headers=headers)

    assert first_start.status_code == 200
    assert second_start.status_code == 409
    assert second_start.json()["detail"] == "Task is already running"

    events = client.get("/events", params={"trace_id": trace_id}).json()
    audit_logs = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == ["task.started"]
    assert [audit["action"] for audit in audit_logs] == ["task.started"]


def test_task_start_rejects_retry_backoff_window() -> None:
    client = TestClient(app)
    trace_id = "trace_task_retry_backoff"
    project_response = client.post(
        "/projects",
        json={
            "title": "Retry backoff",
            "goal": "Do not restart a queued retry too early.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    retry_after_at = datetime.now(UTC) + timedelta(minutes=5)
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Wait before retry",
            attempt_count=1,
            retry_after_at=retry_after_at.isoformat(),
        ),
    )
    assert task_response.status_code == 201

    start_response = client.post(
        f"/tasks/{task_response.json()['id']}/start",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-task-runner",
            "X-Synarch-Trace-Id": trace_id,
        },
    )

    assert start_response.status_code == 409
    assert start_response.json()["detail"].startswith("Task retry backoff has not elapsed:")
    assert client.get("/events", params={"trace_id": trace_id}).json() == []


def test_recover_expired_task_lease_requeues_when_attempts_remain() -> None:
    client = TestClient(app)
    trace_id = "trace_task_lease_retry"
    expired_at = datetime.now(UTC) - timedelta(seconds=30)
    project_response = client.post(
        "/projects",
        json={
            "title": "Recover expired lease",
            "goal": "Requeue an expired running task while attempts remain.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Retry expired task",
            status="running",
            attempt_count=1,
            max_attempts=3,
            lease_owner_id="gateway-task-runner",
            lease_expires_at=expired_at.isoformat(),
            last_heartbeat_at=(expired_at - timedelta(seconds=60)).isoformat(),
        ),
    )
    assert task_response.status_code == 201

    recovery_response = client.post(
        "/tasks/recover-expired-leases",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-scheduler",
            "X-Synarch-Trace-Id": trace_id,
            "X-Synarch-Task-Retry-Backoff-Seconds": "90",
        },
    )

    assert recovery_response.status_code == 200
    recovery = recovery_response.json()
    assert recovery["recovered_task_ids"] == [task_response.json()["id"]]
    assert recovery["failed_task_ids"] == []
    recovered_task = recovery["recovered_tasks"][0]
    assert recovered_task["status"] == "queued"
    assert recovered_task["attempt_count"] == 1
    assert recovered_task["lease_owner_id"] is None
    assert recovered_task["lease_expires_at"] is None
    assert recovered_task["retry_after_at"] is not None
    assert recovered_task["dead_letter_reason"] is None
    assert recovered_task["dead_lettered_at"] is None

    events = client.get("/events", params={"trace_id": trace_id}).json()
    audit_logs = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == ["task.lease_expired"]
    assert events[0]["payload"]["will_retry"] is True
    assert parse_timestamp(events[0]["payload"]["retry_after_at"]) == parse_timestamp(
        recovered_task["retry_after_at"]
    )
    assert [audit["action"] for audit in audit_logs] == ["task.lease_expired"]


def test_recover_expired_task_lease_needs_review_after_max_attempts() -> None:
    client = TestClient(app)
    trace_id = "trace_task_lease_failed"
    expired_at = datetime.now(UTC) - timedelta(seconds=30)
    project_response = client.post(
        "/projects",
        json={
            "title": "Fail expired lease",
            "goal": "Fail an expired running task after max attempts.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Fail expired task",
            status="running",
            attempt_count=2,
            max_attempts=2,
            lease_owner_id="gateway-task-runner",
            lease_expires_at=expired_at.isoformat(),
            last_heartbeat_at=(expired_at - timedelta(seconds=60)).isoformat(),
        ),
    )
    assert task_response.status_code == 201

    recovery_response = client.post(
        "/tasks/recover-expired-leases",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-scheduler",
            "X-Synarch-Trace-Id": trace_id,
        },
    )

    assert recovery_response.status_code == 200
    recovery = recovery_response.json()
    assert recovery["recovered_task_ids"] == []
    assert recovery["failed_task_ids"] == [task_response.json()["id"]]
    failed_task = recovery["failed_tasks"][0]
    assert failed_task["status"] == "needs_review"
    assert failed_task["result"]["reason"] == "lease_expired"
    assert failed_task["lease_owner_id"] is None
    assert failed_task["retry_after_at"] is None
    assert failed_task["dead_letter_reason"] == "lease_expired"
    assert failed_task["dead_lettered_at"] is not None

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert events[0]["payload"]["will_retry"] is False
    assert events[0]["payload"]["dead_letter_reason"] == "lease_expired"


def test_task_review_queue_lists_reviewable_tasks() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Review queue",
            "goal": "List tasks waiting for human review.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Needs review",
            status="needs_review",
            dead_letter_reason="lease_expired",
            dead_lettered_at=datetime.now(UTC).isoformat(),
        ),
    )
    assert task_response.status_code == 201
    blocked_task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Blocked web extraction",
            status="blocked",
            result={"summary": "web.extract returned http_access_denied."},
        ),
    )
    assert blocked_task_response.status_code == 201
    queued_task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Queued task",
            status="queued",
        ),
    )
    assert queued_task_response.status_code == 201

    review_response = client.get(
        "/tasks/review-queue",
        params={"project_id": project_response.json()["id"]},
    )

    assert review_response.status_code == 200
    assert [task["id"] for task in review_response.json()] == [
        task_response.json()["id"],
        blocked_task_response.json()["id"],
    ]


def test_task_review_retry_updates_task_and_allows_start() -> None:
    client = TestClient(app)
    trace_id = "trace_task_review_retry"
    project_response = client.post(
        "/projects",
        json={
            "title": "Retry review",
            "goal": "Human reviewer fixes a dead-lettered task.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Old title",
            status="needs_review",
            attempt_count=2,
            max_attempts=2,
            result={"reason": "lease_expired"},
            dead_letter_reason="lease_expired",
            dead_lettered_at=datetime.now(UTC).isoformat(),
        ),
    )
    assert task_response.status_code == 201

    review_response = client.post(
        f"/tasks/{task_response.json()['id']}/review-decisions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "hugo",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "action": "retry",
            "reason": "Acceptance criteria clarified after lease expiry.",
            "title": "Clarified retry task",
            "acceptance_criteria": ["Retry has a specific expected output."],
        },
    )

    assert review_response.status_code == 200
    review = review_response.json()
    reviewed_task = review["task"]
    assert reviewed_task["status"] == "queued"
    assert reviewed_task["title"] == "Clarified retry task"
    assert reviewed_task["acceptance_criteria"] == ["Retry has a specific expected output."]
    assert reviewed_task["max_attempts"] == 3
    assert reviewed_task["dead_letter_reason"] is None
    assert reviewed_task["dead_lettered_at"] is None
    assert reviewed_task["result"]["review"]["action"] == "retry"
    assert review["event"]["type"] == "task.reviewed"
    assert review["audit_log"]["action"] == "task.reviewed"

    start_response = client.post(f"/tasks/{reviewed_task['id']}/start")
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "running"


def test_task_review_retry_accepts_blocked_task() -> None:
    client = TestClient(app)
    trace_id = "trace_task_review_blocked_retry"
    project_response = client.post(
        "/projects",
        json={
            "title": "Blocked review",
            "goal": "Human reviewer can resume blocked work.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Blocked extraction",
            status="blocked",
            attempt_count=1,
            max_attempts=1,
            result={
                "summary": "web.extract blocked with http_access_denied.",
                "tool_results": [
                    {
                        "tool_name": "web.extract",
                        "status": "blocked",
                        "error": "http_access_denied",
                    }
                ],
            },
            dead_letter_reason="web_extract_blocked",
            dead_lettered_at=datetime.now(UTC).isoformat(),
        ),
    )
    assert task_response.status_code == 201

    review_response = client.post(
        f"/tasks/{task_response.json()['id']}/review-decisions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "hugo",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "action": "retry",
            "reason": "Human reviewed the blocked evidence and provided a safer retry path.",
            "description": "Retry with the reviewed source evidence and summarize the blocker.",
            "acceptance_criteria": ["The retry uses the reviewed blocker context."],
        },
    )

    assert review_response.status_code == 200
    review = review_response.json()
    reviewed_task = review["task"]
    assert reviewed_task["status"] == "queued"
    assert reviewed_task["max_attempts"] == 2
    assert reviewed_task["dead_letter_reason"] is None
    assert reviewed_task["dead_lettered_at"] is None
    assert reviewed_task["result"]["review"]["action"] == "retry"
    assert reviewed_task["result"]["review"]["next_status"] == "queued"
    assert review["event"]["payload"]["previous_status"] == "blocked"
    assert review["event"]["payload"]["next_status"] == "queued"

    start_response = client.post(f"/tasks/{reviewed_task['id']}/start")
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "running"


def test_task_review_cancel_marks_failed() -> None:
    client = TestClient(app)
    trace_id = "trace_task_review_cancel"
    project_response = client.post(
        "/projects",
        json={
            "title": "Cancel review",
            "goal": "Human reviewer cancels unhelpful work.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Cancel me",
            status="needs_review",
            dead_letter_reason="lease_expired",
            dead_lettered_at=datetime.now(UTC).isoformat(),
        ),
    )
    assert task_response.status_code == 201

    review_response = client.post(
        f"/tasks/{task_response.json()['id']}/review-decisions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "hugo",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={"action": "cancel", "reason": "The task is no longer useful."},
    )

    assert review_response.status_code == 200
    reviewed_task = review_response.json()["task"]
    assert reviewed_task["status"] == "failed"
    assert reviewed_task["dead_letter_reason"] == "lease_expired"
    assert reviewed_task["result"]["review"]["action"] == "cancel"

    events = client.get("/events", params={"trace_id": trace_id}).json()
    audit_logs = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == ["task.reviewed"]
    assert events[0]["payload"]["next_status"] == "failed"
    assert [audit["action"] for audit in audit_logs] == ["task.reviewed"]


def test_task_review_update_keeps_task_in_review() -> None:
    client = TestClient(app)
    trace_id = "trace_task_review_update"
    project_response = client.post(
        "/projects",
        json={
            "title": "Update review",
            "goal": "Human reviewer edits task details before retry.",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Needs edit",
            status="needs_review",
            dead_letter_reason="lease_expired",
            dead_lettered_at=datetime.now(UTC).isoformat(),
        ),
    )
    assert task_response.status_code == 201

    review_response = client.post(
        f"/tasks/{task_response.json()['id']}/review-decisions",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "hugo",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "action": "update",
            "reason": "Split the expected output more clearly.",
            "description": "Updated review details.",
            "acceptance_criteria": ["The expected output is precise."],
        },
    )

    assert review_response.status_code == 200
    reviewed_task = review_response.json()["task"]
    assert reviewed_task["status"] == "needs_review"
    assert reviewed_task["description"] == "Updated review details."
    assert reviewed_task["acceptance_criteria"] == ["The expected output is precise."]
    assert reviewed_task["result"]["review"]["next_status"] == "needs_review"


def test_events_are_listed_chronologically_for_trace() -> None:
    client = TestClient(app)
    trace_id = "trace-event-order"

    late_response = client.post(
        "/events",
        json={
            "id": "event_late",
            "type": "task.completed",
            "target": "project-demo",
            "timestamp": "2026-05-03T12:00:02Z",
            "trace_id": trace_id,
        },
    )
    early_response = client.post(
        "/events",
        json={
            "id": "event_early",
            "type": "task.started",
            "target": "project-demo",
            "timestamp": "2026-05-03T12:00:01Z",
            "trace_id": trace_id,
        },
    )

    assert late_response.status_code == 201
    assert early_response.status_code == 201
    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["id"] for event in events] == ["event_early", "event_late"]


def test_task_start_rejects_incomplete_dependencies() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Dependency gate",
            "goal": "Do not start tasks before dependencies are completed",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()
    first_task_response = client.post(
        "/tasks",
        json=task_payload(project["id"], "Dependency", "agent-direction"),
    )
    assert first_task_response.status_code == 201
    second_task_response = client.post(
        "/tasks",
        json=task_payload(
            project["id"],
            "Blocked by dependency",
            depends_on=[first_task_response.json()["id"]],
        ),
    )
    assert second_task_response.status_code == 201

    start_response = client.post(f"/tasks/{second_task_response.json()['id']}/start")

    assert start_response.status_code == 409
    assert start_response.json()["detail"].startswith("Task dependencies are not completed:")


def test_task_result_updates_task_and_writes_event_and_audit() -> None:
    client = TestClient(app)
    trace_id = "trace_task_result_recorded"

    project_response = client.post(
        "/projects",
        json={
            "title": "Runtime result persistence",
            "goal": "Record agent execution output against the task",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()

    task_response = client.post(
        "/tasks",
        json=task_payload(project["id"], "Prepare deterministic result"),
    )
    assert task_response.status_code == 201
    task = task_response.json()

    result_response = client.post(
        f"/tasks/{task['id']}/results",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-dev",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "agent_id": "agent-dev",
            "task_id": task["id"],
            "status": "needs_review",
            "actions_taken": ["Loaded LocalWorldView", "Prepared execution plan"],
            "events_emitted": [
                {
                    "type": "agent.reported",
                    "payload": {"mode": "stub-runtime"},
                }
            ],
            "summary": "Runtime stub prepared the task for review.",
        },
    )

    assert result_response.status_code == 200
    updated_task = result_response.json()
    assert updated_task["status"] == "needs_review"
    assert updated_task["result"]["summary"] == "Runtime stub prepared the task for review."
    assert updated_task["result"]["actions_taken"] == [
        "Loaded LocalWorldView",
        "Prepared execution plan",
    ]

    events_response = client.get("/events", params={"trace_id": trace_id})
    assert events_response.status_code == 200
    events = events_response.json()
    assert [event["type"] for event in events] == ["agent.reported"]
    assert events[0]["source_agent_id"] == "agent-dev"
    assert events[0]["target"] == project["id"]
    assert events[0]["payload"]["task_id"] == task["id"]

    audit_response = client.get("/audit-logs", params={"trace_id": trace_id})
    assert audit_response.status_code == 200
    audit = audit_response.json()[0]
    assert audit["actor_type"] == "agent"
    assert audit["actor_id"] == "agent-dev"
    assert audit["action"] == "task.result_recorded"
    assert audit["target_id"] == task["id"]


def test_task_result_rejects_wrong_agent() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "title": "Reject wrong agent result",
            "goal": "Only the assigned agent can record a task result",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload(project_response.json()["id"], "Wrong agent must fail"),
    )
    assert task_response.status_code == 201
    task = task_response.json()

    result_response = client.post(
        f"/tasks/{task['id']}/results",
        json={
            "agent_id": "agent-finance",
            "task_id": task["id"],
            "status": "completed",
            "summary": "This agent is not assigned.",
        },
    )

    assert result_response.status_code == 400
    assert (
        result_response.json()["detail"] == "Result agent does not match assigned agent: agent-dev"
    )


def test_state_change_with_actor_headers_writes_audit_log() -> None:
    client = TestClient(app)
    trace_id = "trace_actor_project_create"

    project_response = client.post(
        "/projects",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "title": "Audited project",
            "goal": "Create a project and automatically capture the audit trail",
            "owner_agent_id": "agent-direction",
        },
    )

    assert project_response.status_code == 201
    project = project_response.json()

    audit_response = client.get("/audit-logs", params={"trace_id": trace_id})

    assert audit_response.status_code == 200
    audit = audit_response.json()[0]
    assert audit["actor_id"] == "local-user"
    assert audit["action"] == "project.created"
    assert audit["target_type"] == "project"
    assert audit["target_id"] == project["id"]


def test_audit_logs_support_action_prefix_and_limit_filters() -> None:
    client = TestClient(app)
    trace_id = "trace_audit_filter"

    for index, action in enumerate(
        [
            "connector_connection.created",
            "work_queue.item_created",
            "work_queue.reviewed",
        ]
    ):
        response = client.post(
            "/audit-logs",
            json={
                "id": f"audit-filter-{index}",
                "actor_type": "user",
                "actor_id": "local-user",
                "action": action,
                "target_type": "audit_filter",
                "target_id": f"target-{index}",
                "payload": {},
                "trace_id": trace_id,
                "created_at": f"2026-05-27T10:00:0{index}Z",
            },
        )
        assert response.status_code == 201

    audit_response = client.get(
        "/audit-logs",
        params={
            "trace_id": trace_id,
            "action_prefix": "work_queue.",
            "limit": 1,
        },
    )

    assert audit_response.status_code == 200
    audits = audit_response.json()
    assert [audit["action"] for audit in audits] == ["work_queue.reviewed"]


def test_agent_soul_flow_records_identity_event_and_audit() -> None:
    client = TestClient(app)
    trace_id = "trace_agent_soul_created"
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-finance",
            "name": "IA Finance",
            "role": "Compta, TVA, factures",
            "division": "finance",
            "manager_id": "agent-direction",
        },
    )
    assert agent_response.status_code == 201

    soul_response = client.post(
        "/agent-souls",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-direction",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "soul-agent-finance-v1",
            "agent_id": "agent-finance",
            "identity": "IA Finance is the finance service manager.",
            "mission": "Coordinate accounting work and keep payment execution out of scope.",
            "responsibilities": ["Review invoices"],
            "operating_principles": ["Keep financial decisions auditable"],
            "boundaries": ["Never execute payments"],
            "escalation_rules": ["Escalate payment anomalies to IA Direction"],
            "created_by": "agent-direction",
        },
    )

    assert soul_response.status_code == 201
    soul = soul_response.json()
    assert soul["active"] is True
    assert soul["identity"].startswith("IA Finance")

    active_soul_response = client.get("/agents/agent-finance/soul")
    assert active_soul_response.status_code == 200
    assert active_soul_response.json()["id"] == "soul-agent-finance-v1"

    duplicate_response = client.post(
        "/agent-souls",
        json={
            "id": "soul-agent-finance-v2",
            "agent_id": "agent-finance",
            "identity": "Updated identity.",
            "mission": "Updated mission.",
            "created_by": "agent-direction",
        },
    )
    assert duplicate_response.status_code == 409

    events_response = client.get("/events", params={"trace_id": trace_id})
    assert events_response.status_code == 200
    events = events_response.json()
    assert [event["type"] for event in events] == ["agent_soul.created"]
    assert events[0]["target"] == "agent-finance"

    audit_response = client.get("/audit-logs", params={"trace_id": trace_id})
    assert audit_response.status_code == 200
    audit = audit_response.json()[0]
    assert audit["action"] == "agent_soul.created"
    assert audit["target_id"] == "soul-agent-finance-v1"


def test_project_workspace_assignment_flow_records_events_and_active_scope() -> None:
    client = TestClient(app)
    trace_id = "trace_project_workspace_assignment"
    for agent_id in ["agent-direction", "agent-ops-sourcing"]:
        agent_response = client.post(
            "/agents",
            json={
                "id": agent_id,
                "name": agent_id,
                "role": "Project participant",
                "division": "ops-sourcing" if agent_id.endswith("sourcing") else "direction",
            },
        )
        assert agent_response.status_code == 201
    project_response = client.post(
        "/projects",
        json={
            "id": "project-motor-sourcing",
            "title": "Motor sourcing",
            "goal": "Find qualified motor suppliers in China",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    workspace_response = client.post(
        "/project-workspaces",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "workspace-motor-sourcing",
            "project_id": "project-motor-sourcing",
            "name": "Motor sourcing workspace",
            "summary": "Isolated supplier search context.",
            "memory_scope": "project:project-motor-sourcing",
            "allowed_agent_ids": ["agent-direction", "agent-ops-sourcing"],
        },
    )
    assert workspace_response.status_code == 201

    assignment_response = client.post(
        "/agent-project-assignments",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "assignment-motor-sourcing-ops",
            "project_id": "project-motor-sourcing",
            "workspace_id": "workspace-motor-sourcing",
            "agent_id": "agent-ops-sourcing",
            "assignment_role": "owner",
        },
    )
    assert assignment_response.status_code == 201

    active_workspace = client.get("/projects/project-motor-sourcing/workspace")
    assert active_workspace.status_code == 200
    assert active_workspace.json()["memory_scope"] == "project:project-motor-sourcing"

    assignments = client.get(
        "/agent-project-assignments",
        params={"agent_id": "agent-ops-sourcing", "active": True},
    )
    assert assignments.status_code == 200
    assert [assignment["project_id"] for assignment in assignments.json()] == [
        "project-motor-sourcing"
    ]

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "project_workspace.created",
        "agent_project.assigned",
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert {audit["action"] for audit in audits} == {
        "project_workspace.created",
        "agent_project.assigned",
    }


def test_project_complexity_assessment_requests_split_when_threshold_is_reached() -> None:
    client = TestClient(app)
    trace_id = "trace_project_complexity_split"
    for agent_id in ["agent-direction", "agent-dev"]:
        assert (
            client.post(
                "/agents",
                json={
                    "id": agent_id,
                    "name": agent_id,
                    "role": "Project participant",
                    "division": "dev",
                },
            ).status_code
            == 201
        )
    project_response = client.post(
        "/projects",
        json={
            "id": "project-large-build",
            "title": "Large build",
            "goal": "Keep large work decomposed before execution",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    workspace_response = client.post(
        "/project-workspaces",
        json={
            "id": "workspace-large-build",
            "project_id": "project-large-build",
            "name": "Large build workspace",
            "memory_scope": "project:project-large-build",
            "allowed_agent_ids": ["agent-direction", "agent-dev"],
        },
    )
    assert workspace_response.status_code == 201
    assignment_response = client.post(
        "/agent-project-assignments",
        json={
            "id": "assignment-large-build-dev",
            "project_id": "project-large-build",
            "workspace_id": "workspace-large-build",
            "agent_id": "agent-dev",
            "assignment_role": "owner",
        },
    )
    assert assignment_response.status_code == 201
    for index in range(8):
        task_response = client.post(
            "/tasks",
            json=task_payload("project-large-build", f"Implement slice {index + 1}"),
        )
        assert task_response.status_code == 201

    assessment_response = client.post(
        "/projects/project-large-build/complexity-assessments",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-direction",
            "X-Synarch-Trace-Id": trace_id,
        },
    )

    assert assessment_response.status_code == 201
    assessment = assessment_response.json()
    report = assessment["report"]
    split_request = assessment["split_request"]
    assert report["task_count"] == 8
    assert report["open_task_count"] == 8
    assert report["assigned_agent_count"] == 1
    assert report["score"] == 10
    assert report["split_recommended"] is True
    assert split_request["status"] == "requested"
    assert split_request["complexity_report_id"] == report["id"]
    assert split_request["requested_by"] == "agent-direction"
    assert split_request["proposed_shard_titles"] == [
        "Large build - planning",
        "Large build - execution",
    ]

    reports_response = client.get(
        "/project-complexity-reports",
        params={"project_id": "project-large-build"},
    )
    assert reports_response.status_code == 200
    assert [stored_report["id"] for stored_report in reports_response.json()] == [report["id"]]

    split_requests_response = client.get(
        "/project-split-requests",
        params={"project_id": "project-large-build", "status": "requested"},
    )
    assert split_requests_response.status_code == 200
    assert [request["id"] for request in split_requests_response.json()] == [split_request["id"]]

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "project_complexity.reported",
        "project_split.requested",
    ]
    assert events[0]["source_agent_id"] == "agent-direction"
    assert events[0]["payload"]["score"] == 10

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [audit["action"] for audit in audits] == [
        "project_complexity.reported",
        "project_split.requested",
    ]


def test_project_complexity_assessment_skips_split_below_threshold() -> None:
    client = TestClient(app)
    project_response = client.post(
        "/projects",
        json={
            "id": "project-small-build",
            "title": "Small build",
            "goal": "Keep small work in one project",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    task_response = client.post(
        "/tasks",
        json=task_payload("project-small-build", "Implement one small slice"),
    )
    assert task_response.status_code == 201

    assessment_response = client.post("/projects/project-small-build/complexity-assessments")

    assert assessment_response.status_code == 201
    assessment = assessment_response.json()
    assert assessment["report"]["score"] == 1
    assert assessment["report"]["split_recommended"] is False
    assert assessment["split_request"] is None
    assert (
        client.get(
            "/project-split-requests",
            params={"project_id": "project-small-build"},
        ).json()
        == []
    )


def test_project_split_request_decision_updates_status_and_records_trace() -> None:
    client = TestClient(app)
    trace_id = "trace_project_split_decision"
    for agent_id in ["agent-direction", "agent-dev"]:
        assert (
            client.post(
                "/agents",
                json={
                    "id": agent_id,
                    "name": agent_id,
                    "role": "Project participant",
                    "division": "dev",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/projects",
            json={
                "id": "project-split-decision",
                "title": "Split decision",
                "goal": "Approve or reject a generated project split request",
                "owner_agent_id": "agent-direction",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/project-workspaces",
            json={
                "id": "workspace-split-decision",
                "project_id": "project-split-decision",
                "name": "Split decision workspace",
                "memory_scope": "project:project-split-decision",
                "allowed_agent_ids": ["agent-direction", "agent-dev"],
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/agent-project-assignments",
            json={
                "id": "assignment-split-decision-dev",
                "project_id": "project-split-decision",
                "workspace_id": "workspace-split-decision",
                "agent_id": "agent-dev",
            },
        ).status_code
        == 201
    )
    for index in range(8):
        assert (
            client.post(
                "/tasks",
                json=task_payload("project-split-decision", f"Slice {index + 1}"),
            ).status_code
            == 201
        )

    assessment_response = client.post(
        "/projects/project-split-decision/complexity-assessments",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-direction",
            "X-Synarch-Trace-Id": trace_id,
        },
    )
    assert assessment_response.status_code == 201
    split_request = assessment_response.json()["split_request"]

    decision_response = client.post(
        f"/project-split-requests/{split_request['id']}/decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "request_id": split_request["id"],
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "The project should be split before more execution work starts.",
        },
    )

    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert decision["status"] == "approved"
    assert [event["type"] for event in decision["events_emitted"]] == ["approval.decided"]
    assert decision["events_emitted"][0]["payload"]["decision_type"] == "project_split"
    assert decision["events_emitted"][0]["payload"]["status"] == "approved"

    stored_request = client.get(f"/project-split-requests/{split_request['id']}").json()
    assert stored_request["status"] == "approved"

    duplicate_decision = client.post(
        f"/project-split-requests/{split_request['id']}/decisions",
        json={
            "request_id": split_request["id"],
            "status": "rejected",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Do not split twice.",
        },
    )
    assert duplicate_decision.status_code == 409
    assert duplicate_decision.json()["detail"] == "Project split request is already approved"

    apply_response = client.post(
        f"/project-split-requests/{split_request['id']}/apply",
        headers={
            "X-Synarch-Actor-Type": "service",
            "X-Synarch-Actor-Id": "gateway-project-split-applier",
            "X-Synarch-Trace-Id": trace_id,
        },
    )

    assert apply_response.status_code == 201
    application = apply_response.json()
    assert application["split_request"]["status"] == "applied"
    assert [project["title"] for project in application["shard_projects"]] == [
        "Split decision - planning",
        "Split decision - execution",
    ]
    assert len(application["shard_workspaces"]) == 2
    assert all(
        workspace["bridge_project_ids"] == ["project-split-decision"]
        for workspace in application["shard_workspaces"]
    )
    assert len(application["shard_assignments"]) == 4
    assert {assignment["agent_id"] for assignment in application["shard_assignments"]} == {
        "agent-direction",
        "agent-dev",
    }
    assert len(application["shard_tasks"]) == 2
    assert {task["assigned_agent_id"] for task in application["shard_tasks"]} == {"agent-direction"}
    assert all(task["acceptance_criteria"] for task in application["shard_tasks"])
    assert [event["type"] for event in application["events_emitted"]] == ["project_split.applied"]

    applied_request = client.get(f"/project-split-requests/{split_request['id']}").json()
    assert applied_request["status"] == "applied"

    duplicate_apply = client.post(f"/project-split-requests/{split_request['id']}/apply")
    assert duplicate_apply.status_code == 409
    assert (
        duplicate_apply.json()["detail"]
        == "Project split request must be approved before application: applied"
    )

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == [
        "project_complexity.reported",
        "project_split.requested",
        "approval.decided",
        "project_split.applied",
    ]
    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert [audit["action"] for audit in audits] == [
        "project_complexity.reported",
        "project_split.requested",
        "project_split_request.approved",
        "project_split_request.applied",
    ]


def test_project_assignment_requires_workspace_allowlist() -> None:
    client = TestClient(app)
    for agent_id in ["agent-direction", "agent-dev"]:
        assert (
            client.post(
                "/agents",
                json={
                    "id": agent_id,
                    "name": agent_id,
                    "role": "Project participant",
                    "division": "dev",
                },
            ).status_code
            == 201
        )
    project_response = client.post(
        "/projects",
        json={
            "id": "project-restricted",
            "title": "Restricted",
            "goal": "Prove workspace allowlist",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201
    workspace_response = client.post(
        "/project-workspaces",
        json={
            "id": "workspace-restricted",
            "project_id": "project-restricted",
            "name": "Restricted workspace",
            "memory_scope": "project:project-restricted",
            "allowed_agent_ids": ["agent-direction"],
        },
    )
    assert workspace_response.status_code == 201

    assignment_response = client.post(
        "/agent-project-assignments",
        json={
            "project_id": "project-restricted",
            "workspace_id": "workspace-restricted",
            "agent_id": "agent-dev",
        },
    )

    assert assignment_response.status_code == 400
    assert assignment_response.json()["detail"] == "Agent is not allowed in workspace: agent-dev"


def test_project_assignment_rejects_deactivated_agent() -> None:
    client = TestClient(app)
    for agent_id in ["agent-direction", "agent-temporary-project-worker"]:
        assert (
            client.post(
                "/agents",
                json={
                    "id": agent_id,
                    "name": agent_id,
                    "role": "Project participant",
                    "division": "dev",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/projects",
            json={
                "id": "project-deactivated-assignment",
                "title": "Deactivated assignment",
                "goal": "Do not add deactivated agents to active projects.",
                "owner_agent_id": "agent-direction",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/project-workspaces",
            json={
                "id": "workspace-deactivated-assignment",
                "project_id": "project-deactivated-assignment",
                "name": "Deactivated assignment workspace",
                "memory_scope": "project:project-deactivated-assignment",
                "allowed_agent_ids": [
                    "agent-direction",
                    "agent-temporary-project-worker",
                ],
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/agent-lifecycle-requests",
            json={
                "id": "lifecycle-deactivate-project-worker",
                "action": "deactivate_agent",
                "requested_by_type": "agent",
                "requested_by_id": "agent-direction",
                "reason": "The worker should leave project rotation.",
                "target_agent_id": "agent-temporary-project-worker",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/agent-lifecycle-requests/lifecycle-deactivate-project-worker/decisions",
            json={
                "request_id": "lifecycle-deactivate-project-worker",
                "status": "approved",
                "decided_by_type": "user",
                "decided_by_id": "local-user",
                "rationale": "Worker is out of rotation.",
            },
        ).status_code
        == 201
    )

    assignment_response = client.post(
        "/agent-project-assignments",
        json={
            "project_id": "project-deactivated-assignment",
            "workspace_id": "workspace-deactivated-assignment",
            "agent_id": "agent-temporary-project-worker",
        },
    )

    assert assignment_response.status_code == 400
    assert assignment_response.json()["detail"] == (
        "Agent is not active: agent-temporary-project-worker"
    )
    assert client.get("/agent-project-assignments").json() == []


def test_project_complexity_ignores_deactivated_assignments() -> None:
    client = TestClient(app)
    for agent_id in ["agent-direction", "agent-temporary-complexity-worker"]:
        assert (
            client.post(
                "/agents",
                json={
                    "id": agent_id,
                    "name": agent_id,
                    "role": "Project participant",
                    "division": "dev",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/projects",
            json={
                "id": "project-complexity-deactivated",
                "title": "Complexity deactivated assignment",
                "goal": "Do not count deactivated project assignments as active load.",
                "owner_agent_id": "agent-direction",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/project-workspaces",
            json={
                "id": "workspace-complexity-deactivated",
                "project_id": "project-complexity-deactivated",
                "name": "Complexity deactivated workspace",
                "memory_scope": "project:project-complexity-deactivated",
                "allowed_agent_ids": [
                    "agent-direction",
                    "agent-temporary-complexity-worker",
                ],
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/agent-project-assignments",
            json={
                "id": "assignment-complexity-deactivated",
                "project_id": "project-complexity-deactivated",
                "workspace_id": "workspace-complexity-deactivated",
                "agent_id": "agent-temporary-complexity-worker",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/agent-lifecycle-requests",
            json={
                "id": "lifecycle-deactivate-complexity-worker",
                "action": "deactivate_agent",
                "requested_by_type": "agent",
                "requested_by_id": "agent-direction",
                "reason": "The worker should no longer count as active project load.",
                "target_agent_id": "agent-temporary-complexity-worker",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/agent-lifecycle-requests/lifecycle-deactivate-complexity-worker/decisions",
            json={
                "request_id": "lifecycle-deactivate-complexity-worker",
                "status": "approved",
                "decided_by_type": "user",
                "decided_by_id": "local-user",
                "rationale": "Worker is out of rotation.",
            },
        ).status_code
        == 201
    )

    assessment_response = client.post(
        "/projects/project-complexity-deactivated/complexity-assessments"
    )

    assert assessment_response.status_code == 201
    assert assessment_response.json()["report"]["assigned_agent_count"] == 0


def test_state_change_rejects_unknown_actor_type_before_writing() -> None:
    client = TestClient(app)

    project_response = client.post(
        "/projects",
        headers={
            "X-Synarch-Actor-Type": "robot",
            "X-Synarch-Actor-Id": "local-user",
        },
        json={
            "title": "Invalid actor",
            "goal": "This project should not be written",
            "owner_agent_id": "agent-direction",
        },
    )

    assert project_response.status_code == 400
    assert client.get("/projects").json() == []


def test_agent_model_policy_can_be_updated_and_audited() -> None:
    client = TestClient(app)
    trace_id = "trace_agent_model_policy_update"
    provider_response = client.post(
        "/model-providers",
        json={
            "id": "provider-agent-policy-test",
            "name": "Agent Policy Provider",
            "provider_type": "local",
        },
    )
    assert provider_response.status_code == 201
    for model_id in ["model-agent-policy-a", "model-agent-policy-b"]:
        model_response = client.post(
            "/model-definitions",
            json={
                "id": model_id,
                "provider_id": "provider-agent-policy-test",
                "display_name": model_id,
            },
        )
        assert model_response.status_code == 201
    for policy_id, model_id in [
        ("policy-agent-a", "model-agent-policy-a"),
        ("policy-agent-b", "model-agent-policy-b"),
    ]:
        policy_response = client.post(
            "/model-policies",
            json={
                "id": policy_id,
                "name": policy_id,
                "default_model_id": model_id,
                "allowed_model_ids": [model_id],
            },
        )
        assert policy_response.status_code == 201
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-policy-target",
            "name": "Policy Target",
            "role": "Validate model policy update",
            "division": "dev",
            "model_policy_id": "policy-agent-a",
        },
    )
    assert agent_response.status_code == 201

    update_response = client.patch(
        "/agents/agent-policy-target/model-policy",
        headers={
            "X-Synarch-Actor-Type": "user",
            "X-Synarch-Actor-Id": "local-user",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={"model_policy_id": "policy-agent-b"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["model_policy_id"] == "policy-agent-b"
    events_response = client.get("/events", params={"trace_id": trace_id})
    assert events_response.status_code == 200
    events = events_response.json()
    assert [event["type"] for event in events] == ["agent.updated"]
    assert events[0]["payload"] == {
        "changed_fields": ["model_policy_id"],
        "previous_model_policy_id": "policy-agent-a",
        "model_policy_id": "policy-agent-b",
    }
    audit_response = client.get("/audit-logs", params={"trace_id": trace_id})
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["action"] == "agent.model_policy_updated"


def test_agent_model_policy_update_rejects_unknown_policy() -> None:
    client = TestClient(app)
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-policy-reject",
            "name": "Policy Reject",
            "role": "Reject unknown policy",
            "division": "dev",
        },
    )
    assert agent_response.status_code == 201

    update_response = client.patch(
        "/agents/agent-policy-reject/model-policy",
        json={"model_policy_id": "policy-missing"},
    )

    assert update_response.status_code == 400
    assert update_response.json()["detail"] == "Unknown model policy: policy-missing"
    assert client.get("/agents/agent-policy-reject").json()["model_policy_id"] is None


def test_company_state_cost_and_audit_flow() -> None:
    client = TestClient(app)
    trace_id = "trace_state_company_flow"

    division_response = client.post(
        "/divisions",
        json={
            "id": "division-finance-state-test",
            "name": "Finance",
            "purpose": "Comptabilite, TVA, factures, fournisseurs, paiements",
            "manager_agent_id": "agent-direction",
        },
    )
    assert division_response.status_code == 201

    provider_response = client.post(
        "/model-providers",
        json={
            "id": "provider-openrouter-state-test",
            "name": "OpenRouter",
            "provider_type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env_var": "OPENROUTER_API_KEY",
        },
    )
    assert provider_response.status_code == 201

    model_response = client.post(
        "/model-definitions",
        json={
            "id": "model-finance-state-test",
            "provider_id": "provider-openrouter-state-test",
            "display_name": "Finance routing model",
            "context_window": 64000,
            "input_cost_per_million_tokens": 0.14,
            "output_cost_per_million_tokens": 0.28,
            "supports_structured_output": True,
        },
    )
    assert model_response.status_code == 201

    policy_response = client.post(
        "/model-policies",
        json={
            "id": "policy-finance-state-test",
            "name": "Finance default routing",
            "default_model_id": "model-finance-state-test",
            "allowed_model_ids": ["model-finance-state-test"],
            "max_cost_per_day": 2.5,
            "require_human_approval_above": 0.5,
        },
    )
    assert policy_response.status_code == 201

    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-finance-state-test",
            "name": "IA Finance",
            "role": "Compta, TVA, factures, fournisseurs, paiements",
            "division": "finance",
            "manager_id": "agent-direction",
            "model_policy_id": "policy-finance-state-test",
            "allowed_model_ids": ["model-finance-state-test"],
            "capabilities": {
                "skills": ["invoice_ocr", "accounting_entries"],
                "tools": ["document.read", "ledger.write", "event.emit"],
                "models": ["model-finance-state-test"],
            },
            "permissions": {
                "can_read_scopes": ["division:finance", "project:*"],
                "can_write_scopes": ["division:finance", "event:*"],
                "allowed_tools": ["document.read", "ledger.write", "event.emit"],
                "denied_tools": ["payment.execute"],
            },
        },
    )
    assert agent_response.status_code == 201

    service_response = client.post(
        "/services",
        json={
            "id": "service-model-gateway-state-test",
            "name": "Model Gateway",
            "kind": "internal",
            "capabilities": ["model.route", "cost.record", "model.policy.enforce"],
        },
    )
    assert service_response.status_code == 201

    project_response = client.post(
        "/projects",
        json={
            "title": "Finance invoice intake",
            "goal": "Extract invoice data, check VAT, and request approval for exceptions",
            "priority": "high",
            "owner_agent_id": "agent-finance-state-test",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()

    task_response = client.post(
        "/tasks",
        json=task_payload(
            project["id"],
            "Extract invoice JSON and estimate cost",
            "agent-finance-state-test",
        ),
    )
    assert task_response.status_code == 201
    task = task_response.json()

    cost_response = client.post(
        "/cost-records",
        json={
            "provider_id": "provider-openrouter-state-test",
            "model_id": "model-finance-state-test",
            "agent_id": "agent-finance-state-test",
            "project_id": project["id"],
            "task_id": task["id"],
            "trace_id": trace_id,
            "input_tokens": 1200,
            "output_tokens": 350,
            "total_cost": 0.000266,
        },
    )
    assert cost_response.status_code == 201
    cost = cost_response.json()

    audit_response = client.post(
        "/audit-logs",
        json={
            "actor_type": "agent",
            "actor_id": "agent-finance-state-test",
            "action": "cost.recorded",
            "target_type": "cost_record",
            "target_id": cost["id"],
            "trace_id": trace_id,
            "payload": {"project_id": project["id"], "task_id": task["id"]},
        },
    )
    assert audit_response.status_code == 201

    costs_by_project = client.get("/cost-records", params={"project_id": project["id"]})
    assert costs_by_project.status_code == 200
    assert [record["id"] for record in costs_by_project.json()] == [cost["id"]]

    costs_by_agent = client.get("/cost-records", params={"agent_id": "agent-finance-state-test"})
    assert costs_by_agent.status_code == 200
    assert [record["id"] for record in costs_by_agent.json()] == [cost["id"]]

    costs_by_provider = client.get(
        "/cost-records",
        params={"provider_id": "provider-openrouter-state-test"},
    )
    assert costs_by_provider.status_code == 200
    assert [record["id"] for record in costs_by_provider.json()] == [cost["id"]]

    costs_by_model = client.get(
        "/cost-records",
        params={"model_id": "model-finance-state-test"},
    )
    assert costs_by_model.status_code == 200
    assert [record["id"] for record in costs_by_model.json()] == [cost["id"]]

    cost_events = client.get(
        "/events",
        params={"trace_id": trace_id, "event_type": "cost.recorded"},
    )
    assert cost_events.status_code == 200
    assert cost_events.json()[0]["payload"]["cost_id"] == cost["id"]
    assert cost_events.json()[0]["payload"]["total_cost"] == 0.000266

    audit_timeline = client.get("/audit-logs", params={"trace_id": trace_id})
    assert audit_timeline.status_code == 200
    assert audit_timeline.json()[0]["target_id"] == cost["id"]


def test_agent_lifecycle_approval_creates_agent_events_and_audit() -> None:
    client = TestClient(app)
    trace_id = "trace_lifecycle_create_agent"

    lifecycle_response = client.post(
        "/agent-lifecycle-requests",
        headers={
            "X-Synarch-Actor-Type": "agent",
            "X-Synarch-Actor-Id": "agent-direction",
            "X-Synarch-Trace-Id": trace_id,
        },
        json={
            "id": "lifecycle-create-finance-reviewer",
            "action": "create_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "Finance needs a deterministic invoice reviewer.",
            "proposed_agent": {
                "id": "agent-finance-reviewer",
                "name": "IA Finance Reviewer",
                "role": "Review invoices before approval",
                "division": "finance",
                "manager_id": "agent-direction",
                "created_by": "agent-direction",
            },
            "proposed_soul": {
                "id": "soul-agent-finance-reviewer-v1",
                "agent_id": "agent-finance-reviewer",
                "identity": "IA Finance Reviewer verifies invoice evidence before human approval.",
                "mission": "Review invoice anomalies and keep payment execution out of scope.",
                "responsibilities": ["Review invoice evidence", "Escalate unclear VAT cases"],
                "operating_principles": ["Keep every recommendation auditable"],
                "boundaries": ["Never execute payments"],
                "escalation_rules": ["Escalate payment execution requests to IA Direction"],
                "created_by": "agent-direction",
            },
        },
    )
    assert lifecycle_response.status_code == 201

    decision_response = client.post(
        "/agent-lifecycle-requests/lifecycle-create-finance-reviewer/decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "request_id": "lifecycle-create-finance-reviewer",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Scoped role and no unsafe tools.",
        },
    )

    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert decision["status"] == "applied"
    assert [event["type"] for event in decision["events_emitted"]] == [
        "approval.decided",
        "agent.created",
        "agent_soul.created",
    ]

    agent_response = client.get("/agents/agent-finance-reviewer")
    assert agent_response.status_code == 200
    assert agent_response.json()["status"] == "active"
    active_soul_response = client.get("/agents/agent-finance-reviewer/soul")
    assert active_soul_response.status_code == 200
    assert active_soul_response.json()["id"] == "soul-agent-finance-reviewer-v1"

    request_response = client.get("/agent-lifecycle-requests/lifecycle-create-finance-reviewer")
    assert request_response.status_code == 200
    assert request_response.json()["status"] == "applied"
    assert request_response.json()["proposed_soul"]["id"] == "soul-agent-finance-reviewer-v1"

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert {event["type"] for event in events} == {
        "approval.requested",
        "approval.decided",
        "agent.created",
        "agent_soul.created",
    }

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert {audit["action"] for audit in audits} >= {
        "agent_lifecycle_request.created",
        "agent_lifecycle_request.applied",
        "agent.created",
        "agent_soul.created",
    }


def test_agent_lifecycle_deactivation_blocks_new_task_assignment() -> None:
    client = TestClient(app)
    trace_id = "trace_lifecycle_deactivate_agent"

    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-temporary-worker",
            "name": "IA Temporary Worker",
            "role": "Short-lived execution worker",
            "division": "dev",
        },
    )
    assert agent_response.status_code == 201

    lifecycle_response = client.post(
        "/agent-lifecycle-requests",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "id": "lifecycle-deactivate-temporary-worker",
            "action": "deactivate_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "The temporary worker should no longer receive work.",
            "target_agent_id": "agent-temporary-worker",
        },
    )
    assert lifecycle_response.status_code == 201

    decision_response = client.post(
        "/agent-lifecycle-requests/lifecycle-deactivate-temporary-worker/decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "request_id": "lifecycle-deactivate-temporary-worker",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "The agent is out of rotation.",
        },
    )
    assert decision_response.status_code == 201
    assert decision_response.json()["status"] == "applied"

    deactivated_agent = client.get("/agents/agent-temporary-worker").json()
    assert deactivated_agent["status"] == "inactive"

    project_response = client.post(
        "/projects",
        json={
            "title": "Do not assign inactive agent",
            "goal": "Prove lifecycle deactivation gates task assignment",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "This should be blocked",
            "agent-temporary-worker",
        ),
    )

    assert task_response.status_code == 400
    assert task_response.json()["detail"] == "Agent is not active: agent-temporary-worker"


def test_agent_lifecycle_rejects_duplicate_pending_request_for_same_action() -> None:
    client = TestClient(app)
    trace_id = "trace_duplicate_lifecycle_request"

    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-duplicate-lifecycle",
            "name": "IA Duplicate Lifecycle",
            "role": "Temporary lifecycle target",
            "division": "dev",
        },
    )
    assert agent_response.status_code == 201

    first_response = client.post(
        "/agent-lifecycle-requests",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "id": "lifecycle-deactivate-duplicate-first",
            "action": "deactivate_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "The agent should be deactivated once.",
            "target_agent_id": "agent-duplicate-lifecycle",
        },
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/agent-lifecycle-requests",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "id": "lifecycle-deactivate-duplicate-second",
            "action": "deactivate_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "A duplicate request should not create a second approval item.",
            "target_agent_id": "agent-duplicate-lifecycle",
        },
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Pending lifecycle request already exists for agent-duplicate-lifecycle "
        "and action deactivate_agent: lifecycle-deactivate-duplicate-first"
    )
    requests_response = client.get("/agent-lifecycle-requests")
    assert requests_response.status_code == 200
    assert [request["id"] for request in requests_response.json()] == [
        "lifecycle-deactivate-duplicate-first"
    ]
    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert [event["type"] for event in events] == ["approval.requested"]


def test_agent_lifecycle_deactivation_blocks_existing_task_start() -> None:
    client = TestClient(app)
    lifecycle_trace_id = "trace_lifecycle_deactivate_runner"
    start_trace_id = "trace_start_deactivated_runner"

    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-temporary-runner",
            "name": "IA Temporary Runner",
            "role": "Run queued work during a temporary phase",
            "division": "dev",
        },
    )
    assert agent_response.status_code == 201

    project_response = client.post(
        "/projects",
        json={
            "title": "Stop deactivated task start",
            "goal": "Queued work must not start after its agent is deactivated",
            "owner_agent_id": "agent-direction",
        },
    )
    assert project_response.status_code == 201

    task_response = client.post(
        "/tasks",
        json=task_payload(
            project_response.json()["id"],
            "Queued before deactivation",
            "agent-temporary-runner",
        ),
    )
    assert task_response.status_code == 201
    task = task_response.json()

    lifecycle_response = client.post(
        "/agent-lifecycle-requests",
        headers={"X-Synarch-Trace-Id": lifecycle_trace_id},
        json={
            "id": "lifecycle-deactivate-temporary-runner",
            "action": "deactivate_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "The temporary runner should stop receiving execution leases.",
            "target_agent_id": "agent-temporary-runner",
        },
    )
    assert lifecycle_response.status_code == 201

    decision_response = client.post(
        "/agent-lifecycle-requests/lifecycle-deactivate-temporary-runner/decisions",
        headers={"X-Synarch-Trace-Id": lifecycle_trace_id},
        json={
            "request_id": "lifecycle-deactivate-temporary-runner",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "The agent is out of rotation.",
        },
    )
    assert decision_response.status_code == 201

    start_response = client.post(
        f"/tasks/{task['id']}/start",
        headers={"X-Synarch-Trace-Id": start_trace_id},
    )

    assert start_response.status_code == 409
    assert start_response.json()["detail"] == "Agent is not active: agent-temporary-runner"
    queued_task = client.get(f"/tasks/{task['id']}").json()
    assert queued_task["status"] == "queued"
    assert queued_task["attempt_count"] == 0
    assert client.get("/events", params={"trace_id": start_trace_id}).json() == []
    assert client.get("/audit-logs", params={"trace_id": start_trace_id}).json() == []


def test_agent_lifecycle_update_replaces_agent_and_active_soul() -> None:
    client = TestClient(app)
    trace_id = "trace_lifecycle_update_agent_soul"

    direction_response = client.post(
        "/agents",
        json={
            "id": "agent-direction",
            "name": "IA Direction",
            "role": "Company director",
            "division": "direction",
        },
    )
    assert direction_response.status_code == 201
    agent_response = client.post(
        "/agents",
        json={
            "id": "agent-dev-reviewer",
            "name": "IA Dev Reviewer",
            "role": "Review pull requests",
            "division": "dev",
            "manager_id": "agent-direction",
            "created_by": "agent-direction",
        },
    )
    assert agent_response.status_code == 201
    soul_response = client.post(
        "/agent-souls",
        json={
            "id": "soul-agent-dev-reviewer-v1",
            "agent_id": "agent-dev-reviewer",
            "identity": "IA Dev Reviewer checks code changes.",
            "mission": "Review code changes and raise unsafe deployments.",
            "created_by": "agent-direction",
        },
    )
    assert soul_response.status_code == 201

    lifecycle_response = client.post(
        "/agent-lifecycle-requests",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "id": "lifecycle-update-dev-reviewer",
            "action": "update_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "The reviewer now owns CI review and event emission.",
            "target_agent_id": "agent-dev-reviewer",
            "proposed_agent": {
                "id": "agent-dev-reviewer",
                "name": "IA Dev Reviewer",
                "role": "Review pull requests and CI signals",
                "division": "dev",
                "manager_id": "agent-direction",
                "capabilities": {"skills": ["code-review"], "tools": ["event.emit"], "models": []},
                "permissions": {
                    "can_read_scopes": ["project:dev"],
                    "can_write_scopes": ["project:dev"],
                    "allowed_tools": ["event.emit"],
                    "denied_tools": ["payment.execute"],
                },
                "created_by": "agent-other",
            },
            "proposed_soul": {
                "id": "soul-agent-dev-reviewer-v2",
                "agent_id": "agent-dev-reviewer",
                "version": 2,
                "identity": "IA Dev Reviewer owns code review and CI signal triage.",
                "mission": "Review code changes, inspect CI signals, and escalate risky deploys.",
                "responsibilities": ["Review pull requests", "Summarize CI failures"],
                "operating_principles": ["Keep every review traceable"],
                "boundaries": ["Never approve payment execution"],
                "escalation_rules": ["Escalate production deploy risk to IA Direction"],
                "created_by": "agent-direction",
            },
        },
    )
    assert lifecycle_response.status_code == 201

    decision_response = client.post(
        "/agent-lifecycle-requests/lifecycle-update-dev-reviewer/decisions",
        headers={"X-Synarch-Trace-Id": trace_id},
        json={
            "request_id": "lifecycle-update-dev-reviewer",
            "status": "approved",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Update keeps the agent in the same division and scopes tools.",
        },
    )
    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert decision["status"] == "applied"
    assert [event["type"] for event in decision["events_emitted"]] == [
        "approval.decided",
        "agent.updated",
        "agent_soul.created",
    ]

    updated_agent = client.get("/agents/agent-dev-reviewer").json()
    assert updated_agent["role"] == "Review pull requests and CI signals"
    assert updated_agent["permissions"]["allowed_tools"] == ["event.emit"]
    assert updated_agent["created_by"] == "agent-direction"

    active_soul = client.get("/agents/agent-dev-reviewer/soul").json()
    assert active_soul["id"] == "soul-agent-dev-reviewer-v2"
    assert active_soul["version"] == 2
    old_soul = client.get("/agent-souls/soul-agent-dev-reviewer-v1").json()
    assert old_soul["active"] is False

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert {event["type"] for event in events} == {
        "approval.requested",
        "approval.decided",
        "agent.updated",
        "agent_soul.created",
    }
    update_event = next(event for event in events if event["type"] == "agent.updated")
    assert "permissions" in update_event["payload"]["changed_fields"]
    assert "role" in update_event["payload"]["changed_fields"]

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert {audit["action"] for audit in audits} >= {
        "agent.updated",
        "agent_soul.deactivated",
        "agent_soul.created",
        "agent_lifecycle_request.applied",
    }


def test_agent_lifecycle_create_rejects_soul_for_different_agent() -> None:
    client = TestClient(app)

    response = client.post(
        "/agent-lifecycle-requests",
        json={
            "id": "lifecycle-create-mismatched-soul",
            "action": "create_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "Invalid soul should not be accepted.",
            "proposed_agent": {
                "id": "agent-valid-target",
                "name": "IA Valid Target",
                "role": "Temporary reviewer",
                "division": "dev",
            },
            "proposed_soul": {
                "id": "soul-wrong-agent-v1",
                "agent_id": "agent-other-target",
                "identity": "This soul points at another agent.",
                "mission": "This should fail validation.",
                "created_by": "agent-direction",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "proposed_soul.agent_id must match proposed_agent.id"


def test_agent_lifecycle_rejection_does_not_apply_request() -> None:
    client = TestClient(app)

    lifecycle_response = client.post(
        "/agent-lifecycle-requests",
        json={
            "id": "lifecycle-reject-ops-agent",
            "action": "create_agent",
            "requested_by_type": "agent",
            "requested_by_id": "agent-direction",
            "reason": "Ops requested another sourcing worker.",
            "proposed_agent": {
                "id": "agent-ops-extra",
                "name": "IA Ops Extra",
                "role": "Extra sourcing worker",
                "division": "ops-sourcing",
            },
        },
    )
    assert lifecycle_response.status_code == 201

    decision_response = client.post(
        "/agent-lifecycle-requests/lifecycle-reject-ops-agent/decisions",
        json={
            "request_id": "lifecycle-reject-ops-agent",
            "status": "rejected",
            "decided_by_type": "user",
            "decided_by_id": "local-user",
            "rationale": "Capacity is enough for now.",
        },
    )

    assert decision_response.status_code == 201
    assert decision_response.json()["status"] == "rejected"
    assert client.get("/agents/agent-ops-extra").status_code == 404
    assert (
        client.get("/agent-lifecycle-requests/lifecycle-reject-ops-agent").json()["status"]
        == "rejected"
    )
