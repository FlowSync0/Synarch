import {
  Activity,
  AlertTriangle,
  Blocks,
  BrainCircuit,
  CheckCircle2,
  CircleDollarSign,
  Code2,
  Database,
  FileText,
  GitBranch,
  Network,
  PlugZap,
  RadioTower,
  ShieldCheck,
  Sparkles,
  UserRoundPlus,
  UserRoundX,
  Workflow
} from "lucide-react";

export type Tone = "accent" | "ok" | "warn" | "risk" | "info" | "neutral";
export type Status = "done" | "partial" | "next" | "later" | "blocked";

export const overview = [
  {
    label: "Gate courant",
    value: "M5.9",
    detail: "Connector job batch",
    tone: "accent" as Tone
  },
  {
    label: "Tests backend",
    value: "136",
    detail: "passed, 2 skipped",
    tone: "ok" as Tone
  },
  {
    label: "Couches actives",
    value: "7/9",
    detail: "partielles ou en cours",
    tone: "info" as Tone
  },
  {
    label: "Approvals",
    value: "0",
    detail: "lifecycle queue",
    tone: "warn" as Tone
  }
];

export const currentFocus = {
  title: "Connector job batch execution",
  body:
    "Le gateway peut executer un batch borne de jobs connecteurs actifs via le tool gate existant, puis enregistrer les runs et un tick durable dans le state-service.",
  checks: [
    "ConnectorJobRecord porte service, projet, tache, owner et kind",
    "ConnectorJobRunRecord garde sortie, erreur, trigger et trace",
    "Tick borne cree des runs skipped non fake quand aucun adaptateur n'est branche",
    "Execution gateway passe par permissions, service capabilities et credential scopes",
    "Batch gateway limite max_jobs et journalise connector_job.tick meme a vide",
    "Create, tick, execute, run et stop emettent connector_job.* et audit logs",
    "Tests backend complets passent"
  ]
};

export const projects = [
  {
    title: "Durable Company State",
    owner: "State Service",
    status: "partial",
    priority: "critical",
    progress: 72,
    summary:
      "Repositories memoire et PostgreSQL, migrations, seeds, audit automatique et lifecycle decisions appliquees."
  },
  {
    title: "Control Plane from State",
    owner: "Control Plane",
    status: "next",
    priority: "high",
    progress: 58,
    summary:
      "Lire agents, services, policies et lifecycle approvals depuis l'etat canonique expose par state-service."
  },
  {
    title: "Goal to Project Slice",
    owner: "Gateway",
    status: "partial",
    priority: "high",
    progress: 72,
    summary:
      "Transformer un GoalEnvelope en projet, workspace, assignments, taches et events persistants via gateway."
  },
  {
    title: "Live Control Surface",
    owner: "Frontend",
    status: "partial",
    priority: "medium",
    progress: 26,
    summary:
      "Afficher roadmap, agents, signaux, risques et file d'approbation avant branchement API live."
  }
];

export const agents = [
  {
    id: "agent-direction",
    name: "IA Direction",
    division: "Direction",
    status: "seed",
    icon: GitBranch,
    load: 72,
    scope: "Objectifs, arbitrage, priorisation"
  },
  {
    id: "agent-finance",
    name: "IA Finance",
    division: "Finance",
    status: "seed",
    icon: CircleDollarSign,
    load: 44,
    scope: "Factures, TVA, rapprochement"
  },
  {
    id: "agent-dev",
    name: "IA Dev",
    division: "Dev",
    status: "seed",
    icon: Code2,
    load: 63,
    scope: "Code, infra, CI/CD"
  },
  {
    id: "agent-admin-knowledge",
    name: "IA Admin / Knowledge",
    division: "Knowledge",
    status: "seed",
    icon: FileText,
    load: 37,
    scope: "Docs, procedures, historique"
  }
];

