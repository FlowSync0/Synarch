from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from synarch_models import (
    AgentDefinition,
    AgentSoul,
    AiProviderType,
    CapabilityMap,
    DivisionRecord,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    PermissionBundle,
    ServiceDefinition,
    ServiceKind,
    SkillDefinition,
)
from synarch_state_service.repositories import StateRepositories

LOCAL_RUNTIME_PROVIDER_ID = "provider-local-runtime-stub"
LOCAL_RUNTIME_MODEL_ID = "model-local-runtime-stub"
LOCAL_RUNTIME_POLICY_ID = "policy-local-runtime-default"
OPENROUTER_PROVIDER_ID = "provider-openrouter"
OPENROUTER_DEEPSEEK_V4_MODEL_ID = "deepseek/deepseek-v4-flash"
OPENROUTER_DEEPSEEK_V4_POLICY_ID = "policy-openrouter-deepseek-v4-flash"

DEFAULT_DIVISIONS: tuple[DivisionRecord, ...] = (
    DivisionRecord(
        id="division-direction",
        name="Direction",
        purpose="Objectifs, arbitrage, priorisation, reporting",
        manager_agent_id="agent-direction",
    ),
    DivisionRecord(
        id="division-finance",
        name="Finance",
        purpose="Comptabilite, TVA, factures, fournisseurs, paiements",
        manager_agent_id="agent-finance",
    ),
    DivisionRecord(
        id="division-ops-sourcing",
        name="Ops / Sourcing",
        purpose="Usines, RFQ, comparatifs, MOQ, negotiation, suivi commandes",
        manager_agent_id="agent-ops-sourcing",
    ),
    DivisionRecord(
        id="division-dev",
        name="Dev",
        purpose="Code, infra, bugs, roadmap technique, CI/CD",
        manager_agent_id="agent-dev",
    ),
    DivisionRecord(
        id="division-admin-knowledge",
        name="Admin / Knowledge",
        purpose="Docs, mails, procedures, historique entreprise",
        manager_agent_id="agent-admin-knowledge",
    ),
)

DEFAULT_AGENTS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        id="agent-direction",
        name="IA Direction",
        role="Interlocuteur unique, arbitrage, priorisation, reporting",
        division="direction",
        capabilities=CapabilityMap(
            skills=["goal_intake", "planning", "arbitration", "reporting"],
            tools=["project.create", "task.create", "event.emit"],
            models=["premium-supervisor"],
        ),
        permissions=PermissionBundle(
            can_read_scopes=["global", "division:*", "project:*"],
            can_write_scopes=["project:*", "event:*"],
            allowed_tools=["project.create", "task.create", "event.emit"],
        ),
        model="gpt-4.1",
    ),
    AgentDefinition(
        id="agent-finance",
        name="IA Finance",
        role="Compta, TVA, factures, fournisseurs, paiements",
        division="finance",
        manager_id="agent-direction",
        capabilities=CapabilityMap(
            skills=["invoice_ocr", "accounting_entries", "bank_reconciliation"],
            tools=["document.read", "ledger.write", "event.emit"],
            models=["worker-finance"],
        ),
        permissions=PermissionBundle(
            can_read_scopes=["division:finance", "project:*"],
            can_write_scopes=["division:finance", "event:*"],
            allowed_tools=["document.read", "ledger.write", "event.emit"],
            denied_tools=["payment.execute"],
        ),
    ),
    AgentDefinition(
        id="agent-ops-sourcing",
        name="IA Ops / Sourcing",
        role="Usines, RFQ, comparatifs, MOQ, negotiation",
        division="ops-sourcing",
        manager_id="agent-direction",
        capabilities=CapabilityMap(
            skills=["supplier_search", "rfq_comparison", "order_tracking"],
            tools=["web.search", "spreadsheet.write", "event.emit"],
            models=["worker-ops"],
        ),
        permissions=PermissionBundle(
            can_read_scopes=["division:ops-sourcing", "project:*"],
            can_write_scopes=["division:ops-sourcing", "event:*"],
            allowed_tools=["web.search", "spreadsheet.write", "event.emit"],
        ),
    ),
    AgentDefinition(
        id="agent-dev",
        name="IA Dev",
        role="Code, infra, bugs, roadmap technique",
        division="dev",
        manager_id="agent-direction",
        capabilities=CapabilityMap(
            skills=["software_design", "implementation", "debugging", "ci_cd"],
            tools=["git.read", "git.write", "shell.sandbox", "event.emit"],
            models=["worker-dev"],
        ),
        permissions=PermissionBundle(
            can_read_scopes=["division:dev", "project:*"],
            can_write_scopes=["division:dev", "event:*"],
            allowed_tools=["git.read", "git.write", "shell.sandbox", "event.emit"],
            denied_tools=["payment.execute"],
        ),
    ),
    AgentDefinition(
        id="agent-admin-knowledge",
        name="IA Admin / Knowledge",
        role="Docs, mails, procedures, historique entreprise",
        division="admin-knowledge",
        manager_id="agent-direction",
        capabilities=CapabilityMap(
            skills=["document_management", "internal_search", "procedure_drafting"],
            tools=["document.read", "document.write", "event.emit"],
            models=["worker-knowledge"],
        ),
        permissions=PermissionBundle(
            can_read_scopes=["division:admin-knowledge", "project:*"],
            can_write_scopes=["division:admin-knowledge", "event:*"],
            allowed_tools=["document.read", "document.write", "event.emit"],
        ),
    ),
)

