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