export const layers = [
  {
    id: "A",
    name: "Interface",
    status: "partial" as Status,
    icon: Sparkles,
    summary: "Dashboard Next.js lit projets, agents, timeline, approvals et review queue en live.",
    next: "Ajouter vues detaillees projet et taches."
  },
  {
    id: "B",
    name: "Orchestration",
    status: "partial" as Status,
    icon: Workflow,
    summary: "Gateway route les objectifs et persiste projet, workspace, assignments, taches et events.",
    next: "Exposer le lancement controle des taches depuis l'interface."
  },
  {
    id: "C",
    name: "Control Plane",
    status: "partial" as Status,
    icon: ShieldCheck,
    summary: "LocalWorldView, services, policies et lifecycle queue passent par state-service.",
    next: "Afficher historique decisions et demandes de split."
  },
  {
    id: "D",
    name: "Domain Agents",
    status: "partial" as Status,
    icon: BrainCircuit,
    summary: "Runtime type et testable avec boucle tool-call limitee a un round.",
    next: "Generaliser les outils et conditions d'arret par service."
  },
  {
    id: "E",
    name: "Project / Workflow",
    status: "partial" as Status,
    icon: Database,
    summary: "Goal submission cree projets et taches persistants avec events traces.",
    next: "Durcir les transitions run, blocked, review et completed."
  },
  {
    id: "F",
    name: "Memory",
    status: "partial" as Status,
    icon: Blocks,
    summary: "Memory items et context assembly basiques, encore en memoire.",
    next: "Scopes, budget token et stockage Postgres."
  },
  {
    id: "G",
    name: "Execution",
    status: "partial" as Status,
    icon: PlugZap,
    summary: "Tool gate, credential gates, health-checks et cycle de vie durable des jobs connecteurs existent.",
    next: "Ajouter runner cron/webhook borne qui execute les jobs actifs."
  },
  {
    id: "H",
    name: "Knowledge",
    status: "later" as Status,
    icon: Network,
    summary: "Connecteurs et ingestion restent conceptuels pour l'instant.",
    next: "Stub upload/source avec provenance."
  },
  {
    id: "I",
    name: "Observability",
    status: "partial" as Status,
    icon: RadioTower,
    summary: "Events, audit, couts et trace_id sont modelises.",
    next: "Propagation trace_id et instrumentation OTEL."
  }
];

export const timeline = [
  {
    time: "Maintenant",
    label: "lifecycle.applied",
    target: "State + Control Plane",
    icon: ShieldCheck,
    tone: "ok" as Tone
  },
  {
    time: "Suivant",
    label: "approval.queue.ui",
    target: "Frontend",
    icon: UserRoundPlus,
    tone: "accent" as Tone
  },
  {
    time: "Ensuite",
    label: "gateway.project.created",
    target: "Goal to Project",
    icon: Workflow,
    tone: "info" as Tone
  },
  {
    time: "Risque",
    label: "autonomy.too.early",
    target: "LLM retarde avant observability",
    icon: AlertTriangle,
    tone: "warn" as Tone
  }
];

