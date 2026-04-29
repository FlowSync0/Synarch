import pytest
from fastapi.testclient import TestClient

from synarch_state_service.main import app, reset_repositories


@pytest.fixture(autouse=True)
def clean_state_service() -> None:
    reset_repositories()


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
        json={
            "project_id": project["id"],
            "title": "Implement route",
            "assigned_agent_id": "agent-dev",
        },
    )

    assert task_response.status_code == 201
    assert task_response.json()["project_id"] == project["id"]


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
        json={
            "project_id": project["id"],
            "title": "Prepare deterministic result",
            "assigned_agent_id": "agent-dev",
        },
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
        json={
            "project_id": project_response.json()["id"],
            "title": "Wrong agent must fail",
            "assigned_agent_id": "agent-dev",
        },
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
        result_response.json()["detail"]
        == "Result agent does not match assigned agent: agent-dev"
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
        json={
            "project_id": project["id"],
            "title": "Extract invoice JSON and estimate cost",
            "assigned_agent_id": "agent-finance-state-test",
        },
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
    ]

    agent_response = client.get("/agents/agent-finance-reviewer")
    assert agent_response.status_code == 200
    assert agent_response.json()["status"] == "active"

    request_response = client.get(
        "/agent-lifecycle-requests/lifecycle-create-finance-reviewer"
    )
    assert request_response.status_code == 200
    assert request_response.json()["status"] == "applied"

    events = client.get("/events", params={"trace_id": trace_id}).json()
    assert {event["type"] for event in events} == {
        "approval.requested",
        "approval.decided",
        "agent.created",
    }

    audits = client.get("/audit-logs", params={"trace_id": trace_id}).json()
    assert {audit["action"] for audit in audits} >= {
        "agent_lifecycle_request.created",
        "agent_lifecycle_request.applied",
        "agent.created",
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
        json={
            "project_id": project_response.json()["id"],
            "title": "This should be blocked",
            "assigned_agent_id": "agent-temporary-worker",
        },
    )

    assert task_response.status_code == 400
    assert task_response.json()["detail"] == "Agent is not active: agent-temporary-worker"


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
    assert client.get("/agent-lifecycle-requests/lifecycle-reject-ops-agent").json()[
        "status"
    ] == "rejected"
