import psycopg
import pytest
from fastapi.testclient import TestClient

import synarch_memory_service.main as memory_main
from synarch_memory_service.main import app, reset_memory_items
from synarch_models import MemoryItem, MemoryStatus


@pytest.fixture(autouse=True)
def clean_memory_service() -> None:
    reset_memory_items()


def test_create_memory_item_rejects_wrong_embedding_dimension() -> None:
    response = TestClient(app).post(
        "/memory-items",
        json={
            "id": "memory-invalid-embedding",
            "scope": "global",
            "content": "Invalid vector dimensions should be rejected before storage.",
            "embedding": [1.0, 0.0],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Memory embedding must have 1536 dimensions"


def test_create_memory_item_maps_store_foreign_key_errors_to_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForeignKeyFailingStore:
        def create(self, item: MemoryItem) -> MemoryItem:
            raise psycopg.errors.ForeignKeyViolation("missing reference")

        def update_status(
            self,
            item_id: str,
            status: MemoryStatus,
        ) -> MemoryItem | None:
            return None

        def list_items(self) -> list[MemoryItem]:
            return []

        def reset(self) -> None:
            return None

    monkeypatch.setattr(memory_main, "STORE", ForeignKeyFailingStore())

    response = TestClient(app).post(
        "/memory-items",
        json={
            "id": "memory-unknown-project",
            "scope": "project:missing",
            "project_id": "missing",
            "content": "Unknown projects should be rejected as bad input.",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Memory item references an unknown project or agent"


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


def test_context_assembly_requires_explicit_bridge_project_ids() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-target-project",
            "scope": "project:project_target",
            "project_id": "project_target",
            "content": "Target project memory.",
        },
        {
            "id": "memory-bridged-project",
            "scope": "project:project_source",
            "project_id": "project_source",
            "content": "Source project memory visible only through a bridge.",
        },
        {
            "id": "memory-other-project",
            "scope": "project:project_other",
            "project_id": "project_other",
            "content": "Other project memory must stay isolated.",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    without_bridge_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "project_id": "project_target",
            "token_budget": 200,
            "allowed_scopes": ["project:project_target", "project:project_source"],
        },
    )
    with_bridge_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "project_id": "project_target",
            "token_budget": 200,
            "allowed_scopes": ["project:project_target", "project:project_source"],
            "allowed_project_ids": ["project_target", "project_source"],
        },
    )

    assert without_bridge_response.status_code == 200
    assert [item["id"] for item in without_bridge_response.json()["items"]] == [
        "memory-target-project"
    ]
    assert with_bridge_response.status_code == 200
    assert [item["id"] for item in with_bridge_response.json()["items"]] == [
        "memory-target-project",
        "memory-bridged-project",
    ]


def test_context_assembly_expands_related_memory_inside_visibility_rules() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-seed",
            "scope": "project:project_target",
            "project_id": "project_target",
            "content": "Seed memory.",
            "metadata": {
                "related_memory_ids": [
                    "memory-related",
                    "memory-hidden",
                    "memory-missing",
                    42,
                ]
            },
        },
        {
            "id": "memory-unrelated",
            "scope": "project:project_target",
            "project_id": "project_target",
            "content": "Unrelated target memory.",
        },
        {
            "id": "memory-related",
            "scope": "project:project_source",
            "project_id": "project_source",
            "content": "Related bridged project memory.",
        },
        {
            "id": "memory-hidden",
            "scope": "project:project_hidden",
            "project_id": "project_hidden",
            "content": "Hidden project memory must not leak through graph links.",
        },
        {
            "id": "memory-relation-proposal",
            "scope": "project:project_target",
            "project_id": "project_target",
            "status": "approved",
            "content": "Relation proposals are governance records, not runtime memory.",
            "metadata": {
                "kind": "memory_relation_proposal",
                "source_memory_id": "memory-seed",
                "related_memory_ids": ["memory-related"],
            },
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "project_id": "project_target",
            "token_budget": 200,
            "allowed_scopes": ["project:project_target", "project:project_source"],
            "allowed_project_ids": ["project_target", "project_source"],
            "max_related_items": 1,
        },
    )

    assert context_response.status_code == 200
    context = context_response.json()
    assert [item["id"] for item in context["items"]] == [
        "memory-seed",
        "memory-related",
        "memory-unrelated",
    ]
    assert "1 graph-related items" in context["summary"]


