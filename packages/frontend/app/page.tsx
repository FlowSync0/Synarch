"use client";

import { prepareWithSegments, layoutWithLines } from "@chenglou/pretext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Code2,
  Command,
  FileText,
  GitBranch,
  Layers3,
  Menu,
  Network,
  Plus,
  Search,
  Settings2,
  UserRoundPlus,
  UserRoundX,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  decideAgentLifecycleRequest,
  listAgents,
  listAgentLifecycleRequests,
  type AgentDefinition,
  type AgentLifecycleRequest
} from "../lib/control-plane-api";
import { listProjects, type ProjectRecord } from "../lib/state-service-api";
import {
  agents,
  approvals,
  backlog,
  currentFocus,
  layers,
  overview,
  projects,
  riskControls,
  timeline,
  type Status,
  type Tone
} from "../lib/sample-data";

const toneClass: Record<Tone, string> = {
  accent: "text-accent",
  ok: "text-ok",
  warn: "text-warn",
  risk: "text-risk",
  info: "text-info",
  neutral: "text-muted"
};

const toneSurface: Record<Tone, string> = {
  accent: "bg-accent-soft text-accent ring-accent/15",
  ok: "bg-ok-soft text-ok ring-ok/15",
  warn: "bg-warn-soft text-warn ring-warn/15",
  risk: "bg-risk-soft text-risk ring-risk/15",
  info: "bg-info-soft text-info ring-info/15",
  neutral: "bg-slate-100 text-muted ring-border"
};

const statusLabel: Record<Status, string> = {
  done: "Done",
  partial: "Partial",
  next: "Next",
  later: "Later",
  blocked: "Blocked"
};

const statusClass: Record<Status, string> = {
  done: "bg-ok-soft text-ok ring-ok/15",
  partial: "bg-info-soft text-info ring-info/15",
  next: "bg-accent-soft text-accent ring-accent/15",
  later: "bg-slate-100 text-muted ring-border",
  blocked: "bg-risk-soft text-risk ring-risk/15"
};

const projectStatusClass: Record<string, string> = {
  partial: "text-info",
  next: "text-accent",
  later: "text-muted",
  done: "text-ok",
  blocked: "text-risk",
  draft: "text-muted",
  queued: "text-accent",
  running: "text-info",
  completed: "text-ok",
  failed: "text-risk",
  needs_review: "text-warn"
};

const approvalStatusClass: Record<string, string> = {
  requested: "bg-warn-soft text-warn ring-warn/15",
  approved: "bg-info-soft text-info ring-info/15",
  applied: "bg-ok-soft text-ok ring-ok/15",
  rejected: "bg-risk-soft text-risk ring-risk/15"
};

const dataModeClass: Record<string, string> = {
  live: "bg-ok-soft text-ok ring-ok/15",
  syncing: "bg-info-soft text-info ring-info/15",
  sample: "bg-warn-soft text-warn ring-warn/15"
};

const agentStatusClass: Record<string, string> = {
  active: "bg-ok-soft text-ok ring-ok/15",
  inactive: "bg-slate-100 text-muted ring-border",
  degraded: "bg-warn-soft text-warn ring-warn/15",
  pending_approval: "bg-info-soft text-info ring-info/15",
  seed: "bg-slate-100 text-muted ring-border"
};

type BalancedTextProps = {
  children: string;
  className?: string;
  font?: string;
  lineHeight?: number;
};

function BalancedText({
  children,
  className = "",
  font = "400 14px Inter Variable",
  lineHeight = 20
}: BalancedTextProps) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [lines, setLines] = useState<string[] | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined" || !("Segmenter" in Intl)) {
      setLines(null);
      return;
    }

    let frame = 0;
    const prepared = prepareWithSegments(children, font, { whiteSpace: "normal" });
    const observer = new ResizeObserver(([entry]) => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const width = Math.floor(entry.contentRect.width);
        if (width < 24) {
          setLines(null);
          return;
        }
        const result = layoutWithLines(prepared, width, lineHeight);
        setLines(result.lines.map((line) => line.text.trimEnd()));
      });
    });

    observer.observe(node);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [children, font, lineHeight]);

  return (
    <p ref={ref} className={className} aria-label={children} style={{ lineHeight: `${lineHeight}px` }}>
      {lines ? (
        <span aria-hidden="true">
          {lines.map((line, index) => (
            <span key={`${line}-${index}`} className="block">
              {line}
            </span>
          ))}
        </span>
      ) : (
        children
      )}
    </p>
  );
}