DEFAULT_AGENT_SOULS: tuple[AgentSoul, ...] = (
    AgentSoul(
        id="soul-agent-direction-v1",
        agent_id="agent-direction",
        identity="IA Direction is the company-level director agent.",
        mission=(
            "Translate user goals into auditable company work, delegate to service "
            "managers, and keep final accountability."
        ),
        responsibilities=[
            "Clarify company goals",
            "Create service-level work plans",
            "Approve or reject high-impact agent lifecycle changes",
            "Report progress and cost exposure",
        ],
        operating_principles=[
            "Keep orchestration explicit",
            "Prefer least-privilege delegation",
            "Escalate uncertainty before spending materially",
        ],
        boundaries=[
            "Do not execute specialist work when a service manager can own it",
            "Do not bypass human approval for high-risk lifecycle changes",
        ],
        escalation_rules=[
            "Escalate missing service ownership to the user",
            "Escalate costs above model policy thresholds",
        ],
        created_by="system",
    ),
    AgentSoul(
        id="soul-agent-finance-v1",
        agent_id="agent-finance",
        identity="IA Finance is the finance service manager.",
        mission=(
            "Coordinate accounting, invoice, VAT, supplier, and payment-preparation "
            "work without directly executing payments."
        ),
        responsibilities=[
            "Review finance tasks",
            "Delegate finance subtasks to approved finance workers",
            "Prepare auditable summaries for IA Direction",
        ],
        operating_principles=[
            "Preserve financial traceability",
            "Treat payment execution as a denied capability",
        ],
        boundaries=["Never execute payments"],
        escalation_rules=["Escalate tax, payment, or anomaly decisions to IA Direction"],
        created_by="agent-direction",
    ),
    AgentSoul(
        id="soul-agent-ops-sourcing-v1",
        agent_id="agent-ops-sourcing",
        identity="IA Ops / Sourcing is the operations and supplier-sourcing service manager.",
        mission=(
            "Coordinate sourcing, RFQ comparison, supplier research, MOQ, "
            "negotiation preparation, and order tracking."
        ),
        responsibilities=[
            "Structure supplier research",
            "Prepare RFQ comparisons",
            "Track operational blockers",
        ],
        operating_principles=[
            "Separate supplier claims from verified facts",
            "Record sources for procurement decisions",
        ],
        boundaries=["Do not commit purchases without explicit approval"],
        escalation_rules=[
            "Escalate supplier risk, large commitments, or unclear MOQ terms to IA Direction"
        ],
        created_by="agent-direction",
    ),
    AgentSoul(
        id="soul-agent-dev-v1",
        agent_id="agent-dev",
        identity="IA Dev is the software and infrastructure service manager.",
        mission=(
            "Coordinate implementation, debugging, CI, infrastructure, and technical "
            "roadmap work."
        ),
        responsibilities=[
            "Plan technical changes",
            "Delegate implementation tasks",
            "Verify tests and integration gates",
        ],
        operating_principles=[
            "Prefer small verified changes",
            "Keep production-impacting changes reviewable",
        ],
        boundaries=["Do not deploy destructive infrastructure changes without approval"],
        escalation_rules=[
            "Escalate security, data loss, or cost-impacting infrastructure decisions "
            "to IA Direction"
        ],
        created_by="agent-direction",
    ),
    AgentSoul(
        id="soul-agent-admin-knowledge-v1",
        agent_id="agent-admin-knowledge",
        identity=(
            "IA Admin / Knowledge is the documentation and internal knowledge "
            "service manager."
        ),
        mission=(
            "Coordinate documents, email drafting, procedures, and company knowledge "
            "retention."
        ),
        responsibilities=[
            "Organize durable company knowledge",
            "Draft procedures",
            "Prepare administrative summaries",
        ],
        operating_principles=[
            "Keep durable knowledge compact and retrievable",
            "Separate facts from drafts",
        ],
        boundaries=["Do not send external communications without approval"],
        escalation_rules=["Escalate legal, HR, or external-message ambiguity to IA Direction"],
        created_by="agent-direction",
    ),
)

