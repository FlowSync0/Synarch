from synarch_models import (
    ActorType,
    AgentDefinition,
    AgentLifecycleRequest,
    AiProviderType,
    AuditLogRecord,
    CostRecord,
    DivisionRecord,
    LifecycleAction,
    LocalWorldView,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ServiceDefinition,
    ServiceKind,
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


def test_cost_and_audit_records_have_traceable_scope() -> None:
    cost = CostRecord(
        provider_id="provider-openrouter",
        model_id="openrouter/deepseek/deepseek-chat",
        agent_id="agent-finance",
        project_id="project_invoice",
        task_id="task_extract",
        trace_id="trace_123",
        input_tokens=1200,
        output_tokens=350,
        total_cost=0.000266,
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
    )

    assert cost.model_dump(mode="json")["trace_id"] == "trace_123"
    assert audit.model_dump(mode="json")["actor_type"] == "agent"
    assert service.model_dump(mode="json")["capabilities"] == [
        "model.route",
        "cost.record",
        "model.policy.enforce",
    ]


def test_local_world_view_can_expose_state_backed_services_and_policies() -> None:
    world_view = LocalWorldView(
        agent_id="agent-finance",
        role="Compta, TVA, factures",
        division="finance",
        policies=["least_privilege_tools", "model_policy:policy-finance-default"],
        available_services=["service-model-gateway"],
    )

    payload = world_view.model_dump(mode="json")

    assert payload["policies"] == ["least_privilege_tools", "model_policy:policy-finance-default"]
    assert payload["available_services"] == ["service-model-gateway"]