function SectionHeader({
  eyebrow,
  title,
  action
}: {
  eyebrow: string;
  title: string;
  action?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/80 px-4 py-3">
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-normal text-muted">{eyebrow}</p>
        <h2 className="mt-1 truncate text-sm font-semibold text-ink">{title}</h2>
      </div>
      {action ? (
        <button className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border bg-white text-muted transition hover:border-accent/40 hover:text-accent">
          <ArrowUpRight size={16} />
          <span className="sr-only">{action}</span>
        </button>
      ) : null}
    </div>
  );
}

function ProgressBar({ value, tone = "accent" }: { value: number; tone?: Tone }) {
  const barClass = {
    accent: "bg-accent",
    ok: "bg-ok",
    warn: "bg-warn",
    risk: "bg-risk",
    info: "bg-info",
    neutral: "bg-muted"
  }[tone];

  return (
    <div className="h-2 rounded-full bg-slate-200">
      <motion.div
        className={`h-2 rounded-full ${barClass}`}
        initial={false}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      />
    </div>
  );
}

type ApprovalViewModel = {
  id: string;
  title: string;
  action: string;
  requester: string;
  division: string;
  status: string;
  age: string;
  tone: Tone;
  icon: typeof UserRoundPlus;
  impact: string;
  source: "api" | "sample";
};

type AgentViewModel = {
  id: string;
  name: string;
  status: string;
  load: number;
  scope: string;
  division: string;
  icon: typeof GitBranch;
  source: "api" | "sample";
};

type ProjectViewModel = {
  id: string;
  title: string;
  owner: string;
  status: string;
  priority: string;
  progress: number;
  summary: string;
  source: "api" | "sample";
};

