from synarch_models import (
    ActorType,
    AgentDefinition,
    AgentLifecycleRequest,
    AgentSoul,
    AiProviderType,
    AuditLogRecord,
    CostRecord,
    CredentialAccessDecision,
    CredentialAccessRequest,
    DivisionRecord,
    LifecycleAction,
    LocalWorldView,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ModelUsage,
    ServiceDefinition,
    ServiceKind,
    SkillDefinition,
    ToolCallRequest,
)


def test_model_provider_and_policy_contracts_are_serializable() -> None:
    provider = ModelProviderConfig(
        id="provider-openrouter",
        name="OpenRouter",
        provider_type=AiProviderType.openrouter,
        base_url="https://openrouter.ai/api/v1",
        api_key_env_var="OPENROUTER_API_KEY",
        default_model_id="openrouter/deepseek/deepseek-chat",
    )
    model = ModelDefinition(
        id="openrouter/deepseek/deepseek-chat",
        provider_id=provider.id,
        display_name="DeepSeek Chat via OpenRouter",
        context_window=64000,
        input_cost_per_million_tokens=0.14,
        output_cost_per_million_tokens=0.28,
        supports_structured_output=True,
    )
    policy = ModelPolicy(
        id="policy-finance-default",
        name="Finance default routing",
        default_model_id=model.id,
        allowed_model_ids=[model.id],
        max_cost_per_day=2.5,
        require_human_approval_above=0.5,
    )

    assert provider.model_dump(mode="json")["provider_type"] == "openrouter"
    assert model.model_dump(mode="json")["supports_structured_output"] is True
    assert policy.model_dump(mode="json")["allowed_model_ids"] == [model.id]


def test_division_contract_captures_company_structure() -> None:
    division = DivisionRecord(
        id="division-finance",
        name="Finance",
        purpose="Comptabilite, TVA, factures, fournisseurs, paiements",
        manager_agent_id="agent-direction",
    )

    payload = division.model_dump(mode="json")

    assert payload["id"] == "division-finance"
    assert payload["manager_agent_id"] == "agent-direction"


def test_agent_lifecycle_request_requires_auditable_actor() -> None:
    proposed_agent = AgentDefinition(
        id="agent-finance-analyst",
        name="IA Finance Analyst",
        role="Analyse factures et anomalies TVA",
        division="finance",
        manager_id="agent-finance",
        allowed_model_ids=["openrouter/deepseek/deepseek-chat"],
        created_by="agent-direction",
    )
    request = AgentLifecycleRequest(
        action=LifecycleAction.create_agent,
        requested_by_type=ActorType.agent,
        requested_by_id="agent-direction",
        reason="Finance backlog needs a dedicated invoice analyst.",
        proposed_agent=proposed_agent,
    )

    payload = request.model_dump(mode="json")

    assert payload["action"] == "create_agent"
    assert payload["requires_human_approval"] is True
    assert payload["proposed_agent"]["created_by"] == "agent-direction"


def test_credential_access_request_captures_blocking_tool_scope() -> None:
    request = CredentialAccessRequest(
        id="credential-access-task-fetch-web",
        task_id="task_fetch",
        project_id="project_supplier",
        agent_id="agent-ops-sourcing",
        tool_name="web.fetch",
        requested_scopes=["browser:authenticated_fetch"],
        candidate_service_ids=["connector-supplier-web"],
        reason="Credential scopes missing for required tool: web.fetch",
    )

    payload = request.model_dump(mode="json")

    assert payload["status"] == "requested"
    assert payload["requested_by_type"] == "service"
    assert payload["requested_by_id"] == "gateway-scheduler"
    assert payload["requested_scopes"] == ["browser:authenticated_fetch"]
    assert payload["candidate_service_ids"] == ["connector-supplier-web"]


def test_credential_access_decision_is_auditable() -> None:
    decision = CredentialAccessDecision(
        request_id="credential-access-task-fetch-web",
        status="approved",
        decided_by_type=ActorType.user,
        decided_by_id="local-user",
        rationale="Access approved for a scoped supplier task.",
    )

    payload = decision.model_dump(mode="json")

    assert payload["request_id"] == "credential-access-task-fetch-web"
    assert payload["status"] == "approved"
    assert payload["decided_by_type"] == "user"
    assert payload["events_emitted"] == []