export const backlog = [
  {
    label: "M2.1",
    title: "Approval queue UI",
    done: true
  },
  {
    label: "M2.2",
    title: "Task review queue UI",
    done: true
  },
  {
    label: "M3.1",
    title: "Goal creates project",
    done: true
  },
  {
    label: "M3.2",
    title: "Run ready tasks UI",
    done: true
  },
  {
    label: "M3.3",
    title: "Project task detail view",
    done: true
  },
  {
    label: "M3.4",
    title: "Timeline-driven task actions",
    done: true
  },
  {
    label: "M3.5",
    title: "Trace and event drilldown",
    done: true
  },
  {
    label: "M3.6",
    title: "Memory candidate review",
    done: true
  },
  {
    label: "M3.7",
    title: "Memory-aware run verification",
    done: true
  },
  {
    label: "M3.8",
    title: "Permissioned connector slice",
    done: true
  },
  {
    label: "M3.9",
    title: "Concrete connector adapters",
    done: true
  },
  {
    label: "M4.1",
    title: "Tool-use runtime loop",
    done: true
  },
  {
    label: "M4.2",
    title: "Scheduler worker live loop",
    done: true
  },
  {
    label: "M4.3",
    title: "Connector registry hardening",
    done: true
  },
  {
    label: "M4.4",
    title: "Executable adapter registry",
    done: true
  },
  {
    label: "M4.5",
    title: "Adapter manifests and scopes",
    done: true
  },
  {
    label: "M4.6",
    title: "Credential scope enforcement",
    done: true
  },
  {
    label: "M4.7",
    title: "Credential status observability",
    done: true
  },
  {
    label: "M4.8",
    title: "Credential readiness in scheduler",
    done: true
  },
  {
    label: "M4.9",
    title: "Visible scheduler skip reasons",
    done: true
  },
  {
    label: "M5.1",
    title: "Credential request workflow",
    done: true
  },
  {
    label: "M5.2",
    title: "Credential request decisions",
    done: true
  },
  {
    label: "M5.3",
    title: "Credential grant application",
    done: true
  },
  {
    label: "M5.4",
    title: "Credential-gated task resume",
    done: true
  },
  {
    label: "M5.5",
    title: "Service health checks",
    done: true
  },
  {
    label: "M5.6",
    title: "Connector job lifecycle",
    done: true
  },
  {
    label: "M2",
    title: "Lifecycle decisions",
    done: true
  },
  {
    label: "M1",
    title: "State repositories",
    done: true
  }
];

export const taskReviews = [
  {
    id: "task-review-sample-supplier-rfq",
    title: "Verifier le plan RFQ fournisseur moteur",
    projectId: "project-sourcing-sample",
    assignedAgentId: "agent-ops-sourcing",
    status: "needs_review",
    reason: "max_attempts_exceeded: le fournisseur cible n'a pas repondu apres les relances prevues.",
    attempts: "3/3",
    criteria: [
      "Documenter les fournisseurs contactes",
      "Proposer la prochaine action sans spam"
    ],
    age: "24 min"
  },
  {
    id: "task-review-sample-memory",
    title: "Nettoyer une synthese projet trop large",
    projectId: "project-knowledge-sample",
    assignedAgentId: "agent-admin-knowledge",
    status: "needs_review",
    reason: "acceptance_criteria_failed: la synthese melange deux scopes projet.",
    attempts: "2/2",
    criteria: [
      "Separer les faits par projet",
      "Conserver provenance et trace_id"
    ],
    age: "41 min"
  }
];

export const approvals = [
  {
    id: "lifecycle-create-finance-reviewer",
    title: "IA Finance Reviewer",
    action: "create_agent",
    requester: "agent-direction",
    division: "Finance",
    status: "requested",
    age: "12 min",
    tone: "accent" as Tone,
    icon: UserRoundPlus,
    impact: "Ajoute un role de revue facture avant validation humaine des exceptions."
  },
  {
    id: "lifecycle-deactivate-temporary-worker",
    title: "IA Temporary Worker",
    action: "deactivate_agent",
    requester: "local-user",
    division: "Dev",
    status: "applied",
    age: "38 min",
    tone: "ok" as Tone,
    icon: UserRoundX,
    impact: "Retire un worker court terme de l'assignation des nouvelles taches."
  },
  {
    id: "lifecycle-create-ops-extra",
    title: "IA Ops Extra",
    action: "create_agent",
    requester: "agent-ops-sourcing",
    division: "Ops",
    status: "requested",
    age: "1 h",
    tone: "warn" as Tone,
    icon: UserRoundPlus,
    impact: "Propose une capacite RFQ additionnelle pour le flux sourcing."
  }
];

export const riskControls = [
  {
    title: "Pas d'autonomie avant les traces",
    detail: "Les appels modele doivent produire event, cout, audit et trace avant d'etre utiles.",
    icon: ShieldCheck
  },
  {
    title: "Le projet n'est pas un chat",
    detail: "Tasks, events, approvals et memory candidates restent des records structures.",
    icon: CheckCircle2
  },
  {
    title: "Frontend lecteur, pas source",
    detail: "L'interface affiche et declenche via API. Elle ne cache pas de logique metier.",
    icon: Activity
  }
];