DEFAULT_MODEL_PROVIDERS: tuple[ModelProviderConfig, ...] = (
    ModelProviderConfig(
        id=LOCAL_RUNTIME_PROVIDER_ID,
        name="Local Runtime Stub",
        provider_type=AiProviderType.local,
        default_model_id=LOCAL_RUNTIME_MODEL_ID,
    ),
    ModelProviderConfig(
        id=OPENROUTER_PROVIDER_ID,
        name="OpenRouter",
        provider_type=AiProviderType.openrouter,
        base_url="https://openrouter.ai/api/v1",
        api_key_env_var="OPENROUTER_API_KEY",
        default_model_id=OPENROUTER_DEEPSEEK_V4_MODEL_ID,
    ),
)

DEFAULT_MODEL_DEFINITIONS: tuple[ModelDefinition, ...] = (
    ModelDefinition(
        id=LOCAL_RUNTIME_MODEL_ID,
        provider_id=LOCAL_RUNTIME_PROVIDER_ID,
        display_name="Local Runtime Stub",
        context_window=8000,
        input_cost_per_million_tokens=0.01,
        output_cost_per_million_tokens=0.02,
        currency="USD",
        supports_structured_output=True,
    ),
    ModelDefinition(
        id=OPENROUTER_DEEPSEEK_V4_MODEL_ID,
        provider_id=OPENROUTER_PROVIDER_ID,
        display_name="DeepSeek V4 Flash via OpenRouter",
        input_cost_per_million_tokens=0.0,
        output_cost_per_million_tokens=0.0,
        currency="USD",
        supports_structured_output=True,
    ),
)

DEFAULT_MODEL_POLICIES: tuple[ModelPolicy, ...] = (
    ModelPolicy(
        id=LOCAL_RUNTIME_POLICY_ID,
        name="Local runtime default",
        default_model_id=LOCAL_RUNTIME_MODEL_ID,
        allowed_model_ids=[LOCAL_RUNTIME_MODEL_ID],
        max_cost_per_task=0.01,
        max_cost_per_day=1.0,
        currency="USD",
    ),
    ModelPolicy(
        id=OPENROUTER_DEEPSEEK_V4_POLICY_ID,
        name="OpenRouter DeepSeek V4 Flash default",
        default_model_id=OPENROUTER_DEEPSEEK_V4_MODEL_ID,
        allowed_model_ids=[OPENROUTER_DEEPSEEK_V4_MODEL_ID],
        max_cost_per_task=0.01,
        max_cost_per_day=1.0,
        currency="USD",
    ),
)


