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
  KeyRound,
  Layers3,
  Menu,
  Network,
  PencilLine,
  PlugZap,
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
  getAgentWorldView,
  listAgents,
  listAgentLifecycleRequests,
  type AgentDefinition,
  type AgentLifecycleRequest,
  type LocalWorldView
} from "../lib/control-plane-api";
import {
  applyCredentialAccessGrant,
  callTool,
  decideCredentialAccessRequest,
  decideTaskReview,
  getProjectTimeline,
  listCredentialAccessRequests,
  listTaskReviewQueue,
  resumeConnectorJob,
  runReadyTasks,
  runConnectorJobNow,
  runTask,
  submitGoal,
  stopConnectorJob,
  updateMemoryStatus,
  type ConnectorJobAction,
  type ConnectorJobActionResult,
  type GoalEnvelope,
  type GoalPriority,
  type GoalSubmissionResult,
  type CredentialAccessRequest,
  type MemoryStatus,
  type ProjectTimeline,
  type TaskRunBatchResult,
  type TaskRunResult,
  type TaskRecord,
  type TaskReviewAction,
  type TaskReviewDecision,
  type ToolCallRequest,
  type ToolResult
} from "../lib/gateway-api";
import {
  listConnectorJobRuns,
  listConnectorJobs,
  listEvents,
  listProjects,
  type ConnectorJobRecord,
  type ConnectorJobRunRecord,
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

const memoryStatusClass: Record<MemoryStatus, string> = {
  proposed: "bg-warn-soft text-warn ring-warn/15",
  approved: "bg-ok-soft text-ok ring-ok/15",
  rejected: "bg-risk-soft text-risk ring-risk/15"
};

const connectorJobStatusClass: Record<string, string> = {
  active: "bg-ok-soft text-ok ring-ok/15",
  stopped: "bg-slate-100 text-muted ring-border"
};

const connectorJobRunStatusClass: Record<string, string> = {
  completed: "bg-ok-soft text-ok ring-ok/15",
  failed: "bg-risk-soft text-risk ring-risk/15",
  skipped: "bg-warn-soft text-warn ring-warn/15"
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
  source: "api" | "credential" | "sample";
  candidateServiceIds?: string[];
};

type AgentViewModel = {
  id: string;
  name: string;
  status: string;
  load: number;
  scope: string;
  division: string;
  allowedTools: string[];
  deniedTools: string[];
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

type ToolCallDraft = {
  agentId: string;
  toolName: string;
  serviceId: string;
  projectId: string;
  reason: string;
  summary: string;
  url: string;
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

type TraceViewModel = {
  id: string;
  label: string;
  eventCount: number;
  costCount: number;
  totalCost: number;
  lastTimestamp: number;
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

const initialToolCallDraft: ToolCallDraft = {
  agentId: "",
  toolName: "event.emit",
  serviceId: "service-event-log",
  projectId: "",
  reason: "Record a controlled tool-gate smoke event from the Synarch dashboard.",
  summary: "Permission gate smoke event from Synarch dashboard.",
  url: "https://example.com"
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

function credentialApprovalRow(request: CredentialAccessRequest): ApprovalViewModel {
  const scopes =
    request.requested_scopes.length > 0
      ? request.requested_scopes.join(", ")
      : "tool/service mapping";
  return {
    id: request.id,
    title: `${request.tool_name} access`,
    action: "credential_access",
    requester: request.requested_by_id,
    division: request.agent_id,
    status: request.status,
    age: formatLifecycleAge(request.created_at),
    tone: "warn",
    icon: KeyRound,
    impact: `${request.reason} / ${scopes}`,
    source: "credential",
    candidateServiceIds: request.candidate_service_ids
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
    allowedTools: agent.permissions.allowed_tools,
    deniedTools: agent.permissions.denied_tools,
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

function toolCallFromDraft(
  draft: ToolCallDraft,
  options: {
    agentId: string;
    projectId: string;
  }
): ToolCallRequest {
  const toolName = draft.toolName.trim();
  const { agentId, projectId } = options;
  const targetProjectId = projectId.trim();
  let argumentsPayload: Record<string, unknown> = {};
  if (toolName === "event.emit") {
    argumentsPayload = {
      type: "agent.reported",
      target: targetProjectId || undefined,
      payload: {
        summary: draft.summary.trim(),
        source: "frontend.permission_gate"
      }
    };
  }
  if (toolName === "web.fetch") {
    argumentsPayload = {
      url: draft.url.trim(),
      max_bytes: 12000
    };
  }

  return {
    agent_id: agentId,
    tool_name: toolName,
    service_id: draft.serviceId.trim() || null,
    project_id: targetProjectId || null,
    reason: draft.reason.trim(),
    arguments: argumentsPayload
  };
}

function preferredServiceForTool(toolName: string, serviceIds: string[]): string | null {
  if (toolName === "web.fetch" || toolName === "web.search") {
    return (
      serviceIds.find(
        (serviceId) => serviceId.includes("supplier-web") || serviceId.includes("web-fetch")
      ) ?? null
    );
  }
  if (toolName === "event.emit") {
    return serviceIds.find((serviceId) => serviceId.includes("event-log")) ?? null;
  }
  return null;
}

function serviceMatchesTool(toolName: string, serviceId: string): boolean {
  if (toolName === "web.fetch" || toolName === "web.search") {
    return serviceId.includes("supplier-web") || serviceId.includes("web-fetch");
  }
  if (toolName === "event.emit") {
    return serviceId.includes("event-log");
  }
  return true;
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

function taskCost(timeline: ProjectTimeline, taskId: string): number {
  return timeline.cost_records
    .filter((costRecord) => costRecord.task_id === taskId)
    .reduce((total, costRecord) => total + costRecord.total_cost, 0);
}

function eventBelongsToTask(event: EventRecord, taskId: string): boolean {
  return event.target === taskId || event.payload.task_id === taskId;
}

function traceIdForEvent(event: EventRecord): string {
  return event.trace_id ?? "no-trace";
}

function traceIdForCost(costRecord: { trace_id?: string | null }): string {
  return costRecord.trace_id ?? "no-trace";
}

function traceLabel(traceId: string): string {
  return traceId === "no-trace" ? "no trace" : traceId;
}

function formatRelativeTimestamp(value?: string | null): string {
  if (!value) {
    return "none";
  }

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "unknown";
  }

  const deltaMs = timestamp - Date.now();
  const absMinutes = Math.round(Math.abs(deltaMs) / 60_000);
  if (absMinutes < 1) {
    return deltaMs >= 0 ? "in <1 min" : "<1 min ago";
  }
  if (absMinutes < 60) {
    return deltaMs >= 0 ? `in ${absMinutes} min` : `${absMinutes} min ago`;
  }

  const hours = Math.round(absMinutes / 60);
  if (hours < 24) {
    return deltaMs >= 0 ? `in ${hours} h` : `${hours} h ago`;
  }

  const days = Math.round(hours / 24);
  return deltaMs >= 0 ? `in ${days} d` : `${days} d ago`;
}

function metadataNumber(metadata: Record<string, unknown>, key: string): number | null {
  const value = metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function connectorJobPolicyLabels(job: ConnectorJobRecord): string[] {
  const labels: string[] = [];
  const maxRuns = metadataNumber(job.metadata, "max_runs");
  const maxFailures = metadataNumber(job.metadata, "max_failures");
  const cooldown = metadataNumber(job.metadata, "cooldown_seconds");
  const failureCooldown = metadataNumber(job.metadata, "failure_cooldown_seconds");

  if (maxRuns !== null) {
    labels.push(`max_runs ${maxRuns}`);
  }
  if (maxFailures !== null) {
    labels.push(`max_failures ${maxFailures}`);
  }
  if (cooldown !== null) {
    labels.push(`cooldown ${cooldown}s`);
  }
  if (failureCooldown !== null) {
    labels.push(`failure cooldown ${failureCooldown}s`);
  }

  return labels;
}

function connectorJobStopDetail(
  job: ConnectorJobRecord,
  lastRun?: ConnectorJobRunRecord
): string | null {
  const stopReason = lastRun?.output.stop_reason ?? lastRun?.output.reason;
  if (typeof stopReason === "string" && stopReason.trim().length > 0) {
    return stopReason;
  }
  if (job.status !== "stopped") {
    return null;
  }

  const maxFailures = metadataNumber(job.metadata, "max_failures");
  if (maxFailures !== null && lastRun?.status === "failed") {
    return `max_failures=${maxFailures}`;
  }

  const maxRuns = metadataNumber(job.metadata, "max_runs");
  if (maxRuns !== null) {
    return `max_runs=${maxRuns}`;
  }

  return job.stopped_at ? `stopped ${formatRelativeTimestamp(job.stopped_at)}` : "stopped";
}

function formatPayload(payload: unknown): string {
  return JSON.stringify(payload, null, 2);
}

function memoryCountByStatus(timeline: ProjectTimeline, status: MemoryStatus): number {
  return timeline.memory_items.filter((item) => item.status === status).length;
}

function taskEventCount(timeline: ProjectTimeline, taskId: string): number {
  return timeline.events.filter((event) => eventBelongsToTask(event, taskId)).length;
}

function taskResultSummary(task: TaskRecord): string {
  if (task.result && typeof task.result.summary === "string") {
    return task.result.summary;
  }
  if (task.result && typeof task.result.error === "string") {
    return task.result.error;
  }
  return task.description;
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
  const [lastTaskRun, setLastTaskRun] = useState<TaskRunResult | null>(null);
  const [toolCallDraft, setToolCallDraft] = useState<ToolCallDraft>(initialToolCallDraft);
  const [lastToolResult, setLastToolResult] = useState<ToolResult | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [focusedTimelineTaskId, setFocusedTimelineTaskId] = useState("");
  const [selectedTimelineTraceId, setSelectedTimelineTraceId] = useState("");
  const [selectedTimelineEventId, setSelectedTimelineEventId] = useState("");
  const [selectedMemoryItemId, setSelectedMemoryItemId] = useState("");
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
  const credentialAccessQuery = useQuery({
    queryKey: ["credential-access-requests"],
    queryFn: listCredentialAccessRequests,
    refetchInterval: 15_000
  });
  const taskReviewsQuery = useQuery({
    queryKey: ["task-review-queue"],
    queryFn: listTaskReviewQueue,
    refetchInterval: 15_000
  });
  const connectorJobsQuery = useQuery({
    queryKey: ["connector-jobs"],
    queryFn: listConnectorJobs,
    refetchInterval: 10_000
  });
  const connectorJobRunsQuery = useQuery({
    queryKey: ["connector-job-runs"],
    queryFn: listConnectorJobRuns,
    refetchInterval: 10_000
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
      setSelectedProjectId(result.project.id);
      setFocusedTimelineTaskId("");
      setSelectedTimelineTraceId(result.trace_id);
      setSelectedTimelineEventId("");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["credential-access-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const runReadyMutation = useMutation({
    mutationFn: runReadyTasks,
    onSuccess: (result) => {
      setLastRunBatch(result);
      if (result.project_id) {
        setSelectedProjectId(result.project_id);
      }
      setFocusedTimelineTaskId(result.runs[0]?.task.id ?? "");
      setSelectedTimelineTraceId(result.trace_id);
      setSelectedTimelineEventId("");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const taskRunMutation = useMutation({
    mutationFn: runTask,
    onSuccess: (result) => {
      setLastTaskRun(result);
      setSelectedProjectId(result.task.project_id);
      setFocusedTimelineTaskId(result.task.id);
      setSelectedTimelineTraceId(result.trace_id);
      setSelectedTimelineEventId("");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const memoryStatusMutation = useMutation({
    mutationFn: updateMemoryStatus,
    onSuccess: (memoryItem) => {
      setSelectedMemoryItemId(memoryItem.id);
      setSelectedTimelineTraceId("");
      setSelectedTimelineEventId("");
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const decisionMutation = useMutation({
    mutationFn: decideAgentLifecycleRequest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
    }
  });
  const credentialDecisionMutation = useMutation({
    mutationFn: decideCredentialAccessRequest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["credential-access-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const credentialGrantMutation = useMutation({
    mutationFn: applyCredentialAccessGrant,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["credential-access-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const taskReviewMutation = useMutation({
    mutationFn: decideTaskReview,
    onSuccess: (_result, variables) => {
      setFocusedTimelineTaskId(variables.taskId);
      setSelectedTimelineEventId("");
      void queryClient.invalidateQueries({ queryKey: ["task-review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
      setEditingTaskId(null);
      setTaskReviewDrafts({});
    }
  });
  const toolCallMutation = useMutation({
    mutationFn: callTool,
    onSuccess: (result) => {
      setLastToolResult(result);
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const connectorJobActionMutation = useMutation<
    ConnectorJobActionResult,
    Error,
    { jobId: string; action: ConnectorJobAction }
  >({
    mutationFn: ({ jobId, action }: { jobId: string; action: ConnectorJobAction }) => {
      if (action === "run") {
        return runConnectorJobNow({ jobId });
      }
      if (action === "stop") {
        return stopConnectorJob({ jobId });
      }
      return resumeConnectorJob({ jobId });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connector-jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["connector-job-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
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
    if (lifecycleQuery.isSuccess || credentialAccessQuery.isSuccess) {
      return [
        ...(lifecycleQuery.data ?? []).map(lifecycleApprovalRow),
        ...(credentialAccessQuery.data ?? []).map(credentialApprovalRow)
      ];
    }

    return approvals.map((approval) => ({
      ...approval,
      source: "sample" as const
    }));
  }, [
    credentialAccessQuery.data,
    credentialAccessQuery.isSuccess,
    lifecycleQuery.data,
    lifecycleQuery.isSuccess
  ]);
  const approvalMode = lifecycleQuery.isLoading || credentialAccessQuery.isLoading
    ? "syncing"
    : lifecycleQuery.isError && credentialAccessQuery.isError
      ? "sample"
      : "live";
  const approvalModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "Sample fallback"
  }[approvalMode];
  const approvalModeDetail =
    approvalMode === "live"
      ? `${approvalRows.length} approval records from control-plane/gateway`
      : approvalMode === "syncing"
        ? "Connecting to control-plane/gateway"
        : "Control-plane and gateway unavailable, showing sample records";
  const agentRows = useMemo<AgentViewModel[]>(() => {
    if (agentsQuery.isSuccess) {
      return agentsQuery.data.map(agentRow);
    }

    return agents.map((agent) => ({
      ...agent,
      allowedTools: [],
      deniedTools: [],
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
  const liveAgentRows = agentRows.filter((agent) => agent.source === "api");
  const effectiveToolAgentId =
    toolCallDraft.agentId && liveAgentRows.some((agent) => agent.id === toolCallDraft.agentId)
      ? toolCallDraft.agentId
      : (liveAgentRows[0]?.id ?? "");
  const selectedToolAgent = liveAgentRows.find((agent) => agent.id === effectiveToolAgentId);
  const worldViewQuery = useQuery<LocalWorldView>({
    queryKey: ["agent-world-view", effectiveToolAgentId],
    queryFn: () => getAgentWorldView(effectiveToolAgentId),
    enabled: effectiveToolAgentId.length > 0,
    refetchInterval: 30_000
  });
  const worldViewMode = !effectiveToolAgentId
    ? "sample"
    : worldViewQuery.isLoading
      ? "syncing"
      : worldViewQuery.isError
        ? "sample"
        : "live";
  const worldViewModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "No world-view"
  }[worldViewMode];
  const availableToolOptions =
    worldViewQuery.data?.permissions.allowed_tools ?? selectedToolAgent?.allowedTools ?? [];
  const availableServiceOptions = worldViewQuery.data?.available_services ?? [];
  const availableConnectorOptions = worldViewQuery.data?.available_connector_ids ?? [];
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
  const liveProjectRows = projectRows.filter((project) => project.source === "api");
  const effectiveSelectedProjectId =
    selectedProjectId && liveProjectRows.some((project) => project.id === selectedProjectId)
      ? selectedProjectId
      : (liveProjectRows[0]?.id ?? "");
  const selectedProjectRow = projectRows.find(
    (project) => project.id === effectiveSelectedProjectId
  );
  const projectTimelineQuery = useQuery({
    queryKey: ["project-timeline", effectiveSelectedProjectId],
    queryFn: () => getProjectTimeline(effectiveSelectedProjectId),
    enabled: effectiveSelectedProjectId.length > 0,
    refetchInterval: 10_000
  });
  const projectTimelineTasks = useMemo(() => {
    if (!projectTimelineQuery.isSuccess) {
      return [];
    }
    return [...projectTimelineQuery.data.tasks].sort((left, right) => {
      if (left.sequence !== right.sequence) {
        return left.sequence - right.sequence;
      }
      return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
    });
  }, [projectTimelineQuery.data, projectTimelineQuery.isSuccess]);
  const effectiveFocusedTaskId = projectTimelineTasks.some(
    (task) => task.id === focusedTimelineTaskId
  )
    ? focusedTimelineTaskId
    : "";
  const focusedTimelineTask = projectTimelineTasks.find(
    (task) => task.id === effectiveFocusedTaskId
  );
  const projectTimelineTraceRows = useMemo<TraceViewModel[]>(() => {
    if (!projectTimelineQuery.isSuccess) {
      return [];
    }
    const traces = new Map<string, TraceViewModel>();
    for (const event of projectTimelineQuery.data.events) {
      const traceId = traceIdForEvent(event);
      const row =
        traces.get(traceId) ??
        {
          id: traceId,
          label: traceLabel(traceId),
          eventCount: 0,
          costCount: 0,
          totalCost: 0,
          lastTimestamp: 0
        };
      row.eventCount += 1;
      row.lastTimestamp = Math.max(row.lastTimestamp, new Date(event.timestamp).getTime());
      traces.set(traceId, row);
    }
    for (const costRecord of projectTimelineQuery.data.cost_records) {
      const traceId = traceIdForCost(costRecord);
      const row =
        traces.get(traceId) ??
        {
          id: traceId,
          label: traceLabel(traceId),
          eventCount: 0,
          costCount: 0,
          totalCost: 0,
          lastTimestamp: 0
        };
      row.costCount += 1;
      row.totalCost += costRecord.total_cost;
      row.lastTimestamp = Math.max(row.lastTimestamp, new Date(costRecord.created_at).getTime());
      traces.set(traceId, row);
    }
    return [...traces.values()].sort((left, right) => right.lastTimestamp - left.lastTimestamp);
  }, [projectTimelineQuery.data, projectTimelineQuery.isSuccess]);
  const effectiveSelectedTraceId = projectTimelineTraceRows.some(
    (trace) => trace.id === selectedTimelineTraceId
  )
    ? selectedTimelineTraceId
    : "";
  const projectTimelineEvents = useMemo(() => {
    if (!projectTimelineQuery.isSuccess) {
      return [];
    }
    let events = projectTimelineQuery.data.events;
    if (effectiveFocusedTaskId) {
      events = events.filter((event) => eventBelongsToTask(event, effectiveFocusedTaskId));
    }
    if (effectiveSelectedTraceId) {
      events = events.filter((event) => traceIdForEvent(event) === effectiveSelectedTraceId);
    }
    return [...events]
      .sort(
        (left, right) =>
          new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()
      )
      .slice(0, 8);
  }, [
    effectiveFocusedTaskId,
    effectiveSelectedTraceId,
    projectTimelineQuery.data,
    projectTimelineQuery.isSuccess
  ]);
  const selectedTimelineEvent =
    projectTimelineEvents.find((event) => event.id === selectedTimelineEventId) ??
    projectTimelineEvents[0] ??
    null;
  const selectedEventCostRecords =
    projectTimelineQuery.isSuccess && selectedTimelineEvent
      ? projectTimelineQuery.data.cost_records.filter(
          (costRecord) => traceIdForCost(costRecord) === traceIdForEvent(selectedTimelineEvent)
        )
      : [];
  const selectedMemoryItem =
    projectTimelineQuery.isSuccess && selectedMemoryItemId
      ? (projectTimelineQuery.data.memory_items.find((item) => item.id === selectedMemoryItemId) ??
        null)
      : null;
  const selectedProjectLastTaskRun =
    lastTaskRun?.task.project_id === effectiveSelectedProjectId ? lastTaskRun : null;
  const projectTimelineMode = !effectiveSelectedProjectId
    ? "sample"
    : projectTimelineQuery.isLoading
      ? "syncing"
      : projectTimelineQuery.isError
        ? "sample"
        : "live";
  const projectTimelineModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "No timeline"
  }[projectTimelineMode];
  const projectTimelineModeDetail =
    projectTimelineMode === "live" && projectTimelineQuery.data
      ? `${projectTimelineTasks.length} tasks / ${projectTimelineQuery.data.events.length} events / ${projectTimelineQuery.data.total_cost.toFixed(6)} ${projectTimelineQuery.data.currency}`
      : projectTimelineMode === "syncing"
        ? "Loading project timeline from gateway"
        : "Select a live project to inspect its tasks";
  const connectorJobRunsByJobId = useMemo(() => {
    const runsByJobId = new Map<string, ConnectorJobRunRecord[]>();
    if (!connectorJobRunsQuery.isSuccess) {
      return runsByJobId;
    }

    for (const run of connectorJobRunsQuery.data) {
      const runs = runsByJobId.get(run.job_id) ?? [];
      runs.push(run);
      runsByJobId.set(run.job_id, runs);
    }

    for (const runs of runsByJobId.values()) {
      runs.sort(
        (left, right) =>
          new Date(right.completed_at).getTime() - new Date(left.completed_at).getTime()
      );
    }

    return runsByJobId;
  }, [connectorJobRunsQuery.data, connectorJobRunsQuery.isSuccess]);
  const connectorJobRows = useMemo<ConnectorJobRecord[]>(() => {
    if (!connectorJobsQuery.isSuccess) {
      return [];
    }

    return [...connectorJobsQuery.data].sort((left, right) => {
      if (left.status !== right.status) {
        return left.status === "active" ? -1 : 1;
      }
      return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
    });
  }, [connectorJobsQuery.data, connectorJobsQuery.isSuccess]);
  const visibleConnectorJobRows = connectorJobRows
    .filter((job) => !effectiveSelectedProjectId || job.project_id === effectiveSelectedProjectId)
    .slice(0, 8);
  const connectorJobMode =
    connectorJobsQuery.isLoading || connectorJobRunsQuery.isLoading
      ? "syncing"
      : connectorJobsQuery.isError || connectorJobRunsQuery.isError
        ? "sample"
        : "live";
  const connectorJobModeLabel = {
    live: "Live API",
    syncing: "Syncing",
    sample: "No jobs"
  }[connectorJobMode];
  const connectorJobModeDetail =
    connectorJobMode === "live"
      ? `${visibleConnectorJobRows.length}/${connectorJobRows.length} jobs visibles / ${
          connectorJobRunsQuery.data?.length ?? 0
        } runs`
      : connectorJobMode === "syncing"
        ? "Loading connector jobs from state-service"
        : "State-service connector jobs unavailable";
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
  const effectiveToolName = availableToolOptions.includes(toolCallDraft.toolName)
    ? toolCallDraft.toolName
    : (availableToolOptions[0] ?? toolCallDraft.toolName);
  const preferredToolServiceId = preferredServiceForTool(
    effectiveToolName,
    availableServiceOptions
  );
  const effectiveToolServiceId =
    availableServiceOptions.includes(toolCallDraft.serviceId) &&
    serviceMatchesTool(effectiveToolName, toolCallDraft.serviceId)
      ? toolCallDraft.serviceId
      : (preferredToolServiceId ?? availableServiceOptions[0] ?? toolCallDraft.serviceId);
  const effectiveToolProjectId = toolCallDraft.projectId.trim() || effectiveSelectedProjectId;
  const hasToolArguments =
    effectiveToolName === "event.emit"
      ? toolCallDraft.summary.trim().length > 0
      : effectiveToolName === "web.fetch"
        ? toolCallDraft.url.trim().length > 0
        : true;
  const canCallTool =
    effectiveToolAgentId.length > 0 &&
    effectiveToolName.length > 0 &&
    toolCallDraft.reason.trim().length > 0 &&
    hasToolArguments &&
    !toolCallMutation.isPending;
  const updateToolCallDraft = (field: keyof ToolCallDraft, value: string) => {
    setToolCallDraft((draft) => ({
      ...draft,
      [field]: value
    }));
  };
  const handleToolNameChange = (toolName: string) => {
    setToolCallDraft((draft) => ({
      ...draft,
      toolName,
      serviceId:
        preferredServiceForTool(toolName, availableServiceOptions) ??
        draft.serviceId
    }));
  };
  const handleToolCallSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canCallTool) {
      return;
    }
    toolCallMutation.mutate(
      toolCallFromDraft(
        {
          ...toolCallDraft,
          toolName: effectiveToolName,
          serviceId: effectiveToolServiceId
        },
        {
          agentId: effectiveToolAgentId,
          projectId: effectiveToolProjectId
        }
      )
    );
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
                  className={`grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1fr)_112px_150px_auto] ${
                    effectiveSelectedProjectId === project.id ? "bg-accent-soft/40" : ""
                  }`}
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
                  <div className="flex items-center justify-end">
                    <button
                      className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-accent transition enabled:hover:border-accent/40 enabled:hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={project.source !== "api"}
                      type="button"
                      onClick={() => {
                        setSelectedProjectId(project.id);
                        setFocusedTimelineTaskId("");
                        setSelectedTimelineTraceId("");
                        setSelectedTimelineEventId("");
                        setSelectedMemoryItemId("");
                        setRunReadyDraft((draft) => ({
                          ...draft,
                          projectId: project.id
                        }));
                      }}
                    >
                      Inspect
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel">
            <SectionHeader
              eyebrow="Project detail"
              title={selectedProjectRow ? selectedProjectRow.title : "Tâches et preuves"}
            />
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-muted">{projectTimelineModeDetail}</p>
                {effectiveSelectedProjectId ? (
                  <p className="mt-1 truncate text-[11px] text-muted">
                    {effectiveSelectedProjectId}
                  </p>
                ) : null}
                {selectedProjectLastTaskRun ? (
                  <p className="mt-1 truncate text-[11px] font-medium text-ok">
                    Last task run: {selectedProjectLastTaskRun.task.title} /{" "}
                    {selectedProjectLastTaskRun.task.status} / {selectedProjectLastTaskRun.trace_id}
                  </p>
                ) : null}
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <select
                  className="h-9 max-w-[220px] rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Projet inspecté"
                  name="selected_project_id"
                  value={effectiveSelectedProjectId}
                  onChange={(event) => {
                    setSelectedProjectId(event.target.value);
                    setFocusedTimelineTaskId("");
                    setSelectedTimelineTraceId("");
                    setSelectedTimelineEventId("");
                    setSelectedMemoryItemId("");
                    setRunReadyDraft((draft) => ({
                      ...draft,
                      projectId: event.target.value
                    }));
                  }}
                >
                  {liveProjectRows.length === 0 ? <option value="">No project</option> : null}
                  {liveProjectRows.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.title}
                    </option>
                  ))}
                </select>
                <span
                  className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[projectTimelineMode]}`}
                >
                  {projectTimelineModeLabel}
                </span>
              </div>
            </div>
            {projectTimelineQuery.isSuccess ? (
              <div className="divide-y divide-border">
                <div className="grid gap-px bg-border sm:grid-cols-4">
                  {[
                    ["tasks", String(projectTimelineTasks.length)],
                    ["events", String(projectTimelineQuery.data.events.length)],
                    ["memory", String(projectTimelineQuery.data.memory_items.length)],
                    [
                      "cost",
                      `${projectTimelineQuery.data.total_cost.toFixed(6)} ${projectTimelineQuery.data.currency}`
                    ]
                  ].map(([label, value]) => (
                    <div key={label} className="min-w-0 bg-panel px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase text-muted">{label}</p>
                      <p className="mt-1 truncate text-sm font-semibold text-ink">{value}</p>
                    </div>
                  ))}
                </div>
                {projectTimelineTraceRows.length > 0 ? (
                  <div className="grid gap-2 px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold uppercase text-muted">Traces</p>
                      <button
                        className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-muted transition hover:border-accent/40 hover:text-accent"
                        type="button"
                        onClick={() => {
                          setSelectedTimelineTraceId("");
                          setSelectedTimelineEventId("");
                        }}
                      >
                        All traces
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {projectTimelineTraceRows.slice(0, 8).map((trace) => (
                        <button
                          key={trace.id}
                          className={`max-w-full rounded-md px-2 py-1 text-left text-[11px] ring-1 transition ${
                            effectiveSelectedTraceId === trace.id
                              ? "bg-info-soft text-info ring-info/20"
                              : "bg-slate-100 text-muted ring-border hover:text-ink"
                          }`}
                          type="button"
                          onClick={() => {
                            setSelectedTimelineTraceId(
                              effectiveSelectedTraceId === trace.id ? "" : trace.id
                            );
                            setSelectedTimelineEventId("");
                          }}
                        >
                          <span className="block max-w-[260px] truncate font-medium">
                            {trace.label}
                          </span>
                          <span className="block truncate">
                            {trace.eventCount} events / {trace.costCount} costs /{" "}
                            {trace.totalCost.toFixed(6)} {projectTimelineQuery.data.currency}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                {projectTimelineQuery.data.memory_items.length > 0 ? (
                  <div className="grid gap-3 px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-[11px] font-semibold uppercase text-muted">
                          Memory review
                        </p>
                        <p className="mt-1 truncate text-xs text-muted">
                          proposed {memoryCountByStatus(projectTimelineQuery.data, "proposed")} /
                          approved {memoryCountByStatus(projectTimelineQuery.data, "approved")} /
                          rejected {memoryCountByStatus(projectTimelineQuery.data, "rejected")}
                        </p>
                      </div>
                      {selectedMemoryItem ? (
                        <button
                          className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-muted transition hover:border-accent/40 hover:text-accent"
                          type="button"
                          onClick={() => setSelectedMemoryItemId("")}
                        >
                          Close memory
                        </button>
                      ) : null}
                    </div>
                    <div className="grid gap-2">
                      {projectTimelineQuery.data.memory_items.map((memoryItem) => {
                        const isMutatingMemory =
                          memoryStatusMutation.isPending &&
                          memoryStatusMutation.variables?.itemId === memoryItem.id;
                        return (
                          <article
                            key={memoryItem.id}
                            className={`grid gap-3 rounded-md border border-border px-3 py-3 md:grid-cols-[minmax(0,1fr)_auto] ${
                              selectedMemoryItemId === memoryItem.id ? "bg-ok-soft/30" : "bg-white"
                            }`}
                          >
                            <button
                              className="min-w-0 text-left"
                              type="button"
                              onClick={() =>
                                setSelectedMemoryItemId(
                                  selectedMemoryItemId === memoryItem.id ? "" : memoryItem.id
                                )
                              }
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <span
                                  className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${memoryStatusClass[memoryItem.status]}`}
                                >
                                  {memoryItem.status}
                                </span>
                                <span className="max-w-full truncate text-xs text-muted">
                                  {memoryItem.id} / {memoryItem.agent_id ?? "agent"} /{" "}
                                  {memoryItem.scope}
                                </span>
                              </div>
                              <BalancedText className="mt-2 text-sm text-muted" font="400 13px Inter Variable" lineHeight={18}>
                                {memoryItem.content}
                              </BalancedText>
                            </button>
                            <div className="flex items-center gap-1.5 md:justify-end">
                              <button
                                className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-ok transition enabled:hover:border-ok/40 enabled:hover:bg-ok-soft disabled:cursor-not-allowed disabled:opacity-40"
                                disabled={
                                  memoryItem.status === "approved" ||
                                  isMutatingMemory ||
                                  memoryStatusMutation.isPending
                                }
                                type="button"
                                onClick={() =>
                                  memoryStatusMutation.mutate({
                                    itemId: memoryItem.id,
                                    status: "approved"
                                  })
                                }
                              >
                                <Check size={13} />
                                <span>{isMutatingMemory ? "Saving" : "Approve"}</span>
                              </button>
                              <button
                                className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-risk transition enabled:hover:border-risk/40 enabled:hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-40"
                                disabled={
                                  memoryItem.status === "rejected" ||
                                  isMutatingMemory ||
                                  memoryStatusMutation.isPending
                                }
                                type="button"
                                onClick={() =>
                                  memoryStatusMutation.mutate({
                                    itemId: memoryItem.id,
                                    status: "rejected"
                                  })
                                }
                              >
                                <X size={13} />
                                <span>{isMutatingMemory ? "Saving" : "Reject"}</span>
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                    {selectedMemoryItem ? (
                      <pre className="max-h-44 overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
                        {formatPayload(selectedMemoryItem)}
                      </pre>
                    ) : null}
                    {memoryStatusMutation.isError ? (
                      <p className="text-xs font-medium text-risk">
                        {memoryStatusMutation.error instanceof Error
                          ? memoryStatusMutation.error.message
                          : "Memory status update failed."}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <div className="px-4 py-3">
                    <p className="text-xs text-muted">Aucune memory candidate pour ce projet.</p>
                  </div>
                )}
                {selectedProjectLastTaskRun ? (
                  <div className="grid gap-3 px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-[11px] font-semibold uppercase text-muted">
                          Last run memory context
                        </p>
                        <p className="mt-1 truncate text-xs text-muted">
                          {selectedProjectLastTaskRun.memory_context.items.length} approved items /
                          {selectedProjectLastTaskRun.memory_context.tokens_used}/
                          {selectedProjectLastTaskRun.memory_context.token_budget} estimated tokens /
                          {selectedProjectLastTaskRun.memory_context.agent_id}
                        </p>
                      </div>
                      <span className="rounded-md bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info ring-1 ring-info/15">
                        {traceLabel(selectedProjectLastTaskRun.trace_id)}
                      </span>
                    </div>
                    <div className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(260px,0.7fr)]">
                      <div className="min-w-0 rounded-md bg-slate-50 p-3">
                        <BalancedText className="text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                          {selectedProjectLastTaskRun.memory_context.summary ||
                            "No memory assembly summary returned."}
                        </BalancedText>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {selectedProjectLastTaskRun.memory_context.allowed_scopes.map((scope) => (
                            <span
                              key={scope}
                              className="max-w-full truncate rounded-md bg-white px-2 py-0.5 text-[11px] text-muted ring-1 ring-border"
                            >
                              {scope}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="grid gap-2">
                        {selectedProjectLastTaskRun.memory_context.items.length > 0 ? (
                          selectedProjectLastTaskRun.memory_context.items.slice(0, 4).map((item) => (
                            <article
                              key={item.id}
                              className="rounded-md border border-border bg-white p-3"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <span
                                  className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${memoryStatusClass[item.status]}`}
                                >
                                  {item.status}
                                </span>
                                <span className="max-w-full truncate text-[11px] text-muted">
                                  {item.id} / {item.scope}
                                </span>
                              </div>
                              <BalancedText className="mt-2 text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                                {item.content}
                              </BalancedText>
                            </article>
                          ))
                        ) : (
                          <p className="rounded-md bg-slate-50 p-3 text-xs text-muted">
                            No approved memory item was injected for this run.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ) : null}
                {focusedTimelineTask ? (
                  <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                    <p className="min-w-0 truncate text-xs text-muted">
                      Events filtered on {focusedTimelineTask.title}
                    </p>
                    <button
                      className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-muted transition hover:border-accent/40 hover:text-accent"
                      type="button"
                      onClick={() => {
                        setFocusedTimelineTaskId("");
                        setSelectedTimelineEventId("");
                      }}
                    >
                      All events
                    </button>
                  </div>
                ) : null}
                {taskRunMutation.isError ? (
                  <p className="px-4 py-2 text-xs font-medium text-risk">
                    {taskRunMutation.error instanceof Error
                      ? taskRunMutation.error.message
                      : "Task run failed."}
                  </p>
                ) : null}
                {projectTimelineTasks.length === 0 ? (
                  <article className="px-4 py-5">
                    <p className="text-sm font-medium text-ink">Aucune tâche projet</p>
                    <p className="mt-1 text-xs text-muted">La timeline ne retourne pas encore de task.</p>
                  </article>
                ) : null}
                {projectTimelineTasks.map((task) => (
                  <article
                    key={task.id}
                    className={`grid gap-3 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_180px] ${
                      effectiveFocusedTaskId === task.id ? "bg-info-soft/35" : ""
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-muted ring-1 ring-border">
                          #{task.sequence}
                        </span>
                        <h3 className="min-w-0 truncate text-sm font-semibold text-ink">
                          {task.title}
                        </h3>
                        <span
                          className={`rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold ring-1 ring-border ${projectStatusClass[task.status]}`}
                        >
                          {task.status}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted">
                        {task.id} / {task.assigned_agent_id} / attempts {task.attempt_count}
                        /{task.max_attempts}
                      </p>
                      <BalancedText className="mt-2 text-sm text-muted" font="400 13px Inter Variable" lineHeight={18}>
                        {taskResultSummary(task)}
                      </BalancedText>
                      {task.acceptance_criteria.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {task.acceptance_criteria.slice(0, 3).map((criterion) => (
                            <span
                              key={criterion}
                              className="max-w-full truncate rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-muted ring-1 ring-border"
                            >
                              {criterion}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="grid content-start gap-2 text-xs text-muted">
                      <div className="flex items-center justify-between gap-2">
                        <span>cost</span>
                        <span className="font-medium text-ink">
                          {taskCost(projectTimelineQuery.data, task.id).toFixed(6)}{" "}
                          {projectTimelineQuery.data.currency}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>events</span>
                        <span className="font-medium text-ink">
                          {taskEventCount(projectTimelineQuery.data, task.id)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>depends</span>
                        <span className="font-medium text-ink">{task.depends_on.length}</span>
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-1.5">
                        <button
                          className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-muted transition hover:border-info/40 hover:bg-info-soft hover:text-info"
                          type="button"
                          onClick={() => {
                            setFocusedTimelineTaskId(
                              effectiveFocusedTaskId === task.id ? "" : task.id
                            );
                            setSelectedTimelineEventId("");
                          }}
                        >
                          {effectiveFocusedTaskId === task.id ? "All" : "Focus"}
                        </button>
                        <button
                          className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-accent transition enabled:hover:border-accent/40 enabled:hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={
                            task.status !== "queued" ||
                            taskRunMutation.isPending ||
                            taskReviewMutation.isPending
                          }
                          type="button"
                          onClick={() => taskRunMutation.mutate(task.id)}
                        >
                          {taskRunMutation.isPending && taskRunMutation.variables === task.id
                            ? "Run..."
                            : "Run"}
                        </button>
                        <button
                          className="h-8 rounded-md border border-border bg-white px-2 text-xs font-medium text-warn transition enabled:hover:border-warn/40 enabled:hover:bg-warn-soft disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={
                            task.status !== "needs_review" ||
                            taskRunMutation.isPending ||
                            taskReviewMutation.isPending
                          }
                          type="button"
                          onClick={() =>
                            taskReviewMutation.mutate({
                              taskId: task.id,
                              decision: {
                                action: "retry",
                                reason: defaultTaskReviewReason("retry")
                              }
                            })
                          }
                        >
                          {taskReviewMutation.isPending &&
                          taskReviewMutation.variables?.taskId === task.id
                            ? "Retry..."
                            : "Retry"}
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
                {projectTimelineEvents.length > 0 ? (
                  <div className="grid gap-2 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase text-muted">Derniers events</p>
                    <div className="flex flex-wrap gap-1.5">
                      {projectTimelineEvents.map((event) => (
                        <button
                          key={event.id}
                          className={`max-w-full truncate rounded-md px-2 py-0.5 text-left text-[11px] ring-1 transition ${
                            selectedTimelineEvent?.id === event.id
                              ? "bg-accent-soft text-accent ring-accent/20"
                              : "bg-slate-100 text-muted ring-border hover:text-ink"
                          }`}
                          type="button"
                          onClick={() => setSelectedTimelineEventId(event.id)}
                        >
                          {event.type} / {event.target ?? event.trace_id ?? "system"}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : effectiveFocusedTaskId || effectiveSelectedTraceId ? (
                  <div className="px-4 py-3">
                    <p className="text-xs text-muted">Aucun event pour ce filtre.</p>
                  </div>
                ) : null}
                {selectedTimelineEvent ? (
                  <div className="grid gap-3 px-4 py-3 xl:grid-cols-[minmax(0,1fr)_220px]">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-md bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent ring-1 ring-accent/15">
                          {selectedTimelineEvent.type}
                        </span>
                        <span className="max-w-full truncate text-xs text-muted">
                          {selectedTimelineEvent.id} / {traceLabel(traceIdForEvent(selectedTimelineEvent))}
                        </span>
                      </div>
                      <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
                        {formatPayload(selectedTimelineEvent.payload)}
                      </pre>
                    </div>
                    <div className="grid content-start gap-2 text-xs text-muted">
                      <div className="flex items-center justify-between gap-2">
                        <span>target</span>
                        <span className="min-w-0 truncate font-medium text-ink">
                          {selectedTimelineEvent.target ?? "system"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>source</span>
                        <span className="min-w-0 truncate font-medium text-ink">
                          {selectedTimelineEvent.source_agent_id ?? "system"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>trace costs</span>
                        <span className="font-medium text-ink">
                          {selectedEventCostRecords.length}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>trace spend</span>
                        <span className="font-medium text-ink">
                          {selectedEventCostRecords
                            .reduce((total, costRecord) => total + costRecord.total_cost, 0)
                            .toFixed(6)}{" "}
                          {projectTimelineQuery.data.currency}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="px-4 py-5">
                <p className="text-sm font-medium text-ink">
                  {projectTimelineQuery.isLoading ? "Chargement timeline projet" : "Timeline indisponible"}
                </p>
                <p className="mt-1 text-xs text-muted">
                  {projectTimelineQuery.isError && projectTimelineQuery.error instanceof Error
                    ? projectTimelineQuery.error.message
                    : "Sélectionne un projet live pour afficher ses tâches, coûts, mémoire et événements."}
                </p>
              </div>
            )}
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
                      <p className="text-[11px] text-muted">
                        memory {run.memory_context.items.length} items /{" "}
                        {run.memory_context.tokens_used}/{run.memory_context.token_budget} tokens
                      </p>
                      {run.tool_results.length > 0 ? (
                        <p className="text-[11px] text-muted">
                          tools {run.tool_results.length}:{" "}
                          {run.tool_results.map((toolResult) => toolResult.tool_name).join(", ")}
                        </p>
                      ) : null}
                    </div>
                  ))}
                  {lastRunBatch.skipped_tasks.length > 0 ? (
                    <div className="grid gap-1 rounded-md border border-warn/25 bg-warn-soft p-3">
                      {lastRunBatch.skipped_tasks.map((skippedTask) => (
                        <div key={skippedTask.task_id} className="grid gap-0.5">
                          <p className="text-[11px] font-semibold text-warn">
                            skipped {skippedTask.category} / {skippedTask.task_id}
                          </p>
                          <p className="text-[11px] text-muted">{skippedTask.reason}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
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
            <SectionHeader eyebrow="Connectors" title="Jobs autonomes" />
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">{connectorJobModeDetail}</p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[connectorJobMode]}`}
              >
                {connectorJobModeLabel}
              </span>
            </div>
            <div className="divide-y divide-border">
              {visibleConnectorJobRows.length === 0 ? (
                <article className="px-4 py-5">
                  <p className="text-sm font-medium text-ink">Aucun connector job visible</p>
                  <p className="mt-1 text-xs text-muted">
                    Aucun job n&apos;est rattaché au projet sélectionné, ou le state-service ne répond
                    pas encore.
                  </p>
                </article>
              ) : null}
              {visibleConnectorJobRows.map((job) => {
                const lastRun = connectorJobRunsByJobId.get(job.id)?.[0];
                const policyLabels = connectorJobPolicyLabels(job);
                const stopDetail = connectorJobStopDetail(job, lastRun);
                const nextRunLabel =
                  job.status === "active"
                    ? job.next_run_at
                      ? formatRelativeTimestamp(job.next_run_at)
                      : "due now"
                    : job.stopped_at
                      ? formatRelativeTimestamp(job.stopped_at)
                      : "stopped";
                const pendingConnectorJobAction =
                  connectorJobActionMutation.isPending &&
                  connectorJobActionMutation.variables?.jobId === job.id;
                return (
                  <article
                    key={job.id}
                    className="grid gap-3 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_190px_210px]"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${
                            connectorJobStatusClass[job.status] ?? connectorJobStatusClass.stopped
                          }`}
                        >
                          {job.status}
                        </span>
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-muted ring-1 ring-border">
                          {job.kind}
                        </span>
                        <h3 className="min-w-0 truncate text-sm font-semibold text-ink">
                          {job.id}
                        </h3>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted">
                        {job.service_id} / {job.owner_agent_id}
                      </p>
                      <BalancedText className="mt-2 text-sm text-muted" font="400 13px Inter Variable" lineHeight={18}>
                        {job.purpose}
                      </BalancedText>
                      {policyLabels.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {policyLabels.map((label) => (
                            <span
                              key={`${job.id}-${label}`}
                              className="max-w-full truncate rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-muted ring-1 ring-border"
                            >
                              {label}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="grid content-start gap-2 text-xs text-muted">
                      <div className="flex items-center justify-between gap-2">
                        <span>next</span>
                        <span className="min-w-0 truncate font-medium text-ink">{nextRunLabel}</span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>project</span>
                        <span className="min-w-0 truncate font-medium text-ink">
                          {job.project_id ?? "none"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>task</span>
                        <span className="min-w-0 truncate font-medium text-ink">
                          {job.task_id ?? "none"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span>schedule</span>
                        <span className="min-w-0 truncate font-medium text-ink">
                          {job.schedule ?? job.webhook_path ?? "manual"}
                        </span>
                      </div>
                    </div>
                    <div className="grid content-start gap-2 text-xs text-muted">
                      {lastRun ? (
                        <>
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${
                                connectorJobRunStatusClass[lastRun.status] ??
                                connectorJobRunStatusClass.skipped
                              }`}
                            >
                              last {lastRun.status}
                            </span>
                            <span className="min-w-0 truncate text-[11px] text-muted">
                              {formatRelativeTimestamp(lastRun.completed_at)}
                            </span>
                          </div>
                          {stopDetail ?? lastRun.error ? (
                            <BalancedText className="text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                              {stopDetail ?? lastRun.error ?? ""}
                            </BalancedText>
                          ) : null}
                          {lastRun.trace_id ? (
                            <p className="truncate text-[11px] text-muted">
                              {traceLabel(lastRun.trace_id)}
                            </p>
                          ) : null}
                        </>
                      ) : (
                        <p className="text-xs text-muted">No run recorded yet.</p>
                      )}
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {job.status === "active" ? (
                          <>
                            <button
                              className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-muted transition enabled:hover:border-info/40 enabled:hover:bg-info-soft enabled:hover:text-info disabled:cursor-not-allowed disabled:opacity-40"
                              disabled={pendingConnectorJobAction}
                              title="Run connector job now"
                              type="button"
                              onClick={() =>
                                connectorJobActionMutation.mutate({
                                  jobId: job.id,
                                  action: "run"
                                })
                              }
                            >
                              <Play size={13} />
                              <span>
                                {pendingConnectorJobAction &&
                                connectorJobActionMutation.variables?.action === "run"
                                  ? "Running"
                                  : "Run"}
                              </span>
                            </button>
                            <button
                              className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-risk transition enabled:hover:border-risk/40 enabled:hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-40"
                              disabled={pendingConnectorJobAction}
                              title="Stop connector job"
                              type="button"
                              onClick={() =>
                                connectorJobActionMutation.mutate({
                                  jobId: job.id,
                                  action: "stop"
                                })
                              }
                            >
                              <Ban size={13} />
                              <span>
                                {pendingConnectorJobAction &&
                                connectorJobActionMutation.variables?.action === "stop"
                                  ? "Stopping"
                                  : "Stop"}
                              </span>
                            </button>
                          </>
                        ) : (
                          <button
                            className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-ok transition enabled:hover:border-ok/40 enabled:hover:bg-ok-soft disabled:cursor-not-allowed disabled:opacity-40"
                            disabled={pendingConnectorJobAction}
                            title="Resume connector job"
                            type="button"
                            onClick={() =>
                              connectorJobActionMutation.mutate({
                                jobId: job.id,
                                action: "resume"
                              })
                            }
                          >
                            <RotateCcw size={13} />
                            <span>{pendingConnectorJobAction ? "Resuming" : "Resume"}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
            {connectorJobActionMutation.isError ? (
              <p className="border-t border-border px-4 py-2 text-xs font-medium text-risk">
                {connectorJobActionMutation.error instanceof Error
                  ? connectorJobActionMutation.error.message
                  : "Connector job action failed."}
              </p>
            ) : null}
            {connectorJobMode === "sample" ? (
              <p className="border-t border-border px-4 py-2 text-xs font-medium text-risk">
                {connectorJobsQuery.error instanceof Error
                  ? connectorJobsQuery.error.message
                  : connectorJobRunsQuery.error instanceof Error
                    ? connectorJobRunsQuery.error.message
                    : "Connector jobs unavailable."}
              </p>
            ) : null}
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
            <SectionHeader eyebrow="Connectors" title="Permission gate" />
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
              <p className="min-w-0 truncate text-xs text-muted">
                {worldViewQuery.isSuccess
                  ? `${worldViewQuery.data.available_services.length} services / ${worldViewQuery.data.available_connector_ids.length} connectors`
                  : effectiveToolAgentId
                    ? "Connecting to agent world-view"
                    : "No live agent selected"}
              </p>
              <span
                className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${dataModeClass[worldViewMode]}`}
              >
                {worldViewModeLabel}
              </span>
            </div>
            <form className="grid gap-3 px-4 py-3" onSubmit={handleToolCallSubmit}>
              <select
                className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Agent for tool call"
                value={effectiveToolAgentId}
                onChange={(event) => updateToolCallDraft("agentId", event.target.value)}
              >
                {liveAgentRows.length === 0 ? <option value="">No live agent</option> : null}
                {liveAgentRows.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </select>
              <div className="grid gap-2 sm:grid-cols-2">
                <select
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Tool name"
                  value={effectiveToolName}
                  onChange={(event) => handleToolNameChange(event.target.value)}
                >
                  {availableToolOptions.length === 0 ? <option value="">No tool</option> : null}
                  {availableToolOptions.map((tool) => (
                    <option key={tool} value={tool}>
                      {tool}
                    </option>
                  ))}
                </select>
                <select
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Service id"
                  value={effectiveToolServiceId}
                  onChange={(event) => updateToolCallDraft("serviceId", event.target.value)}
                >
                  {availableServiceOptions.length === 0 ? (
                    <option value="">No service</option>
                  ) : null}
                  {availableServiceOptions.map((service) => (
                    <option key={service} value={service}>
                      {service}
                    </option>
                  ))}
                </select>
              </div>
              <input
                className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Tool project id"
                placeholder={effectiveSelectedProjectId || "project_id optional"}
                value={toolCallDraft.projectId}
                onChange={(event) => updateToolCallDraft("projectId", event.target.value)}
              />
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Tool call reason"
                value={toolCallDraft.reason}
                onChange={(event) => updateToolCallDraft("reason", event.target.value)}
              />
              {effectiveToolName === "event.emit" ? (
                <textarea
                  className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Event summary"
                  value={toolCallDraft.summary}
                  onChange={(event) => updateToolCallDraft("summary", event.target.value)}
                />
              ) : null}
              {effectiveToolName === "web.fetch" ? (
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Fetch URL"
                  placeholder="https://example.com"
                  value={toolCallDraft.url}
                  onChange={(event) => updateToolCallDraft("url", event.target.value)}
                />
              ) : null}
              <button
                className="flex h-9 items-center justify-center gap-2 rounded-md bg-ink px-3 text-xs font-medium text-white transition enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!canCallTool}
                type="submit"
              >
                <PlugZap size={14} />
                <span>{toolCallMutation.isPending ? "Checking..." : "Call gate"}</span>
              </button>
            </form>
            <div className="grid gap-3 border-t border-border px-4 py-3">
              {worldViewQuery.data ? (
                <>
                  <div className="grid gap-1.5">
                    <p className="text-[11px] font-semibold uppercase text-muted">
                      Allowed tools
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {worldViewQuery.data.permissions.allowed_tools.map((tool) => (
                        <span
                          key={tool}
                          className="max-w-full truncate rounded-md bg-ok-soft px-2 py-0.5 text-[11px] text-ok ring-1 ring-ok/15"
                        >
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                  {worldViewQuery.data.permissions.denied_tools.length > 0 ? (
                    <div className="grid gap-1.5">
                      <p className="text-[11px] font-semibold uppercase text-muted">
                        Denied tools
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {worldViewQuery.data.permissions.denied_tools.map((tool) => (
                          <span
                            key={tool}
                            className="max-w-full truncate rounded-md bg-risk-soft px-2 py-0.5 text-[11px] text-risk ring-1 ring-risk/15"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="grid gap-1.5">
                    <p className="text-[11px] font-semibold uppercase text-muted">
                      Connectors
                    </p>
                    <p className="truncate text-xs text-muted">
                      {availableConnectorOptions.length > 0
                        ? availableConnectorOptions.join(" / ")
                        : "No connector exposed"}
                    </p>
                  </div>
                </>
              ) : null}
              {lastToolResult ? (
                <pre className="max-h-40 overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
                  {formatPayload(lastToolResult.output)}
                </pre>
              ) : null}
              {toolCallMutation.isError ? (
                <p className="text-xs font-medium text-risk">
                  {toolCallMutation.error instanceof Error
                    ? toolCallMutation.error.message
                    : "Tool gate call failed."}
                </p>
              ) : null}
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
                  <p className="text-sm font-medium text-ink">Aucune demande</p>
                  <p className="mt-1 text-xs text-muted">
                    Les queues control-plane et credentials sont vides.
                  </p>
                </article>
              ) : null}
              {approvalRows.map((approval) => {
                const Icon = approval.icon;
                const isCredentialApproval = approval.source === "credential";
                const isPending = approval.status === "requested" && approval.source !== "sample";
                const candidateServiceId = approval.candidateServiceIds?.[0];
                const canApplyGrant =
                  isCredentialApproval && approval.status === "approved" && !!candidateServiceId;
                const isDecisionPending =
                  decisionMutation.isPending ||
                  credentialDecisionMutation.isPending ||
                  credentialGrantMutation.isPending;
                const isMutatingThisApproval =
                  isCredentialApproval
                    ? credentialDecisionMutation.isPending &&
                      credentialDecisionMutation.variables?.requestId === approval.id
                    : decisionMutation.isPending &&
                      decisionMutation.variables?.requestId === approval.id;
                const isApplyingGrant =
                  credentialGrantMutation.isPending &&
                  credentialGrantMutation.variables?.requestId === approval.id;
                const decideApproval = (status: "approved" | "rejected") => {
                  const payload = { requestId: approval.id, status };
                  if (isCredentialApproval) {
                    credentialDecisionMutation.mutate(payload);
                    return;
                  }
                  decisionMutation.mutate(payload);
                };
                const applyGrant = () => {
                  if (!candidateServiceId) {
                    return;
                  }
                  credentialGrantMutation.mutate({
                    requestId: approval.id,
                    serviceId: candidateServiceId
                  });
                };
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
                            {isCredentialApproval ? (
                              <button
                                className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-accent transition enabled:hover:border-accent/40 enabled:hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
                                aria-label={`Apply grant ${approval.title}`}
                                title={
                                  candidateServiceId
                                    ? `Apply grant to ${candidateServiceId}`
                                    : `No candidate service for ${approval.title}`
                                }
                                disabled={!canApplyGrant || isDecisionPending}
                                onClick={applyGrant}
                              >
                                <KeyRound size={15} />
                              </button>
                            ) : null}
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-ok transition enabled:hover:border-ok/40 enabled:hover:bg-ok-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Approve ${approval.title}`}
                              title={`Approve ${approval.title}`}
                              disabled={!isPending || isDecisionPending}
                              onClick={() => decideApproval("approved")}
                            >
                              <Check size={15} />
                            </button>
                            <button
                              className="grid h-8 w-8 place-items-center rounded-md border border-border bg-white text-risk transition enabled:hover:border-risk/40 enabled:hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-40"
                              aria-label={`Reject ${approval.title}`}
                              title={`Reject ${approval.title}`}
                              disabled={!isPending || isDecisionPending}
                              onClick={() => decideApproval("rejected")}
                            >
                              <X size={15} />
                            </button>
                          </div>
                        </div>
                        {isMutatingThisApproval ? (
                          <p className="mt-2 text-xs font-medium text-accent">Decision pending...</p>
                        ) : null}
                        {isApplyingGrant ? (
                          <p className="mt-2 text-xs font-medium text-accent">Grant applying...</p>
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
