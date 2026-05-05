"use client";

import { prepareWithSegments, layoutWithLines } from "@chenglou/pretext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Ban,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Code2,
  Command,
  Database,
  FileText,
  GitBranch,
  Layers3,
  Menu,
  Network,
  PencilLine,
  Plus,
  Play,
  RadioTower,
  RotateCcw,
  Search,
  Settings2,
  ShieldCheck,
  UserRoundPlus,
  UserRoundX,
  Workflow,
  X
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  decideAgentLifecycleRequest,
  listAgents,
  listAgentLifecycleRequests,
  type AgentDefinition,
  type AgentLifecycleRequest
} from "../lib/control-plane-api";
import {
  decideTaskReview,
  listTaskReviewQueue,
  runReadyTasks,
  submitGoal,
  type GoalEnvelope,
  type GoalPriority,
  type GoalSubmissionResult,
  type TaskRunBatchResult,
  type TaskRecord,
  type TaskReviewAction,
  type TaskReviewDecision
} from "../lib/gateway-api";
import {
  listEvents,
  listProjects,
  type EventRecord,
  type ProjectRecord
} from "../lib/state-service-api";
import {
  agents,
  approvals,
  backlog,
  currentFocus,
  layers,
  overview,
  projects,
  riskControls,
  taskReviews,
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

type TaskReviewViewModel = {
  id: string;
  title: string;
  projectId: string;
  assignedAgentId: string;
  status: string;
  reason: string;
  attempts: string;
  criteria: string[];
  age: string;
  source: "api" | "sample";
};

type TaskReviewDraft = {
  title: string;
  assignedAgentId: string;
  maxAttempts: string;
  acceptanceCriteria: string;
  reason: string;
};

type GoalDraft = {
  goal: string;
  priority: GoalPriority;
  constraints: string;
  requester: string;
};

type RunReadyDraft = {
  projectId: string;
  maxTasks: string;
};

type TimelineViewModel = {
  id: string;
  time: string;
  label: string;
  target: string;
  tone: Tone;
  icon: typeof Activity;
  source: "api" | "sample";
};

const initialGoalDraft: GoalDraft = {
  goal: "",
  priority: "medium",
  constraints: "",
  requester: "local-user"
};

const initialRunReadyDraft: RunReadyDraft = {
  projectId: "",
  maxTasks: "1"
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

function taskReviewReason(task: TaskRecord): string {
  if (task.dead_letter_reason) {
    return task.dead_letter_reason;
  }
  if (task.result && typeof task.result.error === "string") {
    return task.result.error;
  }
  return "Task requires human review before the next transition.";
}

function taskReviewRow(task: TaskRecord): TaskReviewViewModel {
  return {
    id: task.id,
    title: task.title,
    projectId: task.project_id,
    assignedAgentId: task.assigned_agent_id,
    status: task.status,
    reason: taskReviewReason(task),
    attempts: `${task.attempt_count}/${task.max_attempts}`,
    criteria: task.acceptance_criteria,
    age: formatLifecycleAge(task.dead_lettered_at ?? task.created_at),
    source: "api"
  };
}

function taskReviewDraft(row: TaskReviewViewModel): TaskReviewDraft {
  const maxAttempts = row.attempts.split("/").at(1) ?? "";
  return {
    title: row.title,
    assignedAgentId: row.assignedAgentId,
    maxAttempts,
    acceptanceCriteria: row.criteria.join("\n"),
    reason: "Task details updated from Synarch dashboard."
  };
}

function defaultTaskReviewReason(action: TaskReviewAction): string {
  if (action === "retry") {
    return "Retry requested from Synarch dashboard.";
  }
  if (action === "cancel") {
    return "Cancelled from Synarch dashboard.";
  }
  return "Task details updated from Synarch dashboard.";
}

function taskReviewDecisionFromDraft(draft: TaskReviewDraft): TaskReviewDecision {
  const maxAttempts = Number.parseInt(draft.maxAttempts, 10);
  const decision: TaskReviewDecision = {
    action: "update",
    reason: draft.reason.trim() || defaultTaskReviewReason("update")
  };
  const title = draft.title.trim();
  const assignedAgentId = draft.assignedAgentId.trim();
  const acceptanceCriteria = draft.acceptanceCriteria
    .split(/\r?\n/)
    .map((criterion) => criterion.trim())
    .filter(Boolean);

  if (title) {
    decision.title = title;
  }
  if (assignedAgentId) {
    decision.assigned_agent_id = assignedAgentId;
  }
  if (acceptanceCriteria.length > 0) {
    decision.acceptance_criteria = acceptanceCriteria;
  }
  if (Number.isFinite(maxAttempts)) {
    decision.max_attempts = maxAttempts;
  }

  return decision;
}

function constraintsFromDraft(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((constraint) => constraint.trim())
    .filter(Boolean);
}

function goalEnvelopeFromDraft(draft: GoalDraft): GoalEnvelope {
  return {
    goal: draft.goal.trim(),
    priority: draft.priority,
    requester: draft.requester.trim() || "local-user",
    constraints: constraintsFromDraft(draft.constraints),
    context: {}
  };
}

function runCost(batch: TaskRunBatchResult): number {
  return batch.runs.reduce(
    (total, run) =>
      total +
      (run.cost_records ?? []).reduce(
        (runTotal, costRecord) => runTotal + (costRecord.total_cost ?? 0),
        0
      ),
    0
  );
}

function eventTone(event: EventRecord): Tone {
  if (event.type.includes("failed")) {
    return "risk";
  }
  if (event.type.includes("blocked") || event.type.includes("requested")) {
    return "warn";
  }
  if (event.type.includes("completed") || event.type.includes("created")) {
    return "ok";
  }
  if (event.type.includes("approval")) {
    return "accent";
  }
  return "info";
}

function eventIcon(event: EventRecord): typeof Activity {
  if (event.type.startsWith("approval")) {
    return ShieldCheck;
  }
  if (event.type.startsWith("project") || event.type.startsWith("task")) {
    return Workflow;
  }
  if (event.type.startsWith("cost") || event.type.startsWith("model_call")) {
    return RadioTower;
  }
  if (event.type.includes("failed") || event.type.includes("blocked")) {
    return AlertTriangle;
  }
  if (event.type.startsWith("agent")) {
    return UserRoundPlus;
  }
  return Database;
}

function eventRow(event: EventRecord): TimelineViewModel {
  return {
    id: event.id,
    time: formatLifecycleAge(event.timestamp),
    label: event.type,
    target: event.target ?? event.source_agent_id ?? event.trace_id ?? "system",
    tone: eventTone(event),
    icon: eventIcon(event),
    source: "api"
  };
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [isGoalFormOpen, setIsGoalFormOpen] = useState(false);
  const [goalDraft, setGoalDraft] = useState<GoalDraft>(initialGoalDraft);
  const [lastGoalSubmission, setLastGoalSubmission] =
    useState<GoalSubmissionResult | null>(null);
  const [runReadyDraft, setRunReadyDraft] = useState<RunReadyDraft>(initialRunReadyDraft);
  const [lastRunBatch, setLastRunBatch] = useState<TaskRunBatchResult | null>(null);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [taskReviewDrafts, setTaskReviewDrafts] = useState<Record<string, TaskReviewDraft>>({});
  const eventsQuery = useQuery({
    queryKey: ["events"],
    queryFn: listEvents,
    refetchInterval: 15_000
  });
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
  const taskReviewsQuery = useQuery({
    queryKey: ["task-review-queue"],
    queryFn: listTaskReviewQueue,
    refetchInterval: 15_000
  });
  const goalMutation = useMutation({
    mutationFn: submitGoal,
    onSuccess: (result) => {
      setLastGoalSubmission(result);
      setIsGoalFormOpen(false);
      setGoalDraft(initialGoalDraft);
      setRunReadyDraft({
        projectId: result.project.id,
        maxTasks: "1"
      });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
    }
  });
  const runReadyMutation = useMutation({
    mutationFn: runReadyTasks,
    onSuccess: (result) => {
      setLastRunBatch(result);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
    }
  });
  const decisionMutation = useMutation({
    mutationFn: decideAgentLifecycleRequest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
    }
  });
  const taskReviewMutation = useMutation({
    mutationFn: decideTaskReview,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      setEditingTaskId(null);
      setTaskReviewDrafts({});
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
      return [...projectsQuery.data]
        .sort(
          (left, right) =>
            new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
        )
        .map(projectRow)
        .slice(0, 8);
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
      ? `${projectRows.length}/${projectsQuery.data?.length ?? projectRows.length} recent projects from state-service`
      : projectMode === "syncing"
        ? "Connecting to state-service"
        : "State-service unavailable, showing roadmap projects";
  const taskReviewRows = useMemo<TaskReviewViewModel[]>(() => {
    if (taskReviewsQuery.isSuccess) {
      return taskReviewsQuery.data.map(taskReviewRow);
    }

    return taskReviews.map((taskReview) => ({
      ...taskReview,
      source: "sample" as const
    }));
  }, [taskReviewsQuery.data, taskReviewsQuery.isSuccess]);
  const taskReviewMode = taskReviewsQuery.isLoading
    ? "syncing"
    : taskReviewsQuery.isError
      ? "sample"
      : "live";
  const taskReviewModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "Sample fallback"
  }[taskReviewMode];
  const taskReviewModeDetail =
    taskReviewMode === "live"
      ? `${taskReviewRows.length} tasks from gateway review queue`
      : taskReviewMode === "syncing"
        ? "Connecting to gateway"
        : "Gateway unavailable, showing sample review queue";
  const timelineRows = useMemo<TimelineViewModel[]>(() => {
    if (eventsQuery.isSuccess) {
      return [...eventsQuery.data]
        .sort(
          (left, right) =>
            new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()
        )
        .map(eventRow)
        .slice(0, 8);
    }

    return timeline.map((event) => ({
      ...event,
      id: `${event.time}-${event.label}`,
      source: "sample" as const
    }));
  }, [eventsQuery.data, eventsQuery.isSuccess]);
  const timelineMode = eventsQuery.isLoading
    ? "syncing"
    : eventsQuery.isError
      ? "sample"
      : "live";
  const timelineModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "Sample fallback"
  }[timelineMode];
  const timelineModeDetail =
    timelineMode === "live"
      ? `${timelineRows.length} events from state-service`
      : timelineMode === "syncing"
        ? "Connecting to state-service"
        : "State-service unavailable, showing sample timeline";
  const canSubmitGoal = goalDraft.goal.trim().length > 0 && !goalMutation.isPending;
  const updateGoalDraft = <FieldT extends keyof GoalDraft>(
    field: FieldT,
    value: GoalDraft[FieldT]
  ) => {
    setGoalDraft((draft) => ({
      ...draft,
      [field]: value
    }));
  };
  const handleGoalSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmitGoal) {
      return;
    }
    goalMutation.mutate(goalEnvelopeFromDraft(goalDraft));
  };
  const maxReadyTasks = Number.parseInt(runReadyDraft.maxTasks, 10);
  const canRunReadyTasks =
    runReadyDraft.projectId.trim().length > 0 &&
    Number.isFinite(maxReadyTasks) &&
    maxReadyTasks >= 1 &&
    !runReadyMutation.isPending;
  const updateRunReadyDraft = (field: keyof RunReadyDraft, value: string) => {
    setRunReadyDraft((draft) => ({
      ...draft,
      [field]: value
    }));
  };
  const handleRunReadySubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canRunReadyTasks) {
      return;
    }
    runReadyMutation.mutate({
      projectId: runReadyDraft.projectId.trim(),
      maxTasks: maxReadyTasks
    });
  };
  const updateTaskReviewDraft = (
    taskId: string,
    field: keyof TaskReviewDraft,
    value: string
  ) => {
    setTaskReviewDrafts((drafts) => ({
      ...drafts,
      [taskId]: {
        ...(drafts[taskId] ??
          taskReviewDraft(
            taskReviewRows.find((row) => row.id === taskId) ?? {
              id: taskId,
              title: "",
              projectId: "",
              assignedAgentId: "",
              status: "needs_review",
              reason: "",
              attempts: "",
              criteria: [],
              age: "now",
              source: "sample"
            }
          )),
        [field]: value
      }
    }));
  };
  const beginTaskReviewEdit = (row: TaskReviewViewModel) => {
    setTaskReviewDrafts((drafts) => ({
      ...drafts,
      [row.id]: drafts[row.id] ?? taskReviewDraft(row)
    }));
    setEditingTaskId((currentTaskId) => (currentTaskId === row.id ? null : row.id));
  };
  const applyTaskReviewAction = (row: TaskReviewViewModel, action: TaskReviewAction) => {
    const decision =
      action === "update"
        ? taskReviewDecisionFromDraft(taskReviewDrafts[row.id] ?? taskReviewDraft(row))
        : {
            action,
            reason: defaultTaskReviewReason(action)
          };
    taskReviewMutation.mutate({
      taskId: row.id,
      decision
    });
  };

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
              onClick={() => setIsGoalFormOpen(true)}
            >
              <Plus size={18} />
              <span className="hidden sm:inline">Objectif</span>
            </button>
          </div>
        </div>
      </header>

      {isGoalFormOpen ? (
        <div className="fixed inset-0 z-40 overflow-y-auto bg-ink/35 px-4 py-6 backdrop-blur-sm">
          <form
            className="mx-auto max-w-xl overflow-hidden rounded-md border border-border bg-panel shadow-soft"
            onSubmit={handleGoalSubmit}
          >
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-normal text-muted">
                  Gateway
                </p>
                <h2 className="truncate text-sm font-semibold text-ink">Nouvel objectif</h2>
              </div>
              <button
                className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border bg-white text-muted transition hover:border-accent/40 hover:text-accent"
                aria-label="Fermer le formulaire objectif"
                title="Fermer le formulaire objectif"
                type="button"
                onClick={() => setIsGoalFormOpen(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3 p-4">
              <textarea
                className="min-h-28 w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                aria-label="Objectif"
                name="goal"
                placeholder="Objectif"
                value={goalDraft.goal}
                onChange={(event) => updateGoalDraft("goal", event.target.value)}
              />
              <div className="grid gap-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                <select
                  className="h-10 w-full rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                  aria-label="Priorite"
                  name="priority"
                  value={goalDraft.priority}
                  onChange={(event) =>
                    updateGoalDraft("priority", event.target.value as GoalPriority)
                  }
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
                <input
                  className="h-10 w-full rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                  aria-label="Requester"
                  name="requester"
                  placeholder="Requester"
                  value={goalDraft.requester}
                  onChange={(event) => updateGoalDraft("requester", event.target.value)}
                />
              </div>
              <textarea
                className="min-h-20 w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                aria-label="Contraintes"
                name="constraints"
                placeholder="Contraintes"
                value={goalDraft.constraints}
                onChange={(event) => updateGoalDraft("constraints", event.target.value)}
              />
              {goalMutation.isError ? (
                <p className="text-xs font-medium text-risk">
                  {goalMutation.error instanceof Error
                    ? goalMutation.error.message
                    : "Goal submission failed."}
                </p>
              ) : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
              <button
                className="h-9 rounded-md border border-border bg-white px-3 text-sm font-medium text-muted transition hover:border-accent/40 hover:text-accent"
                type="button"
                onClick={() => setIsGoalFormOpen(false)}
              >
                Annuler
              </button>
              <button
                className="flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-white transition enabled:hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!canSubmitGoal}
                type="submit"
              >
                <Plus size={16} />
                <span>{goalMutation.isPending ? "Creation..." : "Creer"}</span>
              </button>
            </div>
          </form>
        </div>
      ) : null}

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
                {lastGoalSubmission ? (
                  <p className="mt-3 truncate text-xs font-medium text-ok">
                    {lastGoalSubmission.project.title} / {lastGoalSubmission.tasks.length} tasks /{" "}
                    {lastGoalSubmission.trace_id}
                  </p>
                ) : null}
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
            <SectionHeader eyebrow="Runner" title="Exécuter une tranche prête" />
            <form
              className="grid gap-3 border-b border-border px-4 py-3 md:grid-cols-[minmax(0,1fr)_112px_auto]"
              onSubmit={handleRunReadySubmit}
            >
              <input
                className="h-10 min-w-0 rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                aria-label="Project id"
                name="project_id"
                placeholder="project_id"
                value={runReadyDraft.projectId}
                onChange={(event) => updateRunReadyDraft("projectId", event.target.value)}
              />
              <select
                className="h-10 rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                aria-label="Max tasks"
                name="max_tasks"
                value={runReadyDraft.maxTasks}
                onChange={(event) => updateRunReadyDraft("maxTasks", event.target.value)}
              >
                <option value="1">1 task</option>
                <option value="2">2 tasks</option>
                <option value="3">3 tasks</option>
              </select>
              <button
                className="flex h-10 items-center justify-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white transition enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!canRunReadyTasks}
                type="submit"
              >
                <Play size={16} />
                <span>{runReadyMutation.isPending ? "Running..." : "Run"}</span>
              </button>
            </form>
            <div className="px-4 py-3">
              {lastRunBatch ? (
                <div className="grid gap-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info ring-1 ring-info/15">
                      {lastRunBatch.stop_reason}
                    </span>
                    <span className="text-xs text-muted">
                      {lastRunBatch.runs.length}/{lastRunBatch.max_tasks} runs /{" "}
                      {lastRunBatch.trace_id}
                    </span>
                  </div>
                  {lastRunBatch.runs.map((run) => (
                    <div key={run.task.id} className="grid gap-1 rounded-md bg-slate-50 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate text-sm font-semibold text-ink">
                          {run.task.title}
                        </p>
                        <span className={`shrink-0 text-xs font-medium ${projectStatusClass[run.task.status]}`}>
                          {run.task.status}
                        </span>
                      </div>
                      <BalancedText className="text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                        {run.agent_result.summary}
                      </BalancedText>
                    </div>
                  ))}
                  <p className="text-xs text-muted">
                    cost {runCost(lastRunBatch).toFixed(6)} USD / skipped{" "}
                    {lastRunBatch.skipped_task_ids.length}
                  </p>
                </div>
              ) : (
                <p className="text-xs text-muted">
                  Le lancement exige un project_id pour éviter toute exécution globale.
                </p>
              )}
              {runReadyMutation.isError ? (
                <p className="mt-2 text-xs font-medium text-risk">
                  {runReadyMutation.error instanceof Error
                    ? runReadyMutation.error.message
                    : "Task execution failed."}
                </p>
              ) : null}
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
            <SectionHeader eyebrow="Tasks" title="Review queue" action="Voir tasks" />
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">{taskReviewModeDetail}</p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[taskReviewMode]}`}
              >
                {taskReviewModeLabel}
              </span>
            </div>
            <div className="divide-y divide-border">
              {taskReviewRows.length === 0 ? (
                <article className="px-4 py-5">
                  <p className="text-sm font-medium text-ink">Aucune tâche en revue</p>
                  <p className="mt-1 text-xs text-muted">Le gateway ne retourne aucune tâche needs_review.</p>
                </article>
              ) : null}
              {taskReviewRows.map((taskReview) => {
                const isApiRow = taskReview.source === "api";
                const isEditing = editingTaskId === taskReview.id;
                const isMutatingThisTask =
                  taskReviewMutation.isPending &&
                  taskReviewMutation.variables?.taskId === taskReview.id;
                const draft = taskReviewDrafts[taskReview.id] ?? taskReviewDraft(taskReview);
                return (
                  <article key={taskReview.id} className="px-4 py-3">
                    <div className="flex items-start gap-3">
                      <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-md ring-1 ${toneSurface.warn}`}>
                        <AlertTriangle size={18} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-semibold">{taskReview.title}</h3>
                            <p className="mt-0.5 truncate text-xs text-muted">
                              {taskReview.projectId} / {taskReview.assignedAgentId}
                            </p>
                          </div>
                          <span
                            className="shrink-0 rounded-md bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn ring-1 ring-warn/15"
                          >
                            {taskReview.status}
                          </span>
                        </div>
                        <BalancedText className="mt-2 text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                          {taskReview.reason}
                        </BalancedText>
                        <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                          <p className="min-w-0 truncate text-xs text-muted">
                            attempts {taskReview.attempts} / {taskReview.age}
                          </p>
                          <div className="flex items-center gap-2">
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-accent transition enabled:hover:border-accent/40 enabled:hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Retry ${taskReview.title}`}
                              title={`Retry ${taskReview.title}`}
                              disabled={!isApiRow || taskReviewMutation.isPending}
                              onClick={() => applyTaskReviewAction(taskReview, "retry")}
                            >
                              <RotateCcw size={15} />
                            </button>
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-info transition enabled:hover:border-info/40 enabled:hover:bg-info-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Update ${taskReview.title}`}
                              title={`Update ${taskReview.title}`}
                              disabled={!isApiRow || taskReviewMutation.isPending}
                              onClick={() => beginTaskReviewEdit(taskReview)}
                            >
                              <PencilLine size={15} />
                            </button>
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-risk transition enabled:hover:border-risk/40 enabled:hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Cancel ${taskReview.title}`}
                              title={`Cancel ${taskReview.title}`}
                              disabled={!isApiRow || taskReviewMutation.isPending}
                              onClick={() => applyTaskReviewAction(taskReview, "cancel")}
                            >
                              <Ban size={15} />
                            </button>
                          </div>
                        </div>
                        {isEditing ? (
                          <div className="mt-3 space-y-2 border-t border-border pt-3">
                            <input
                              className="h-9 w-full rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                              aria-label={`Task title for ${taskReview.title}`}
                              value={draft.title}
                              onChange={(event) =>
                                updateTaskReviewDraft(taskReview.id, "title", event.target.value)
                              }
                            />
                            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_92px]">
                              <input
                                className="h-9 w-full rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                                aria-label={`Assigned agent for ${taskReview.title}`}
                                value={draft.assignedAgentId}
                                onChange={(event) =>
                                  updateTaskReviewDraft(
                                    taskReview.id,
                                    "assignedAgentId",
                                    event.target.value
                                  )
                                }
                              />
                              <input
                                className="h-9 w-full rounded-md border border-border bg-white px-3 text-sm text-ink outline-none transition focus:border-accent"
                                aria-label={`Max attempts for ${taskReview.title}`}
                                inputMode="numeric"
                                value={draft.maxAttempts}
                                onChange={(event) =>
                                  updateTaskReviewDraft(taskReview.id, "maxAttempts", event.target.value)
                                }
                              />
                            </div>
                            <textarea
                              className="min-h-20 w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                              aria-label={`Acceptance criteria for ${taskReview.title}`}
                              value={draft.acceptanceCriteria}
                              onChange={(event) =>
                                updateTaskReviewDraft(
                                  taskReview.id,
                                  "acceptanceCriteria",
                                  event.target.value
                                )
                              }
                            />
                            <textarea
                              className="min-h-16 w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                              aria-label={`Review reason for ${taskReview.title}`}
                              value={draft.reason}
                              onChange={(event) =>
                                updateTaskReviewDraft(taskReview.id, "reason", event.target.value)
                              }
                            />
                            <div className="flex items-center justify-end gap-2">
                              <button
                                className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-muted transition hover:border-accent/40 hover:text-accent"
                                aria-label={`Close update form for ${taskReview.title}`}
                                title={`Close update form for ${taskReview.title}`}
                                onClick={() => setEditingTaskId(null)}
                              >
                                <X size={15} />
                              </button>
                              <button
                                className="grid h-8 w-8 place-items-center rounded-md bg-accent text-white transition enabled:hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-40"
                                aria-label={`Apply update for ${taskReview.title}`}
                                title={`Apply update for ${taskReview.title}`}
                                disabled={taskReviewMutation.isPending}
                                onClick={() => applyTaskReviewAction(taskReview, "update")}
                              >
                                <Check size={15} />
                              </button>
                            </div>
                          </div>
                        ) : null}
                        {isMutatingThisTask ? (
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
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">{timelineModeDetail}</p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[timelineMode]}`}
              >
                {timelineModeLabel}
              </span>
            </div>
            <div className="divide-y divide-border">
              {timelineRows.length === 0 ? (
                <article className="px-4 py-5">
                  <p className="text-sm font-medium text-ink">Aucun event disponible</p>
                  <p className="mt-1 text-xs text-muted">Le state-service ne retourne aucun event.</p>
                </article>
              ) : null}
              {timelineRows.map((event) => {
                const Icon = event.icon;
                return (
                  <article key={event.id} className="flex gap-3 px-4 py-3">
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
