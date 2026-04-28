import { Activity, Blocks, CircleDollarSign, Code2, FileText, Factory, GitBranch } from "lucide-react";

export const metrics = [
  { label: "Projets actifs", value: "4", tone: "accent" },
  { label: "Taches ouvertes", value: "18", tone: "warn" },
  { label: "Agents actifs", value: "5", tone: "ok" },
  { label: "Cout du jour", value: "12.84 EUR", tone: "risk" }
];

export const agents = [
  {
    id: "agent-direction",
    name: "IA Direction",
    division: "Direction",
    status: "active",
    icon: GitBranch,
    load: 72
  },
  {
    id: "agent-finance",
    name: "IA Finance",
    division: "Finance",
    status: "active",
    icon: CircleDollarSign,
    load: 44
  },
  {
    id: "agent-ops-sourcing",
    name: "IA Ops / Sourcing",
    division: "Ops",
    status: "active",
    icon: Factory,
    load: 58
  },
  {
    id: "agent-dev",
    name: "IA Dev",
    division: "Dev",
    status: "active",
    icon: Code2,
    load: 63
  },
  {
    id: "agent-admin-knowledge",
    name: "IA Admin / Knowledge",
    division: "Knowledge",
    status: "active",
    icon: FileText,
    load: 37
  }
];

export const projects = [
  {
    title: "Ingestion factures fournisseurs",
    owner: "IA Finance",
    status: "blocked",
    priority: "high",
    progress: 46
  },
  {
    title: "Gateway API phase 1",
    owner: "IA Dev",
    status: "running",
    priority: "critical",
    progress: 68
  },
  {
    title: "RFQ packaging Q2",
    owner: "IA Ops / Sourcing",
    status: "running",
    priority: "medium",
    progress: 31
  },
  {
    title: "Procedures internes",
    owner: "IA Admin / Knowledge",
    status: "queued",
    priority: "low",
    progress: 14
  }
];

export const events = [
  { time: "09:20", label: "goal.received", target: "Gateway", icon: Activity },
  { time: "09:21", label: "routing.decided", target: "IA Direction", icon: Blocks },
  { time: "09:24", label: "task.blocked", target: "IA Finance", icon: CircleDollarSign },
  { time: "09:31", label: "agent.reported", target: "IA Dev", icon: Code2 }
];