def test_context_assembly_can_disable_related_memory_expansion() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-seed",
            "scope": "project:project_target",
            "project_id": "project_target",
            "content": "Seed memory.",
            "metadata": {"related_memory_ids": ["memory-related"]},
        },
        {
            "id": "memory-related",
            "scope": "project:project_source",
            "project_id": "project_source",
            "content": "Related bridged project memory.",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "project_id": "project_target",
            "token_budget": 200,
            "allowed_scopes": ["project:project_target", "project:project_source"],
            "allowed_project_ids": ["project_target", "project_source"],
            "max_related_items": 0,
        },
    )

    assert context_response.status_code == 200
    assert [item["id"] for item in context_response.json()["items"]] == [
        "memory-seed",
        "memory-related",
    ]
    assert "0 graph-related items" in context_response.json()["summary"]


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


def test_context_assembly_ranks_by_query_embedding_after_scope_filters() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-project-vector-miss",
            "scope": "project:project_semantic",
            "project_id": "project_semantic",
            "content": "This fact is visible but points to a different vector direction.",
            "embedding": embedding_axis(0),
        },
        {
            "id": "memory-project-vector-match",
            "scope": "project:project_semantic",
            "project_id": "project_semantic",
            "content": "This fact should rank first for the query vector.",
            "embedding": embedding_axis(1),
        },
        {
            "id": "memory-global-no-vector",
            "scope": "global",
            "content": "This fallback fact has no embedding.",
        },
        {
            "id": "memory-other-project-vector-match",
            "scope": "project:project_other",
            "project_id": "project_other",
            "content": "This fact matches the vector but belongs to another project.",
            "embedding": embedding_axis(1),
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "project_id": "project_semantic",
            "token_budget": 200,
            "allowed_scopes": ["project:project_semantic", "global"],
            "query_embedding": embedding_axis(1),
        },
    )

    assert context_response.status_code == 200
    context = context_response.json()
    assert [item["id"] for item in context["items"]] == [
        "memory-project-vector-match",
        "memory-project-vector-miss",
        "memory-global-no-vector",
    ]
    assert "semantic vector ranking" in context["summary"]