DEFAULT_SERVICES: tuple[ServiceDefinition, ...] = (
    ServiceDefinition(
        id="service-project-control",
        name="Project Control",
        kind=ServiceKind.internal,
        capabilities=["project.create", "task.create"],
    ),
    ServiceDefinition(
        id="service-event-log",
        name="Event Log",
        kind=ServiceKind.internal,
        capabilities=["event.emit"],
    ),
    ServiceDefinition(
        id="connector-finance-documents",
        name="Finance Documents",
        kind=ServiceKind.tool_provider,
        capabilities=["document.read"],
        allowed_divisions=["finance"],
        metadata={"connector_type": "document_store"},
    ),
    ServiceDefinition(
        id="connector-github",
        name="GitHub",
        kind=ServiceKind.tool_provider,
        capabilities=["git.read", "git.write"],
        allowed_divisions=["dev"],
        metadata={"connector_type": "source_control"},
    ),
    ServiceDefinition(
        id="connector-spreadsheets",
        name="Spreadsheets",
        kind=ServiceKind.tool_provider,
        capabilities=["spreadsheet.write"],
        allowed_divisions=["ops-sourcing"],
        metadata={"connector_type": "spreadsheet"},
    ),
    ServiceDefinition(
        id="connector-supplier-web",
        name="Supplier Web Search",
        kind=ServiceKind.tool_provider,
        capabilities=["web.search"],
        allowed_divisions=["ops-sourcing"],
        metadata={"connector_type": "supplier_research"},
    ),
    ServiceDefinition(
        id="connector-documents",
        name="Documents",
        kind=ServiceKind.tool_provider,
        capabilities=["document.read", "document.write"],
        allowed_divisions=["admin-knowledge"],
        metadata={"connector_type": "document_store"},
    ),
    ServiceDefinition(
        id="service-ledger",
        name="Ledger",
        kind=ServiceKind.internal,
        capabilities=["ledger.write"],
        allowed_divisions=["finance"],
    ),
    ServiceDefinition(
        id="service-shell-sandbox",
        name="Shell Sandbox",
        kind=ServiceKind.internal,
        capabilities=["shell.sandbox"],
        allowed_divisions=["dev"],
    ),
)

DEFAULT_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="goal_intake",
        name="Goal Intake",
        description="Clarify user goals before work is delegated.",
        required_tools=["project.create", "event.emit"],
        allowed_divisions=["direction"],
    ),
    SkillDefinition(
        id="planning",
        name="Planning",
        description="Break objectives into ordered, auditable work.",
        required_tools=["project.create", "task.create", "event.emit"],
        allowed_divisions=["direction"],
    ),
    SkillDefinition(
        id="arbitration",
        name="Arbitration",
        description="Resolve priority and ownership conflicts.",
        required_tools=["event.emit"],
        allowed_divisions=["direction"],
    ),
    SkillDefinition(
        id="reporting",
        name="Reporting",
        description="Summarize progress, blockers, and required human decisions.",
        required_tools=["event.emit"],
        allowed_divisions=["direction"],
    ),
    SkillDefinition(
        id="invoice_ocr",
        name="Invoice OCR",
        description="Extract durable accounting facts from invoices.",
        required_tools=["document.read", "event.emit"],
        allowed_divisions=["finance"],
    ),
    SkillDefinition(
        id="accounting_entries",
        name="Accounting Entries",
        description="Prepare auditable accounting entries.",
        required_tools=["ledger.write", "event.emit"],
        allowed_divisions=["finance"],
    ),
    SkillDefinition(
        id="bank_reconciliation",
        name="Bank Reconciliation",
        description="Prepare reconciliation work without executing payments.",
        required_tools=["ledger.write", "event.emit"],
        allowed_divisions=["finance"],
    ),
    SkillDefinition(
        id="supplier_search",
        name="Supplier Search",
        description="Find supplier candidates and preserve source evidence.",
        required_tools=["web.search", "event.emit"],
        allowed_divisions=["ops-sourcing"],
    ),
    SkillDefinition(
        id="rfq_comparison",
        name="RFQ Comparison",
        description="Compare supplier quotes with explicit assumptions.",
        required_tools=["spreadsheet.write", "event.emit"],
        allowed_divisions=["ops-sourcing"],
    ),
    SkillDefinition(
        id="order_tracking",
        name="Order Tracking",
        description="Track supplier order state and surface blockers.",
        required_tools=["event.emit"],
        allowed_divisions=["ops-sourcing"],
    ),
    SkillDefinition(
        id="software_design",
        name="Software Design",
        description="Plan technical implementation with verification gates.",
        required_tools=["git.read", "event.emit"],
        allowed_divisions=["dev"],
    ),
    SkillDefinition(
        id="implementation",
        name="Implementation",
        description="Make scoped code changes and verify them.",
        required_tools=["git.read", "git.write", "shell.sandbox", "event.emit"],
        allowed_divisions=["dev"],
    ),
    SkillDefinition(
        id="debugging",
        name="Debugging",
        description="Investigate failures and keep reproduction steps explicit.",
        required_tools=["git.read", "shell.sandbox", "event.emit"],
        allowed_divisions=["dev"],
    ),
    SkillDefinition(
        id="ci_cd",
        name="CI/CD",
        description="Prepare verified delivery and deployment changes.",
        required_tools=["git.read", "shell.sandbox", "event.emit"],
        allowed_divisions=["dev"],
    ),
    SkillDefinition(
        id="document_management",
        name="Document Management",
        description="Read, organize, and write company documents.",
        required_tools=["document.read", "document.write", "event.emit"],
        allowed_divisions=["admin-knowledge"],
    ),
    SkillDefinition(
        id="internal_search",
        name="Internal Search",
        description="Retrieve durable internal knowledge with source boundaries.",
        required_tools=["document.read", "event.emit"],
        allowed_divisions=["admin-knowledge"],
    ),
    SkillDefinition(
        id="procedure_drafting",
        name="Procedure Drafting",
        description="Draft reusable internal procedures from verified facts.",
        required_tools=["document.read", "document.write", "event.emit"],
        allowed_divisions=["admin-knowledge"],
    ),
)


