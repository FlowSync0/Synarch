from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from synarch_models import (
    AgentDefinition,
    AiProviderType,
    CapabilityMap,
    DivisionRecord,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    PermissionBundle,
)
from synarch_state_service.repositories import StateRepositories

LOCAL_RUNTIME_PROVIDER_ID = "provider-local-runtime-stub"
LOCAL_RUNTIME_MODEL_ID = "model-local-runtime-stub"
LOCAL_RUNTIME_POLICY_ID = "policy-local-runtime-default"

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

DEFAULT_MODEL_PROVIDERS: tuple[ModelProviderConfig, ...] = (
    ModelProviderConfig(
        id=LOCAL_RUNTIME_PROVIDER_ID,
        name="Local Runtime Stub",
        provider_type=AiProviderType.local,
        default_model_id=LOCAL_RUNTIME_MODEL_ID,
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
)


@dataclass(frozen=True)
class SeedSummary:
    divisions_created: int = 0
    agents_created: int = 0
    model_providers_created: int = 0
    model_definitions_created: int = 0
    model_policies_created: int = 0


def seed_repositories(repositories: StateRepositories) -> SeedSummary:
    divisions_created = 0
    agents_created = 0
    model_providers_created = 0
    model_definitions_created = 0
    model_policies_created = 0

    for division in DEFAULT_DIVISIONS:
        if not repositories.divisions.exists(division.id):
            repositories.divisions.create(division.id, division)
            divisions_created += 1

    for agent in DEFAULT_AGENTS:
        if not repositories.agents.exists(agent.id):
            repositories.agents.create(agent.id, agent)
            agents_created += 1

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

    return SeedSummary(
        divisions_created=divisions_created,
        agents_created=agents_created,
        model_providers_created=model_providers_created,
        model_definitions_created=model_definitions_created,
        model_policies_created=model_policies_created,
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
        f"{summary.model_providers_created} model providers, "
        f"{summary.model_definitions_created} model definitions, "
        f"{summary.model_policies_created} model policies created."
    )


if __name__ == "__main__":
    main()