def test_context_assembly_rejects_wrong_query_embedding_dimension() -> None:
    response = TestClient(app).post(
        "/context/assemble",
        json={
            "agent_id": "agent-dev",
            "token_budget": 200,
            "allowed_scopes": ["global"],
            "query_embedding": [0.0, 1.0],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Query embedding must have 1536 dimensions"


def embedding_axis(index: int) -> list[float]:
    embedding = [0.0] * 1536
    embedding[index] = 1.0
    return embedding


def test_list_memory_items_filters_by_project_and_status() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-project-proposed",
            "scope": "project:project_demo",
            "project_id": "project_demo",
            "content": "Candidate fact for the demo project.",
            "status": "proposed",
        },
        {
            "id": "memory-project-approved",
            "scope": "project:project_demo",
            "project_id": "project_demo",
            "content": "Approved fact for the demo project.",
            "status": "approved",
        },
        {
            "id": "memory-other-project",
            "scope": "project:project_other",
            "project_id": "project_other",
            "content": "Candidate fact for another project.",
            "status": "proposed",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    list_response = client.get(
        "/memory-items",
        params={"project_id": "project_demo", "status": "proposed"},
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == ["memory-project-proposed"]


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


def test_compact_memory_items_creates_proposed_item_with_source_provenance() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-source-a",
            "scope": "project:project_compaction",
            "project_id": "project_compaction",
            "content": "Supplier A requires a signed NDA before sending pricing.",
            "status": "approved",
        },
        {
            "id": "memory-source-b",
            "scope": "project:project_compaction",
            "project_id": "project_compaction",
            "content": "Supplier B can ship samples in three weeks.",
            "status": "approved",
        },
        {
            "id": "memory-proposed",
            "scope": "project:project_compaction",
            "project_id": "project_compaction",
            "content": "Proposed memory must not be compacted.",
            "status": "proposed",
        },
        {
            "id": "memory-other-project",
            "scope": "project:project_other",
            "project_id": "project_other",
            "content": "Other project memory must not be compacted.",
            "status": "approved",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    response = client.post(
        "/memory-items/compact",
        json={
            "scope": "project:project_compaction",
            "project_id": "project_compaction",
            "max_source_items": 10,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_memory_ids"] == ["memory-source-a", "memory-source-b"]
    assert payload["source_count"] == 2
    assert payload["source_tokens"] > 0
    compacted_item = payload["compacted_item"]
    assert compacted_item["status"] == "proposed"
    assert compacted_item["scope"] == "project:project_compaction"
    assert compacted_item["project_id"] == "project_compaction"
    assert compacted_item["metadata"] == {
        "kind": "compaction",
        "source_memory_ids": ["memory-source-a", "memory-source-b"],
        "source_count": 2,
        "source_tokens": payload["source_tokens"],
    }
    assert "Source memory ids: memory-source-a, memory-source-b" in compacted_item["content"]
    assert "[memory-source-a]" in compacted_item["content"]
    assert "[memory-source-b]" in compacted_item["content"]

    context_response = client.post(
        "/context/assemble",
        json={
            "agent_id": "agent-ops",
            "project_id": "project_compaction",
            "token_budget": 400,
            "allowed_scopes": ["project:project_compaction"],
        },
    )
    assert compacted_item["id"] not in [
        item["id"] for item in context_response.json()["items"]
    ]


def test_compact_memory_items_if_needed_creates_policy_candidate_above_threshold() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-large-a",
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "content": "A" * 100,
            "status": "approved",
        },
        {
            "id": "memory-large-b",
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "content": "B" * 100,
            "status": "approved",
        },
        {
            "id": "memory-policy-proposed",
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "content": "Proposed memory is excluded from policy source tokens.",
            "status": "proposed",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    response = client.post(
        "/memory-items/compact-if-needed",
        json={
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "min_source_tokens": 40,
            "max_source_items": 10,
            "max_summary_chars": 200,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["compaction_needed"] is True
    assert payload["reason"] == "source_tokens_exceed_threshold"
    assert payload["threshold_tokens"] == 40
    assert payload["source_memory_ids"] == ["memory-large-a", "memory-large-b"]
    assert payload["source_count"] == 2
    assert payload["source_tokens"] == 50
    compacted_item = payload["compaction"]["compacted_item"]
    assert compacted_item["status"] == "proposed"
    assert compacted_item["metadata"]["kind"] == "compaction"
    assert compacted_item["metadata"]["source_memory_ids"] == [
        "memory-large-a",
        "memory-large-b",
    ]
    assert "Source memory ids: memory-large-a, memory-large-b" in compacted_item["content"]

    duplicate_response = client.post(
        "/memory-items/compact-if-needed",
        json={
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "min_source_tokens": 40,
            "max_source_items": 10,
            "max_summary_chars": 200,
        },
    )
    assert duplicate_response.status_code == 200
    duplicate_payload = duplicate_response.json()
    assert duplicate_payload["compaction_needed"] is False
    assert duplicate_payload["reason"] == "matching_compaction_exists"
    assert duplicate_payload["existing_compacted_item"]["id"] == compacted_item["id"]
    assert duplicate_payload["compaction"] is None

    approve_response = client.patch(
        f"/memory-items/{compacted_item['id']}/status",
        json={"status": "approved"},
    )
    assert approve_response.status_code == 200

    approved_duplicate_response = client.post(
        "/memory-items/compact-if-needed",
        json={
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "min_source_tokens": 40,
            "max_source_items": 10,
            "max_summary_chars": 200,
        },
    )
    assert approved_duplicate_response.status_code == 200
    approved_duplicate_payload = approved_duplicate_response.json()
    assert approved_duplicate_payload["reason"] == "matching_compaction_exists"
    assert approved_duplicate_payload["source_memory_ids"] == [
        "memory-large-a",
        "memory-large-b",
    ]
    assert approved_duplicate_payload["existing_compacted_item"]["id"] == compacted_item["id"]
    assert approved_duplicate_payload["compaction"] is None

    items_response = client.get("/memory-items?project_id=project_policy")
    compacted_items = [
        item
        for item in items_response.json()
        if item["metadata"].get("kind") == "compaction"
    ]
    assert [item["id"] for item in compacted_items] == [compacted_item["id"]]


def test_compact_memory_items_if_needed_skips_when_sources_fit_threshold() -> None:
    client = TestClient(app)
    response = client.post(
        "/memory-items",
        json={
            "id": "memory-small",
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "content": "Small fact.",
            "status": "approved",
        },
    )
    assert response.status_code == 201

    response = client.post(
        "/memory-items/compact-if-needed",
        json={
            "scope": "project:project_policy",
            "project_id": "project_policy",
            "min_source_tokens": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["compaction_needed"] is False
    assert payload["reason"] == "source_tokens_within_threshold"
    assert payload["threshold_tokens"] == 100
    assert payload["source_memory_ids"] == ["memory-small"]
    assert payload["existing_compacted_item"] is None
    assert payload["compaction"] is None

    items_response = client.get("/memory-items?project_id=project_policy")
    assert [item["id"] for item in items_response.json()] == ["memory-small"]


def test_memory_compaction_plan_discovers_overloaded_scopes_without_duplicates() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-plan-a",
            "scope": "project:project_plan",
            "project_id": "project_plan",
            "agent_id": "agent-ops",
            "content": "A" * 100,
            "status": "approved",
        },
        {
            "id": "memory-plan-b",
            "scope": "project:project_plan",
            "project_id": "project_plan",
            "agent_id": "agent-ops",
            "content": "B" * 100,
            "status": "approved",
        },
        {
            "id": "memory-small-scope",
            "scope": "project:project_plan_small",
            "project_id": "project_plan_small",
            "content": "Small fact.",
            "status": "approved",
        },
        {
            "id": "memory-other-project",
            "scope": "project:project_other",
            "project_id": "project_other",
            "content": "C" * 100,
            "status": "approved",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    response = client.post(
        "/memory-items/compaction-plan",
        json={
            "project_id": "project_plan",
            "min_source_tokens": 40,
            "max_source_items": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["threshold_tokens"] == 40
    assert payload["inspected_scope_count"] == 1
    assert payload["planned_scope_count"] == 1
    assert payload["items"] == [
        {
            "scope": "project:project_plan",
            "project_id": "project_plan",
            "agent_id": "agent-ops",
            "source_memory_ids": ["memory-plan-a", "memory-plan-b"],
            "source_count": 2,
            "source_tokens": 50,
        }
    ]

    compaction_response = client.post(
        "/memory-items/compact-if-needed",
        json={
            "scope": "project:project_plan",
            "project_id": "project_plan",
            "agent_id": "agent-ops",
            "min_source_tokens": 40,
            "max_source_items": 10,
        },
    )
    assert compaction_response.status_code == 200

    duplicate_plan_response = client.post(
        "/memory-items/compaction-plan",
        json={
            "project_id": "project_plan",
            "min_source_tokens": 40,
            "max_source_items": 10,
        },
    )
    assert duplicate_plan_response.status_code == 200
    duplicate_plan = duplicate_plan_response.json()
    assert duplicate_plan["inspected_scope_count"] == 1
    assert duplicate_plan["planned_scope_count"] == 0
    assert duplicate_plan["items"] == []


def test_memory_compaction_plan_respects_explicit_scope_allowlist() -> None:
    client = TestClient(app)
    for item in [
        {
            "id": "memory-active-a",
            "scope": "project:project_active",
            "project_id": "project_active",
            "content": "A" * 100,
            "status": "approved",
        },
        {
            "id": "memory-active-b",
            "scope": "project:project_active",
            "project_id": "project_active",
            "content": "B" * 100,
            "status": "approved",
        },
        {
            "id": "memory-archived-a",
            "scope": "project:project_archived",
            "project_id": "project_archived",
            "content": "C" * 100,
            "status": "approved",
        },
        {
            "id": "memory-archived-b",
            "scope": "project:project_archived",
            "project_id": "project_archived",
            "content": "D" * 100,
            "status": "approved",
        },
    ]:
        response = client.post("/memory-items", json=item)
        assert response.status_code == 201

    response = client.post(
        "/memory-items/compaction-plan",
        json={
            "scopes": ["project:project_active"],
            "min_source_tokens": 40,
            "max_source_items": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inspected_scope_count"] == 1
    assert payload["planned_scope_count"] == 1
    assert payload["items"][0]["scope"] == "project:project_active"
    assert payload["items"][0]["source_memory_ids"] == [
        "memory-active-a",
        "memory-active-b",
    ]

    empty_response = client.post(
        "/memory-items/compaction-plan",
        json={
            "scopes": [],
            "min_source_tokens": 40,
            "max_source_items": 10,
        },
    )
    assert empty_response.status_code == 200
    assert empty_response.json()["inspected_scope_count"] == 0
    assert empty_response.json()["planned_scope_count"] == 0