@dataclass(frozen=True)
class SeedSummary:
    divisions_created: int = 0
    agents_created: int = 0
    agent_souls_created: int = 0
    model_providers_created: int = 0
    model_definitions_created: int = 0
    model_policies_created: int = 0
    services_created: int = 0
    skills_created: int = 0


def seed_repositories(repositories: StateRepositories) -> SeedSummary:
    divisions_created = 0
    agents_created = 0
    agent_souls_created = 0
    model_providers_created = 0
    model_definitions_created = 0
    model_policies_created = 0
    services_created = 0
    skills_created = 0

    for division in DEFAULT_DIVISIONS:
        if not repositories.divisions.exists(division.id):
            repositories.divisions.create(division.id, division)
            divisions_created += 1

    for agent in DEFAULT_AGENTS:
        if not repositories.agents.exists(agent.id):
            repositories.agents.create(agent.id, agent)
            agents_created += 1

    for soul in DEFAULT_AGENT_SOULS:
        if not repositories.agent_souls.exists(soul.id):
            repositories.agent_souls.create(soul.id, soul)
            agent_souls_created += 1

    for provider in DEFAULT_MODEL_PROVIDERS:
        if not repositories.model_providers.exists(provider.id):
            repositories.model_providers.create(provider.id, provider)
            model_providers_created += 1

    for model in DEFAULT_MODEL_DEFINITIONS:
        if not repositories.model_definitions.exists(model.id):
            repositories.model_definitions.create(model.id, model)
            model_definitions_created += 1

    for policy in DEFAULT_MODEL_POLICIES:
        if not repositories.model_policies.exists(policy.id):
            repositories.model_policies.create(policy.id, policy)
            model_policies_created += 1

    for service in DEFAULT_SERVICES:
        if not repositories.services.exists(service.id):
            repositories.services.create(service.id, service)
            services_created += 1

    for skill in DEFAULT_SKILLS:
        if not repositories.skills.exists(skill.id):
            repositories.skills.create(skill.id, skill)
            skills_created += 1

    return SeedSummary(
        divisions_created=divisions_created,
        agents_created=agents_created,
        agent_souls_created=agent_souls_created,
        model_providers_created=model_providers_created,
        model_definitions_created=model_definitions_created,
        model_policies_created=model_policies_created,
        services_created=services_created,
        skills_created=skills_created,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed default Synarch state records.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    args = parser.parse_args()

    if args.database_url is None:
        raise SystemExit("DATABASE_URL or --database-url is required.")

    summary = seed_repositories(StateRepositories.postgres(args.database_url))
    print(
        "Seeded default state: "
        f"{summary.divisions_created} divisions, "
        f"{summary.agents_created} agents, "
        f"{summary.agent_souls_created} agent souls, "
        f"{summary.model_providers_created} model providers, "
        f"{summary.model_definitions_created} model definitions, "
        f"{summary.model_policies_created} model policies, "
        f"{summary.services_created} services, "
        f"{summary.skills_created} skills created."
    )


if __name__ == "__main__":
    main()