function formatLifecycleAge(createdAt: string): string {
  const timestamp = new Date(createdAt).getTime();
  if (Number.isNaN(timestamp)) {
    return "now";
  }

  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60_000));
  if (minutes < 1) {
    return "now";
  }
  if (minutes < 60) {
    return `${minutes} min`;
  }

  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} h`;
  }

  return `${Math.round(hours / 24)} d`;
}

function lifecycleTone(request: AgentLifecycleRequest): Tone {
  if (request.status === "applied") {
    return "ok";
  }
  if (request.status === "rejected") {
    return "risk";
  }
  if (request.action === "deactivate_agent") {
    return "warn";
  }
  return "accent";
}

function lifecycleIcon(request: AgentLifecycleRequest): typeof UserRoundPlus {
  if (request.action === "deactivate_agent") {
    return UserRoundX;
  }
  return UserRoundPlus;
}

function lifecycleApprovalRow(request: AgentLifecycleRequest): ApprovalViewModel {
  return {
    id: request.id,
    title: request.proposed_agent?.name ?? request.target_agent_id ?? request.id,
    action: request.action,
    requester: request.requested_by_id,
    division: request.proposed_agent?.division ?? "Org",
    status: request.status,
    age: formatLifecycleAge(request.created_at),
    tone: lifecycleTone(request),
    icon: lifecycleIcon(request),
    impact: request.reason,
    source: "api"
  };
}

function agentIcon(agent: AgentDefinition): typeof GitBranch {
  const division = agent.division.toLowerCase();
  if (division.includes("finance")) {
    return CircleDollarSign;
  }
  if (division.includes("dev")) {
    return Code2;
  }
  if (division.includes("admin") || division.includes("knowledge")) {
    return FileText;
  }
  if (division.includes("ops") || division.includes("sourcing")) {
    return Network;
  }
  return GitBranch;
}

function agentLoad(agent: AgentDefinition): number {
  if (agent.status === "inactive") {
    return 0;
  }
  if (agent.status === "degraded") {
    return 92;
  }

  const toolWeight = agent.permissions.allowed_tools.length * 7;
  const skillWeight = agent.capabilities.skills.length * 5;
  return Math.min(88, 30 + toolWeight + skillWeight);
}

function agentRow(agent: AgentDefinition): AgentViewModel {
  return {
    id: agent.id,
    name: agent.name,
    status: agent.status,
    load: agentLoad(agent),
    scope: agent.role,
    division: agent.division,
    icon: agentIcon(agent),
    source: "api"
  };
}

function projectProgress(project: ProjectRecord): number {
  const progressByStatus: Record<string, number> = {
    draft: 8,
    queued: 18,
    running: 52,
    needs_review: 68,
    blocked: 64,
    failed: 100,
    completed: 100
  };
  return progressByStatus[project.status] ?? 15;
}

function projectProgressTone(status: string): Tone {
  if (status === "completed") {
    return "ok";
  }
  if (status === "blocked" || status === "failed") {
    return "risk";
  }
  if (status === "needs_review") {
    return "warn";
  }
  if (status === "running") {
    return "info";
  }
  return "accent";
}

function projectRow(project: ProjectRecord): ProjectViewModel {
  return {
    id: project.id,
    title: project.title,
    owner: project.owner_agent_id,
    status: project.status,
    priority: project.priority,
    progress: projectProgress(project),
    summary: project.goal,
    source: "api"
  };
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    refetchInterval: 30_000
  });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents,
    refetchInterval: 30_000
  });
  const lifecycleQuery = useQuery({
    queryKey: ["agent-lifecycle-requests"],
    queryFn: listAgentLifecycleRequests,
    refetchInterval: 15_000
  });
  const decisionMutation = useMutation({
    mutationFn: decideAgentLifecycleRequest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
    }
  });
  const layerStats = useMemo(
    () => ({
      next: layers.filter((layer) => layer.status === "next").length,
      partial: layers.filter((layer) => layer.status === "partial").length,
      later: layers.filter((layer) => layer.status === "later").length
    }),
    []
  );
  const approvalRows = useMemo<ApprovalViewModel[]>(() => {
    if (lifecycleQuery.isSuccess) {
      return lifecycleQuery.data.map(lifecycleApprovalRow);
    }

    return approvals.map((approval) => ({
      ...approval,
      source: "sample" as const
    }));
  }, [lifecycleQuery.data, lifecycleQuery.isSuccess]);
  const approvalMode = lifecycleQuery.isLoading
    ? "syncing"
    : lifecycleQuery.isError
      ? "sample"
      : "live";
  const approvalModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "Sample fallback"
  }[approvalMode];
  const approvalModeDetail =
    approvalMode === "live"
      ? `${approvalRows.length} lifecycle records from control-plane`
      : approvalMode === "syncing"
        ? "Connecting to control-plane"
        : "Control-plane unavailable, showing sample lifecycle records";
  const agentRows = useMemo<AgentViewModel[]>(() => {
    if (agentsQuery.isSuccess) {
      return agentsQuery.data.map(agentRow);
    }

    return agents.map((agent) => ({
      ...agent,
      source: "sample" as const
    }));
  }, [agentsQuery.data, agentsQuery.isSuccess]);
  const agentMode = agentsQuery.isLoading ? "syncing" : agentsQuery.isError ? "sample" : "live";
  const agentModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "Sample fallback"
  }[agentMode];
  const agentModeDetail =
    agentMode === "live"
      ? `${agentRows.length} agents from control-plane`
      : agentMode === "syncing"
        ? "Connecting to control-plane"
        : "Control-plane unavailable, showing seeded agents";
  const projectRows = useMemo<ProjectViewModel[]>(() => {
    if (projectsQuery.isSuccess) {
      return projectsQuery.data.map(projectRow);
    }

    return projects.map((project) => ({
      ...project,
      id: project.title,
      source: "sample" as const
    }));
  }, [projectsQuery.data, projectsQuery.isSuccess]);
  const projectMode = projectsQuery.isLoading
    ? "syncing"
    : projectsQuery.isError
      ? "sample"
      : "live";
  const projectModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "Sample fallback"
  }[projectMode];
  const projectModeDetail =
    projectMode === "live"
      ? `${projectRows.length} projects from state-service`
      : projectMode === "syncing"
        ? "Connecting to state-service"
        : "State-service unavailable, showing roadmap projects";

  return (
    <main className="min-h-screen bg-app text-ink">
      <header className="sticky top-0 z-30 border-b border-border/80 bg-panel/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3 px-4 py-3 sm:px-5">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <button
              className="grid h-10 w-10 place-items-center rounded-md border border-border bg-white text-muted lg:hidden"
              aria-label="Menu"
              title="Menu"
            >
              <Menu size={18} />
            </button>
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-ink text-white shadow-soft">
              <Command size={18} />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-normal text-accent">Synarch</p>
              <h1 className="truncate text-xl font-semibold tracking-normal sm:text-2xl">
                Control Surface
              </h1>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              className="hidden h-10 items-center gap-2 rounded-md border border-border bg-white px-3 text-sm text-muted transition hover:border-accent/40 hover:text-accent sm:flex"
              aria-label="Search"
              title="Search"
            >
              <Search size={17} />
              <span className="hidden md:inline">Rechercher</span>
            </button>
            <button
              className="hidden h-10 w-10 place-items-center rounded-md border border-border bg-white text-muted transition hover:border-accent/40 hover:text-accent sm:grid"
              aria-label="Settings"
              title="Settings"
            >
              <Settings2 size={18} />
            </button>
            <button
              className="flex h-10 w-10 items-center justify-center gap-2 rounded-md bg-accent text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong sm:w-auto sm:px-3"
              aria-label="Nouvel objectif"
              title="Nouvel objectif"
            >
              <Plus size={18} />
              <span className="hidden sm:inline">Objectif</span>
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1440px] gap-4 px-4 py-4 sm:px-5 lg:grid-cols-[72px_minmax(0,1fr)_360px] xl:grid-cols-[88px_minmax(0,1fr)_400px]">
        <nav className="hidden rounded-md border border-border bg-panel p-2 lg:block">
          <div className="flex flex-col gap-2">
            {[Command, Layers3, Clock3, Settings2].map((Icon, index) => (
              <button
                key={index}
                className={`grid h-11 w-full place-items-center rounded-md transition ${
                  index === 0 ? "bg-ink text-white" : "text-muted hover:bg-slate-100 hover:text-ink"
                }`}
                aria-label={`Navigation ${index + 1}`}
                title={`Navigation ${index + 1}`}
              >
                <Icon size={18} />
              </button>
            ))}
          </div>
        </nav>

        <section className="min-w-0 space-y-4">
          <motion.section
            className="overflow-hidden rounded-md border border-border bg-panel"
            initial={false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)]">
              <div className="min-w-0">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent ring-1 ring-accent/15">
                    Roadmap active
                  </span>
                  <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-muted ring-1 ring-border">
                    9 couches suivies
                  </span>
                </div>
                <h2 className="max-w-3xl text-2xl font-semibold tracking-normal text-ink sm:text-3xl">
                  {currentFocus.title}
                </h2>
                <BalancedText className="mt-3 max-w-3xl text-sm text-muted" lineHeight={21}>
                  {currentFocus.body}
                </BalancedText>
              </div>
              <div className="grid min-w-0 gap-2 rounded-md bg-slate-50 p-3">
                {currentFocus.checks.map((check) => (
                  <div key={check} className="flex items-center gap-2 text-sm text-ink">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white text-accent ring-1 ring-border">
                      <Check size={14} />
                    </span>
                    <span className="min-w-0 break-words">{check}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.section>

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {overview.map((metric, index) => (
              <motion.article
                key={metric.label}
                className="rounded-md border border-border bg-panel p-4"
                initial={false}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04, duration: 0.35 }}
              >
                <p className="text-sm text-muted">{metric.label}</p>
                <p className={`mt-2 text-2xl font-semibold tracking-normal ${toneClass[metric.tone]}`}>
                  {metric.value}
                </p>
                <p className="mt-1 truncate text-xs text-muted">{metric.detail}</p>
              </motion.article>
            ))}
          </section>

          <section className="rounded-md border border-border bg-panel">
            <SectionHeader eyebrow="Execution" title="Chantiers produit" action="Voir les projets" />
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">{projectModeDetail}</p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[projectMode]}`}
              >
                {projectModeLabel}
              </span>
            </div>
            <div className="divide-y divide-border">
              {projectRows.length === 0 ? (
                <article className="px-4 py-5">
                  <p className="text-sm font-medium text-ink">Aucun projet disponible</p>
                  <p className="mt-1 text-xs text-muted">Le state-service ne retourne aucun projet.</p>
                </article>
              ) : null}
              {projectRows.map((project) => (
                <article
                  key={project.id}
                  className="grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1fr)_112px_150px]"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-ink">{project.title}</h3>
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-normal text-muted">
                        {project.priority}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">{project.owner}</p>
                    <BalancedText className="mt-2 text-sm text-muted" font="400 13px Inter Variable" lineHeight={18}>
                      {project.summary}
                    </BalancedText>
                  </div>
                  <div>
                    <p className={`text-sm font-medium ${projectStatusClass[project.status]}`}>
                      {project.status}
                    </p>
                    <p className="mt-1 text-xs text-muted">roadmap</p>
                  </div>
                  <div className="space-y-2">
                    <ProgressBar value={project.progress} tone={projectProgressTone(project.status)} />
                    <p className="text-right text-xs text-muted">{project.progress}%</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel">
            <SectionHeader
              eyebrow="Architecture"
              title={`9 couches: ${layerStats.next} next, ${layerStats.partial} partial, ${layerStats.later} later`}
              action="Voir roadmap"
            />
            <div className="grid gap-px bg-border sm:grid-cols-2 xl:grid-cols-3">
              {layers.map((layer) => {
                const Icon = layer.icon;
                return (
                  <article key={layer.id} className="min-w-0 bg-panel p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-slate-100 text-ink">
                          <Icon size={17} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-[11px] font-semibold uppercase text-muted">Layer {layer.id}</p>
                          <h3 className="truncate text-sm font-semibold">{layer.name}</h3>
                        </div>
                      </div>
                      <span
                        className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${statusClass[layer.status]}`}
                      >
                        {statusLabel[layer.status]}
                      </span>
                    </div>
                    <BalancedText className="mt-3 text-sm text-muted" font="400 13px Inter Variable" lineHeight={18}>
                      {layer.summary}
                    </BalancedText>
                    <div className="mt-3 flex items-center gap-2 text-xs font-medium text-accent">
                      <ChevronRight size={14} />
                      <span className="min-w-0 truncate">{layer.next}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </section>

        <aside className="space-y-4 lg:sticky lg:top-[76px] lg:self-start">
          <section className="rounded-md border border-border bg-panel">
            <SectionHeader eyebrow="Agents" title="Organisation IA" action="Voir agents" />
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">{agentModeDetail}</p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[agentMode]}`}
              >
                {agentModeLabel}
              </span>
            </div>
            <div className="divide-y divide-border">
              {agentRows.length === 0 ? (
                <article className="px-4 py-5">
                  <p className="text-sm font-medium text-ink">Aucun agent disponible</p>
                  <p className="mt-1 text-xs text-muted">Le control-plane ne retourne aucun agent.</p>
                </article>
              ) : null}
              {agentRows.map((agent) => {
                const Icon = agent.icon;
                return (
                  <article key={agent.id} className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="grid h-10 w-10 place-items-center rounded-md bg-slate-100 text-accent">
                        <Icon size={18} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold">{agent.name}</h3>
                        <p className="truncate text-xs text-muted">
                          {agent.scope} / {agent.division}
                        </p>
                      </div>
                      <span
                        className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${
                          agentStatusClass[agent.status] ?? agentStatusClass.seed
                        }`}
                      >
                        {agent.status}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-[1fr_40px] items-center gap-3">
                      <ProgressBar value={agent.load} tone="warn" />
                      <span className="text-right text-xs text-muted">{agent.load}%</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel">
            <SectionHeader eyebrow="Approvals" title="Lifecycle queue" action="Voir approvals" />
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">{approvalModeDetail}</p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[approvalMode]}`}
              >
                {approvalModeLabel}
              </span>
            </div>
            <div className="divide-y divide-border">
              {approvalRows.length === 0 ? (
                <article className="px-4 py-5">
                  <p className="text-sm font-medium text-ink">Aucune demande lifecycle</p>
                  <p className="mt-1 text-xs text-muted">La queue control-plane est vide.</p>
                </article>
              ) : null}
              {approvalRows.map((approval) => {
                const Icon = approval.icon;
                const isPending = approval.status === "requested" && approval.source === "api";
                const isMutatingThisApproval =
                  decisionMutation.isPending &&
                  decisionMutation.variables?.requestId === approval.id;
                return (
                  <article key={approval.id} className="px-4 py-3">
                    <div className="flex items-start gap-3">
                      <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-md ring-1 ${toneSurface[approval.tone]}`}>
                        <Icon size={18} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-semibold">{approval.title}</h3>
                            <p className="mt-0.5 truncate text-xs text-muted">
                              {approval.action} / {approval.division}
                            </p>
                          </div>
                          <span
                            className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${approvalStatusClass[approval.status]}`}
                          >
                            {approval.status}
                          </span>
                        </div>
                        <BalancedText className="mt-2 text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                          {approval.impact}
                        </BalancedText>
                        <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                          <p className="min-w-0 truncate text-xs text-muted">
                            {approval.requester} / {approval.age}
                          </p>
                          <div className="flex items-center gap-2">
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-ok transition enabled:hover:border-ok/40 enabled:hover:bg-ok-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Approve ${approval.title}`}
                              title={`Approve ${approval.title}`}
                              disabled={!isPending || decisionMutation.isPending}
                              onClick={() =>
                                decisionMutation.mutate({
                                  requestId: approval.id,
                                  status: "approved"
                                })
                              }
                            >
                              <Check size={15} />
                            </button>
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-risk transition enabled:hover:border-risk/40 enabled:hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Reject ${approval.title}`}
                              title={`Reject ${approval.title}`}
                              disabled={!isPending || decisionMutation.isPending}
                              onClick={() =>
                                decisionMutation.mutate({
                                  requestId: approval.id,
                                  status: "rejected"
                                })
                              }
                            >
                              <X size={15} />
                            </button>
                          </div>
                        </div>
                        {isMutatingThisApproval ? (
                          <p className="mt-2 text-xs font-medium text-accent">Decision pending...</p>
                        ) : null}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel">
            <SectionHeader eyebrow="Timeline" title="Signaux recents" action="Voir timeline" />
            <div className="divide-y divide-border">
              {timeline.map((event) => {
                const Icon = event.icon;
                return (
                  <article key={`${event.time}-${event.label}`} className="flex gap-3 px-4 py-3">
                    <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-md ring-1 ${toneSurface[event.tone]}`}>
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-sm font-medium">{event.label}</p>
                        <span className="shrink-0 text-xs text-muted">{event.time}</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted">{event.target}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel">
            <SectionHeader eyebrow="Backlog" title="Prochaine tranche" />
            <div className="divide-y divide-border">
              {backlog.map((item) => (
                <article key={`${item.label}-${item.title}`} className="flex items-center gap-3 px-4 py-3">
                  <div
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-md ${
                      item.done ? "bg-ok-soft text-ok" : "bg-slate-100 text-muted"
                    }`}
                  >
                    {item.done ? <Check size={14} /> : <Clock3 size={14} />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-semibold uppercase text-muted">{item.label}</p>
                    <p className="truncate text-sm font-medium">{item.title}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel p-4">
            <p className="text-[11px] font-semibold uppercase tracking-normal text-muted">Garde-fous</p>
            <div className="mt-3 space-y-3">
              {riskControls.map((control) => {
                const Icon = control.icon;
                return (
                  <div key={control.title} className="flex gap-3">
                    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-slate-100 text-ink">
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold">{control.title}</h3>
                      <BalancedText className="mt-1 text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                        {control.detail}
                      </BalancedText>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
