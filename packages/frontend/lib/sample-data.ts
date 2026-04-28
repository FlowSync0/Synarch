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
  Fingerprint,
  GitBranch,
  Network,
  PlugZap,
  RadioTower,
  ShieldCheck,
  Sparkles,
  Workflow
} from "lucide-react";

export type Tone = "accent" | "ok" | "warn" | "risk" | "info" | "neutral";
export type Status = "done" | "partial" | "next" | "later" | "blocked";

export const overview = [
  {
    label: "Gate courant",
    value: "M1",
    detail: "Durable Company State",
    tone: "accent" as Tone
  },
  {
    label: "Tests backend",
    value: "12",
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
    label: "Dette critique",
    value: "Postgres",
    detail: "state encore memoire",
    tone: "warn" as Tone
  }
];

export const currentFocus = {
  title: "Rendre Synarch durable avant l'autonomie",
  body:
    "Le prochain passage transforme le state-service en source canonique PostgreSQL, tout en gardant des repositories memoire rapides pour les tests. Les agents et le frontend viendront lire cet etat au lieu de porter leur propre verite.",
  checks: [
    "Repository interface pour company state",
    "Persistence Postgres avec restart survival",
    "Audit et couts lisibles par trace_id",
    "Gateway pret a creer de vrais projets"
  ]
};

export const projects = [
  {
    title: "Durable Company State",
    owner: "State Service",
    status: "next",
    priority: "critical",
    progress: 34,
    summary:
      "Brancher divisions, agents, projects, tasks, events, model policies, costs et audit logs sur une couche repository testable."
  },
  {
    title: "Control Plane from State",
    owner: "Control Plane",
    status: "partial",
    priority: "high",
    progress: 22,
    summary:
      "Remplacer les seeds Python par des vues deterministes construites depuis l'etat canonique et les permissions."
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
    progress: 18,
    summary:
      "Connecter le dashboard aux APIs pour afficher projets, agents, timeline, couts et validations sans devenir source de verite."
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
    summary: "LocalWorldView et permissions existent, mais les agents sont encore seedes.",
    next: "Lire agents, services et policies depuis state-service."
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
    summary: "Contrats et endpoints existent. La persistance durable est le chantier actif.",
    next: "Repositories Postgres et restart survival."
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
    label: "state.company.expanded",
    target: "State Service",
    icon: Database,
    tone: "ok" as Tone
  },
  {
    time: "Suivant",
    label: "repository.interface",
    target: "In-memory + PostgreSQL",
    icon: Fingerprint,
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
    label: "M1.1",
    title: "Repository interface",
    done: false
  },
  {
    label: "M1.2",
    title: "PostgreSQL persistence",
    done: false
  },
  {
    label: "M1.3",
    title: "Restart survival test",
    done: false
  },
  {
    label: "M0",
    title: "Backend verify local",
    done: true
  },
  {
    label: "M0",
    title: "Roadmap 9 couches",
    done: true
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