def test_agent_soul_captures_persistent_identity() -> None:
    soul = AgentSoul(
        agent_id="agent-finance",
        identity="IA Finance is the finance service manager for accounting and invoice review.",
        mission="Protect company finances by reviewing invoices and VAT anomalies.",
        responsibilities=["Review invoices", "Prepare accounting entries"],
        operating_principles=["Keep financial actions auditable"],
        boundaries=["Never execute payments"],
        escalation_rules=["Escalate payment or tax anomalies to agent-direction"],
        created_by="agent-direction",
    )
    world_view = LocalWorldView(
        agent_id="agent-finance",
        name="IA Finance",
        role="Compta, TVA, factures",
        division="finance",
        manager="agent-direction",
        manager_agent_id="agent-direction",
        peers=["agent-finance-analyst"],
        peer_agent_ids=["agent-finance-analyst"],
        direct_report_agent_ids=["agent-finance-intern"],
        soul=soul,
    )

    payload = world_view.model_dump(mode="json")

    assert payload["soul"]["mission"].startswith("Protect company finances")
    assert payload["soul"]["operating_principles"] == ["Keep financial actions auditable"]
    assert payload["soul"]["boundaries"] == ["Never execute payments"]
    assert payload["soul"]["created_by"] == "agent-direction"
    assert payload["name"] == "IA Finance"
    assert payload["manager_agent_id"] == "agent-direction"
    assert payload["peer_agent_ids"] == ["agent-finance-analyst"]
    assert payload["direct_report_agent_ids"] == ["agent-finance-intern"]


def test_cost_and_audit_records_have_traceable_scope() -> None:
    usage = ModelUsage(
        provider_id="provider-openrouter",
        model_id="deepseek/deepseek-v4-flash",
        input_tokens=1200,
        output_tokens=350,
        total_cost=0.000266,
    )
    cost = CostRecord(
        provider_id="provider-openrouter",
        model_id=usage.model_id,
        agent_id="agent-finance",
        project_id="project_invoice",
        task_id="task_extract",
        trace_id="trace_123",
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_cost=usage.total_cost,
    )
    audit = AuditLogRecord(
        actor_type=ActorType.agent,
        actor_id="agent-direction",
        action="agent_lifecycle.requested",
        target_type="agent",
        target_id="agent-finance-analyst",
        trace_id="trace_123",
    )
    service = ServiceDefinition(
        id="service-model-gateway",
        name="Model Gateway",
        kind=ServiceKind.internal,
        capabilities=["model.route", "cost.record", "model.policy.enforce"],
        allowed_divisions=["dev"],
        audit_required=True,
        metadata={"connector_type": "internal"},
    )
    skill = SkillDefinition(
        id="software_design",
        name="Software design",
        description="Plan technical implementation safely.",
        required_tools=["git.read"],
        allowed_divisions=["dev"],
    )

    assert usage.model_id == "deepseek/deepseek-v4-flash"
    assert cost.model_dump(mode="json")["trace_id"] == "trace_123"
    assert audit.model_dump(mode="json")["actor_type"] == "agent"
    assert service.model_dump(mode="json")["capabilities"] == [
        "model.route",
        "cost.record",
        "model.policy.enforce",
    ]
    assert service.model_dump(mode="json")["allowed_divisions"] == ["dev"]
    assert service.model_dump(mode="json")["audit_required"] is True
    assert service.model_dump(mode="json")["metadata"] == {"connector_type": "internal"}
    assert skill.model_dump(mode="json")["required_tools"] == ["git.read"]


def test_local_world_view_can_expose_state_backed_services_and_policies() -> None:
    world_view = LocalWorldView(
        agent_id="agent-finance",
        role="Compta, TVA, factures",
        division="finance",
        policies=["least_privilege_tools", "model_policy:policy-finance-default"],
        available_services=["service-model-gateway"],
        available_connector_ids=["connector-email"],
        available_skill_ids=["invoice_ocr"],
    )

    payload = world_view.model_dump(mode="json")

    assert payload["policies"] == ["least_privilege_tools", "model_policy:policy-finance-default"]
    assert payload["available_services"] == ["service-model-gateway"]
    assert payload["available_connector_ids"] == ["connector-email"]
    assert payload["available_skill_ids"] == ["invoice_ocr"]


def test_tool_call_request_carries_execution_scope() -> None:
    request = ToolCallRequest(
        agent_id="agent-dev",
        tool_name="git.read",
        service_id="connector-github",
        project_id="project_demo",
        task_id="task_demo",
        trace_id="trace_tool_demo",
        reason="Inspect the repository before changing code.",
        arguments={"path": "README.md"},
    )

    payload = request.model_dump(mode="json")

    assert payload["service_id"] == "connector-github"
    assert payload["project_id"] == "project_demo"
    assert payload["task_id"] == "task_demo"
    assert payload["trace_id"] == "trace_tool_demo"
