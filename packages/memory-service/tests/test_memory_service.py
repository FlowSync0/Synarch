import pytest
from fastapi.testclient import TestClient

from synarch_memory_service.main import app, reset_memory_items


@pytest.fixture(autouse=True)
def clean_memory_service() -> None:
    reset_memory_items()


def test_context_assembly_filters_by_scope_agent_and_project() -> None:
    client = TestClient(app)
    project_id = "project_invoice"

    for item in [
        {
            "id": "memory-global",
            "scope": "global",
            "content": "Company prefers explicit human approval for payments.",
        },
        {
            "id": "memory-finance",
            "scope": "division:finance",
            "content": "Finance invoices require VAT consistency checks.",
        },
        {
            "id": "memory-agent",
            "scope": "agent:agent-finance",
            "agent_id": "agent-finance",
            "content": "The finance agent drafts accounting entries but never pays invoices.",
        },
        {
            "id": "memory-project",
            "scope": f"project:{project_id}",
            "project_id": project_id,
            "content": "This supplier invoice has a bank reconciliation exception.",
        },
        {
            "id": "memory-dev",
            "scope": "division:dev",
            "content": "Dev memory must not leak into finance context.",
        },
        {
            "id": "memory-other-project",
            "scope": "global",
            "project_id": "project_other",
            "content": "Other project memory must not leak.",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-finance",
            "project_id": project_id,
            "token_budget": 200,
            "allowed_scopes": [
                "global",
                "division:finance",
                "agent:agent-finance",
                f"project:{project_id}",
            ],
        },
    )

    assert context_response.status_code == 200
    context = context_response.json()
    assert [item["id"] for item in context["items"]] == [
        "memory-project",
        "memory-agent",
        "memory-finance",
        "memory-global",
    ]
    assert context["tokens_used"] <= context["token_budget"]
    assert "4 memory items" in context["summary"]


def test_context_assembly_enforces_token_budget() -> None:
    client = TestClient(app)
    short_response = client.post(
        "/memory-items",
        json={
            "id": "memory-short",
            "scope": "global",
            "content": "Short.",
        },
    )
    assert short_response.status_code == 201
    long_response = client.post(
        "/memory-items",
        json={
            "id": "memory-long",
            "scope": "global",
            "content": "x" * 120,
        },
    )
    assert long_response.status_code == 201

    context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "token_budget": 3,
            "allowed_scopes": ["global"],
        },
    )

    assert context_response.status_code == 200
    context = context_response.json()
    assert [item["id"] for item in context["items"]] == ["memory-short"]
    assert context["tokens_used"] <= 3


def test_proposed_memory_is_excluded_until_approved() -> None:
    client = TestClient(app)
    create_response = client.post(
        "/memory-items",
        json={
            "id": "memory-candidate",
            "scope": "global",
            "content": "Candidate facts must be reviewed before use.",
            "status": "proposed",
        },
    )
    assert create_response.status_code == 201

    proposed_context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "token_budget": 200,
            "allowed_scopes": ["global"],
        },
    )
    assert proposed_context_response.status_code == 200
    assert proposed_context_response.json()["items"] == []

    approve_response = client.patch(
        "/memory-items/memory-candidate/status",
        json={"status": "approved"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    approved_context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "token_budget": 200,
            "allowed_scopes": ["global"],
        },
    )
    assert [item["id"] for item in approved_context_response.json()["items"]] == [
        "memory-candidate"
    ]

    reject_response = client.patch(
        "/memory-items/memory-candidate/status",
        json={"status": "rejected"},
    )
    assert reject_response.status_code == 200
    rejected_response = client.get("/memory-items", params={"status": "rejected"})
    assert [item["id"] for item in rejected_response.json()] == ["memory-candidate"]
    rejected_context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "token_budget": 200,
            "allowed_scopes": ["global"],
        },
    )
    assert rejected_context_response.json()["items"] == []
