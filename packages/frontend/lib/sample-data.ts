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
    value: "M2",
    detail: "Control Plane From State",
    tone: "accent" as Tone
  },
  {
    label: "Tests backend",
    value: "35",
    detail: "passing",
    tone: "ok" as Tone
  },
  {
    label: "Couches actives",
    value: "6/9",
    detail: "partielles ou en cours",
    tone: "info" as Tone
  },
  {
    label: "Approvals",
    value: "3",
    detail: "lifecycle queue",
    tone: "warn" as Tone
  }
];

export const currentFocus = {
  title: "Faire passer les agents par une gouvernance lisible",
  body:
    "Le state-service sait maintenant appliquer les demandes de creation ou desactivation d'agents apres decision humaine. Le control-plane expose cette file pour que l'interface devienne le poste de validation sans devenir source de verite.",
  checks: [
    "Lifecycle request cree un event approval.requested",
    "Decision approuvee applique agent.created ou agent.deactivated",
    "Agents inactifs bloques a l'assignation",
    "Control-plane relaie queue, creation et decision"
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
    progress: 28,
    summary:
      "Transformer un GoalEnvelope en projet, taches, routage et timeline persistants au lieu de retourner seulement un draft."
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
    summary: "Dashboard Next.js responsive, encore branche sur donnees locales.",
    next: "Lire projets, agents et timeline depuis les APIs."
  },
  {
    id: "B",
    name: "Orchestration",
    status: "partial" as Status,
    icon: Workflow,
    summary: "Gateway route les objectifs avec une logique deterministe par mots cles.",
    next: "Creer projet, taches et events depuis POST /goals."
  },
  {
    id: "C",
    name: "Control Plane",
    status: "partial" as Status,
    icon: ShieldCheck,
    summary: "LocalWorldView, services, policies et lifecycle queue passent par state-service.",
    next: "Brancher approval queue frontend sur control-plane."
  },
  {
    id: "D",
    name: "Domain Agents",
    status: "partial" as Status,
    icon: BrainCircuit,
    summary: "Runtime stub type et testable, pas encore de boucle agent persistante.",
    next: "Finance stub pour intake facture avec resultats verifies."
  },
  {
    id: "E",
    name: "Project / Workflow",
    status: "next" as Status,
    icon: Database,
    summary: "Contrats et endpoints existent. Les transitions de workflow restent a durcir.",
    next: "Goal -> project -> tasks -> events persistants."
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
    status: "later" as Status,
    icon: PlugZap,
    summary: "Contrats tool-call presents, execution reelle volontairement retardee.",
    next: "Registry + permission check avant execution."
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
    title: "TanStack Query API reads",
    done: false
  },
  {
    label: "M3.1",
    title: "Goal creates project",
    done: false
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
