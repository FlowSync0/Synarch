from synarch_models import AgentDefinition, CapabilityMap, PermissionBundle

AGENTS: list[AgentDefinition] = [
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
]
