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
  createAgentLifecycleRequest,
  decideAgentLifecycleRequest,
  getAgentWorldView,
  listAgents,
  listAgentLifecycleRequests,
  updateAgentModelPolicy,
  type AgentDefinition,
  type AgentLifecycleRequest,
  type LocalWorldView
} from "../lib/control-plane-api";
import {
  applyMemoryRelationProposal,
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
  type MemoryItem,
  type MemoryStatus,
  type ProjectTimeline,
  type TaskSkipRecord,
  type TaskRunBatchResult,
  type TaskRunResult,
  type TaskRecord,
  type TaskReviewAction,
  type TaskReviewDecision,
  type ToolCallRequest,
  type ToolResult
} from "../lib/gateway-api";
import {
  listAuditLogs,
  listConnectorJobRuns,
  listConnectorJobs,
  listEvents,
  listModelDefinitions,
  listModelPolicies,
  listProjects,
  type AuditLogRecord,
  type ConnectorJobRecord,
  type ConnectorJobRunRecord,
  type EventRecord,
  type ModelDefinition,
  type ModelPolicy,
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
  agentId?: string;
  createdAtMs: number;
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
  modelPolicyId?: string | null;
  allowedModelIds: string[];
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

type LifecycleCreateDraft = {
  agentId: string;
  name: string;
  role: string;
  division: string;
  managerId: string;
  reason: string;
  soulIdentity: string;
  soulMission: string;
};

type LifecycleUpdateDraft = {
  targetAgentId: string;
  role: string;
  division: string;
  reason: string;
  soulIdentity: string;
  soulMission: string;
};

type LifecycleDeactivateDraft = {
  targetAgentId: string;
  reason: string;
};

type TimelineViewModel = {
  id: string;
  time: string;
  label: string;
  target: string;
  detail?: string;
  tone: Tone;
  icon: typeof Activity;
  source: "api" | "sample";
};

type TaskSkipTimelineRecord = TaskSkipRecord & {
  event_id: string;
  timestamp: string;
  trace_id?: string | null;
};

type TraceViewModel = {
  id: string;
  label: string;
  eventCount: number;
  costCount: number;
  totalCost: number;
  lastTimestamp: number;
};

type ConnectorTraceViewModel = {
  id: string;
  label: string;
  runCount: number;
  eventCount: number;
  auditCount: number;
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

const initialLifecycleCreateDraft: LifecycleCreateDraft = {
  agentId: "agent-dashboard-draft",
  name: "Dashboard Agent Draft",
  role: "Dashboard-created AI employee",
  division: "dev",
  managerId: "agent-direction",
  reason: "Create a scoped AI employee from the Synarch dashboard.",
  soulIdentity: "A scoped AI employee created through Synarch lifecycle governance.",
  soulMission: "Validate dashboard lifecycle creation, human approval, and active soul injection."
};

const initialLifecycleUpdateDraft: LifecycleUpdateDraft = {
  targetAgentId: "",
  role: "",
  division: "",
  reason: "Update this AI employee through Synarch lifecycle governance.",
  soulIdentity: "",
  soulMission: ""
};

const initialLifecycleDeactivateDraft: LifecycleDeactivateDraft = {
  targetAgentId: "",
  reason: "Deactivate this AI employee through Synarch lifecycle governance."
};

function createLifecycleCreateDraft(): LifecycleCreateDraft {
  const suffix = Date.now().toString();
  return {
    agentId: `agent-dashboard-${suffix}`,
    name: `Dashboard Agent ${suffix.slice(-6)}`,
    role: "Dashboard-created AI employee",
    division: "dev",
    managerId: "agent-direction",
    reason: "Create a scoped AI employee from the Synarch dashboard.",
    soulIdentity: "A scoped AI employee created through Synarch lifecycle governance.",
    soulMission:
      "Validate dashboard lifecycle creation, human approval, and active soul injection."
  };
}

function soulIdForAgent(agentId: string): string {
  const suffix = agentId.replace(/^agent-/, "");
  return `soul-${suffix}-v1`;
}

function lifecycleUpdateRequestId(agentId: string): string {
  return `lifecycle-update-${agentId}-${Date.now()}`;
}

function soulUpdateIdForAgent(agentId: string, version: number): string {
  const suffix = agentId.replace(/^agent-/, "");
  return `soul-${suffix}-update-${Date.now()}-v${version}`;
}

function lifecycleDeactivateRequestId(agentId: string): string {
  return `lifecycle-deactivate-${agentId}-${Date.now()}`;
}

function resolveLifecycleCreateDraft(draft: LifecycleCreateDraft): LifecycleCreateDraft {
  const generatedDraft = createLifecycleCreateDraft();
  const usesDefaultAgentId = draft.agentId.trim() === initialLifecycleCreateDraft.agentId;
  const usesDefaultName = draft.name.trim() === initialLifecycleCreateDraft.name;

  return {
    ...draft,
    agentId: usesDefaultAgentId ? generatedDraft.agentId : draft.agentId.trim(),
    name: usesDefaultAgentId && usesDefaultName ? generatedDraft.name : draft.name.trim(),
    role: draft.role.trim(),
    division: draft.division.trim(),
    managerId: draft.managerId.trim(),
    reason: draft.reason.trim(),
    soulIdentity: draft.soulIdentity.trim(),
    soulMission: draft.soulMission.trim()
  };
}

function timestampMs(value: string): number {
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function approvalStatusRank(status: string): number {
  if (status === "requested") {
    return 0;
  }
  if (status === "approved") {
    return 1;
  }
  if (status === "applied") {
    return 2;
  }
  return 3;
}

function sortApprovalRows(rows: ApprovalViewModel[]): ApprovalViewModel[] {
  return [...rows].sort((left, right) => {
    const statusDelta = approvalStatusRank(left.status) - approvalStatusRank(right.status);
    if (statusDelta !== 0) {
      return statusDelta;
    }
    return right.createdAtMs - left.createdAtMs;
  });
}

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
  if (request.action === "update_agent") {
    return "info";
  }
  return "accent";
}

function lifecycleIcon(request: AgentLifecycleRequest): typeof UserRoundPlus {
  if (request.action === "deactivate_agent") {
    return UserRoundX;
  }
  if (request.action === "update_agent") {
    return PencilLine;
  }
  return UserRoundPlus;
}

function lifecycleApprovalRow(request: AgentLifecycleRequest): ApprovalViewModel {
  return {
    id: request.id,
    agentId: request.proposed_agent?.id ?? request.target_agent_id ?? undefined,
    createdAtMs: timestampMs(request.created_at),
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

function lifecycleRequestTarget(request: AgentLifecycleRequest): string {
  return request.proposed_agent?.name ?? request.target_agent_id ?? request.id;
}

function lifecycleRequestDetail(request: AgentLifecycleRequest): string {
  return request.proposed_agent?.id ?? request.target_agent_id ?? "no target";
}

function credentialApprovalRow(request: CredentialAccessRequest): ApprovalViewModel {
  const scopes =
    request.requested_scopes.length > 0
      ? request.requested_scopes.join(", ")
      : "tool/service mapping";
  return {
    id: request.id,
    createdAtMs: timestampMs(request.created_at),
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
    modelPolicyId: agent.model_policy_id,
    allowedModelIds: agent.allowed_model_ids,
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
  return (
    event.target === taskId ||
    event.payload.task_id === taskId ||
    payloadStringArray(event.payload, "skipped_task_ids").includes(taskId) ||
    taskSkipsFromPayload(event.payload).some((skip) => skip.task_id === taskId)
  );
}

function traceIdForEvent(event: EventRecord): string {
  return event.trace_id ?? "no-trace";
}

function traceIdForCost(costRecord: { trace_id?: string | null }): string {
  return costRecord.trace_id ?? "no-trace";
}

function traceIdForConnectorRecord(record: { trace_id?: string | null }): string {
  return record.trace_id ?? "no-trace";
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

function modelPolicyLabel(
  policy: ModelPolicy,
  modelById: Map<string, ModelDefinition>
): string {
  const defaultModel = modelById.get(policy.default_model_id);
  return `${policy.name} / ${defaultModel?.display_name ?? policy.default_model_id}`;
}

function modelPolicyShortLabel(policyId?: string | null): string {
  if (!policyId) {
    return "no policy";
  }
  return policyId.replace(/^policy-/, "");
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

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function payloadStringArray(payload: Record<string, unknown>, key: string): string[] {
  const value = payload[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function taskSkipsFromPayload(payload: Record<string, unknown>): TaskSkipRecord[] {
  const value = payload.skipped_tasks;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }
    const candidate = item as Record<string, unknown>;
    if (
      typeof candidate.task_id !== "string" ||
      typeof candidate.category !== "string" ||
      typeof candidate.reason !== "string"
    ) {
      return [];
    }
    return [
      {
        task_id: candidate.task_id,
        category: candidate.category,
        reason: candidate.reason
      }
    ];
  });
}

function taskSkipRecordsForTask(
  timeline: ProjectTimeline,
  taskId: string
): TaskSkipTimelineRecord[] {
  return timeline.events
    .flatMap((event) =>
      taskSkipsFromPayload(event.payload)
        .filter((skip) => skip.task_id === taskId)
        .map((skip) => ({
          ...skip,
          event_id: event.id,
          timestamp: event.timestamp,
          trace_id: event.trace_id
        }))
    )
    .sort(
      (left, right) =>
        new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()
    );
}

function schedulerSkipDetail(event: EventRecord): string | null {
  const skips = taskSkipsFromPayload(event.payload);
  if (skips.length === 0) {
    return null;
  }
  const [firstSkip] = skips;
  const suffix = skips.length > 1 ? ` +${skips.length - 1}` : "";
  return `${firstSkip.category}: ${firstSkip.reason}${suffix}`;
}

function eventBelongsToConnectorJob(
  event: EventRecord,
  jobId: string,
  traceIds: Set<string>
): boolean {
  return (
    payloadString(event.payload, "connector_job_id") === jobId ||
    Boolean(event.trace_id && traceIds.has(event.trace_id))
  );
}

function auditBelongsToConnectorJob(
  auditLog: AuditLogRecord,
  jobId: string,
  traceIds: Set<string>
): boolean {
  return (
    (auditLog.target_type === "connector_job" && auditLog.target_id === jobId) ||
    payloadString(auditLog.payload, "connector_job_id") === jobId ||
    Boolean(auditLog.trace_id && traceIds.has(auditLog.trace_id))
  );
}

function formatPayload(payload: unknown): string {
  return JSON.stringify(payload, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function memoryMetadata(memoryItem: MemoryItem): Record<string, unknown> {
  return isRecord(memoryItem.metadata) ? memoryItem.metadata : {};
}

function isMemoryRelationProposal(memoryItem: MemoryItem): boolean {
  return memoryMetadata(memoryItem).kind === "memory_relation_proposal";
}

function memoryRelationSourceId(memoryItem: MemoryItem): string | null {
  const sourceMemoryId = memoryMetadata(memoryItem).source_memory_id;
  return typeof sourceMemoryId === "string" ? sourceMemoryId : null;
}

function memoryRelationRelatedIds(memoryItem: MemoryItem): string[] {
  const relatedMemoryIds = memoryMetadata(memoryItem).related_memory_ids;
  if (!Array.isArray(relatedMemoryIds)) {
    return [];
  }
  return relatedMemoryIds.filter(
    (relatedMemoryId): relatedMemoryId is string =>
      typeof relatedMemoryId === "string" && relatedMemoryId.length > 0
  );
}

function memoryRelationApplied(memoryItem: MemoryItem): boolean {
  return memoryMetadata(memoryItem).applied === true;
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
  if (event.type === "scheduler.tick" && taskSkipsFromPayload(event.payload).length > 0) {
    return "warn";
  }
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
  if (event.type === "scheduler.tick" && taskSkipsFromPayload(event.payload).length > 0) {
    return AlertTriangle;
  }
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
  const skippedTasks = taskSkipsFromPayload(event.payload);
  const detail = schedulerSkipDetail(event);
  return {
    id: event.id,
    time: formatLifecycleAge(event.timestamp),
    label:
      event.type === "scheduler.tick" && skippedTasks.length > 0
        ? `scheduler.tick / ${skippedTasks.length} skipped`
        : event.type,
    target: event.target ?? event.source_agent_id ?? event.trace_id ?? "system",
    detail: detail ?? undefined,
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
  const [lifecycleCreateDraft, setLifecycleCreateDraft] =
    useState<LifecycleCreateDraft>(initialLifecycleCreateDraft);
  const [lifecycleUpdateDraft, setLifecycleUpdateDraft] =
    useState<LifecycleUpdateDraft>(initialLifecycleUpdateDraft);
  const [lifecycleDeactivateDraft, setLifecycleDeactivateDraft] =
    useState<LifecycleDeactivateDraft>(initialLifecycleDeactivateDraft);
  const [lastLifecycleRequest, setLastLifecycleRequest] =
    useState<AgentLifecycleRequest | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [focusedTimelineTaskId, setFocusedTimelineTaskId] = useState("");
  const [selectedTimelineTraceId, setSelectedTimelineTraceId] = useState("");
  const [selectedTimelineEventId, setSelectedTimelineEventId] = useState("");
  const [selectedConnectorJobId, setSelectedConnectorJobId] = useState("");
  const [selectedConnectorTraceId, setSelectedConnectorTraceId] = useState("");
  const [selectedMemoryItemId, setSelectedMemoryItemId] = useState("");
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [taskReviewDrafts, setTaskReviewDrafts] = useState<Record<string, TaskReviewDraft>>({});
  const eventsQuery = useQuery({
    queryKey: ["events"],
    queryFn: listEvents,
    refetchInterval: 15_000
  });
  const auditLogsQuery = useQuery({
    queryKey: ["audit-logs"],
    queryFn: listAuditLogs,
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
  const modelPoliciesQuery = useQuery({
    queryKey: ["model-policies"],
    queryFn: listModelPolicies,
    refetchInterval: 30_000
  });
  const modelDefinitionsQuery = useQuery({
    queryKey: ["model-definitions"],
    queryFn: listModelDefinitions,
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
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["credential-access-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
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
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["credential-access-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
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
  const memoryRelationApplyMutation = useMutation({
    mutationFn: applyMemoryRelationProposal,
    onSuccess: (result) => {
      setSelectedMemoryItemId(result.source_memory.id);
      setSelectedTimelineTraceId("");
      setSelectedTimelineEventId("");
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const lifecycleRequestMutation = useMutation({
    mutationFn: createAgentLifecycleRequest,
    onSuccess: (request) => {
      setLastLifecycleRequest(request);
      if (request.action === "create_agent") {
        setLifecycleCreateDraft(createLifecycleCreateDraft());
      }
      if (request.action === "update_agent") {
        setLifecycleUpdateDraft({
          ...initialLifecycleUpdateDraft,
          targetAgentId: request.target_agent_id ?? request.proposed_agent?.id ?? ""
        });
      }
      if (request.action === "deactivate_agent") {
        setLifecycleDeactivateDraft(initialLifecycleDeactivateDraft);
      }
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
      void queryClient.invalidateQueries({ queryKey: ["project-timeline"] });
    }
  });
  const decisionMutation = useMutation({
    mutationFn: decideAgentLifecycleRequest,
    onSuccess: (_decision, variables) => {
      const request = lifecycleQuery.data?.find(
        (lifecycleRequest) => lifecycleRequest.id === variables.requestId
      );
      if (request) {
        setLastLifecycleRequest({
          ...request,
          status: variables.status === "approved" ? "applied" : "rejected"
        });
      }
      if (variables.status === "approved") {
        const agentId = request?.proposed_agent?.id ?? request?.target_agent_id;
        if (agentId) {
          setToolCallDraft((draft) => ({
            ...draft,
            agentId
          }));
        }
      }
      void queryClient.invalidateQueries({ queryKey: ["agent-lifecycle-requests"] });
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-world-view"] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
    }
  });
  const agentModelPolicyMutation = useMutation({
    mutationFn: ({
      agentId,
      modelPolicyId
    }: {
      agentId: string;
      modelPolicyId: string | null;
    }) => updateAgentModelPolicy(agentId, modelPolicyId),
    onSuccess: (_agent, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-world-view", variables.agentId] });
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
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
      void queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
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
      return sortApprovalRows([
        ...(lifecycleQuery.data ?? []).map(lifecycleApprovalRow),
        ...(credentialAccessQuery.data ?? []).map(credentialApprovalRow)
      ]);
    }

    return sortApprovalRows(
      approvals.map((approval) => ({
        ...approval,
        createdAtMs: 0,
        source: "sample" as const
      }))
    );
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
      modelPolicyId: null,
      allowedModelIds: [],
      source: "sample" as const
    }));
  }, [agentsQuery.data, agentsQuery.isSuccess]);
  const modelById = useMemo(
    () =>
      new Map(
        (modelDefinitionsQuery.data ?? []).map((modelDefinition) => [
          modelDefinition.id,
          modelDefinition
        ])
      ),
    [modelDefinitionsQuery.data]
  );
  const modelPolicyOptions = modelPoliciesQuery.data ?? [];
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
  const effectiveLifecycleUpdateAgentId =
    lifecycleUpdateDraft.targetAgentId &&
    liveAgentRows.some((agent) => agent.id === lifecycleUpdateDraft.targetAgentId)
      ? lifecycleUpdateDraft.targetAgentId
      : effectiveToolAgentId;
  const selectedLifecycleUpdateAgent = agentsQuery.data?.find(
    (agent) => agent.id === effectiveLifecycleUpdateAgentId
  );
  const activeSoulForLifecycleUpdate =
    effectiveLifecycleUpdateAgentId === effectiveToolAgentId ? worldViewQuery.data?.soul : null;
  const selectedLifecycleDeactivateAgent = agentsQuery.data?.find(
    (agent) => agent.id === lifecycleDeactivateDraft.targetAgentId
  );
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
  const selectedTimelineEventSkips = selectedTimelineEvent
    ? taskSkipsFromPayload(selectedTimelineEvent.payload)
    : [];
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
  const effectiveSelectedConnectorJobId = visibleConnectorJobRows.some(
    (job) => job.id === selectedConnectorJobId
  )
    ? selectedConnectorJobId
    : (visibleConnectorJobRows[0]?.id ?? "");
  const selectedConnectorJob =
    visibleConnectorJobRows.find((job) => job.id === effectiveSelectedConnectorJobId) ?? null;
  const selectedConnectorJobKey = selectedConnectorJob?.id ?? "";
  const selectedConnectorJobRuns = selectedConnectorJobKey
    ? (connectorJobRunsByJobId.get(selectedConnectorJobKey) ?? [])
    : [];
  const selectedConnectorTraceIds = new Set<string>();
  if (selectedConnectorJobKey) {
    for (const run of selectedConnectorJobRuns) {
      selectedConnectorTraceIds.add(traceIdForConnectorRecord(run));
    }
    if (eventsQuery.isSuccess) {
      for (const event of eventsQuery.data) {
        if (payloadString(event.payload, "connector_job_id") === selectedConnectorJobKey) {
          selectedConnectorTraceIds.add(traceIdForEvent(event));
        }
      }
    }
    if (auditLogsQuery.isSuccess) {
      for (const auditLog of auditLogsQuery.data) {
        if (
          (auditLog.target_type === "connector_job" &&
            auditLog.target_id === selectedConnectorJobKey) ||
          payloadString(auditLog.payload, "connector_job_id") === selectedConnectorJobKey
        ) {
          selectedConnectorTraceIds.add(traceIdForConnectorRecord(auditLog));
        }
      }
    }
  }
  const selectedConnectorEvents =
    eventsQuery.isSuccess && selectedConnectorJobKey
      ? eventsQuery.data
          .filter((event) =>
            eventBelongsToConnectorJob(event, selectedConnectorJobKey, selectedConnectorTraceIds)
          )
          .sort(
            (left, right) =>
              new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()
          )
      : [];
  const selectedConnectorAuditLogs =
    auditLogsQuery.isSuccess && selectedConnectorJobKey
      ? auditLogsQuery.data
          .filter((auditLog) =>
            auditBelongsToConnectorJob(
              auditLog,
              selectedConnectorJobKey,
              selectedConnectorTraceIds
            )
          )
          .sort(
            (left, right) =>
              new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
          )
      : [];
  const connectorTraces = new Map<string, ConnectorTraceViewModel>();
  const ensureConnectorTrace = (
    traceId: string,
    timestamp: string
  ): ConnectorTraceViewModel => {
    const timestampValue = new Date(timestamp).getTime();
    const row =
      connectorTraces.get(traceId) ??
      {
        id: traceId,
        label: traceLabel(traceId),
        runCount: 0,
        eventCount: 0,
        auditCount: 0,
        lastTimestamp: 0
      };
    row.lastTimestamp = Math.max(
      row.lastTimestamp,
      Number.isNaN(timestampValue) ? 0 : timestampValue
    );
    connectorTraces.set(traceId, row);
    return row;
  };
  for (const run of selectedConnectorJobRuns) {
    ensureConnectorTrace(traceIdForConnectorRecord(run), run.completed_at).runCount += 1;
  }
  for (const event of selectedConnectorEvents) {
    ensureConnectorTrace(traceIdForEvent(event), event.timestamp).eventCount += 1;
  }
  for (const auditLog of selectedConnectorAuditLogs) {
    ensureConnectorTrace(traceIdForConnectorRecord(auditLog), auditLog.created_at).auditCount += 1;
  }
  const connectorTraceRows = [...connectorTraces.values()].sort(
    (left, right) => right.lastTimestamp - left.lastTimestamp
  );
  const effectiveSelectedConnectorTraceId = connectorTraceRows.some(
    (trace) => trace.id === selectedConnectorTraceId
  )
    ? selectedConnectorTraceId
    : "";
  const visibleSelectedConnectorRuns = effectiveSelectedConnectorTraceId
    ? selectedConnectorJobRuns.filter(
        (run) => traceIdForConnectorRecord(run) === effectiveSelectedConnectorTraceId
      )
    : selectedConnectorJobRuns.slice(0, 6);
  const visibleSelectedConnectorEvents = effectiveSelectedConnectorTraceId
    ? selectedConnectorEvents.filter(
        (event) => traceIdForEvent(event) === effectiveSelectedConnectorTraceId
      )
    : selectedConnectorEvents.slice(0, 6);
  const visibleSelectedConnectorAuditLogs = effectiveSelectedConnectorTraceId
    ? selectedConnectorAuditLogs.filter(
        (auditLog) => traceIdForConnectorRecord(auditLog) === effectiveSelectedConnectorTraceId
      )
    : selectedConnectorAuditLogs.slice(0, 6);
  const connectorJobMode =
    connectorJobsQuery.isLoading || connectorJobRunsQuery.isLoading || auditLogsQuery.isLoading
      ? "syncing"
      : connectorJobsQuery.isError || connectorJobRunsQuery.isError || auditLogsQuery.isError
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
        : "State-service connector jobs or audit logs unavailable";
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
  const lifecycleAgentId = lifecycleCreateDraft.agentId.trim();
  const lifecycleDivision = lifecycleCreateDraft.division.trim();
  const canCreateLifecycleRequest =
    lifecycleAgentId.length > 0 &&
    lifecycleCreateDraft.name.trim().length > 0 &&
    lifecycleCreateDraft.role.trim().length > 0 &&
    lifecycleDivision.length > 0 &&
    lifecycleCreateDraft.reason.trim().length > 0 &&
    lifecycleCreateDraft.soulIdentity.trim().length > 0 &&
    lifecycleCreateDraft.soulMission.trim().length > 0 &&
    !lifecycleRequestMutation.isPending;
  const updateLifecycleCreateDraft = (
    field: keyof LifecycleCreateDraft,
    value: string
  ) => {
    setLifecycleCreateDraft((draft) => ({
      ...draft,
      [field]: value
    }));
  };
  const handleLifecycleCreateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canCreateLifecycleRequest) {
      return;
    }
    const resolvedDraft = resolveLifecycleCreateDraft(lifecycleCreateDraft);

    lifecycleRequestMutation.mutate({
      id: `lifecycle-create-${resolvedDraft.agentId}`,
      action: "create_agent",
      requested_by_type: "user",
      requested_by_id: "local-user",
      reason: resolvedDraft.reason,
      proposed_agent: {
        id: resolvedDraft.agentId,
        name: resolvedDraft.name,
        role: resolvedDraft.role,
        division: resolvedDraft.division,
        manager_id: resolvedDraft.managerId || null,
        capabilities: {
          skills: ["task.breakdown"],
          tools: ["event.emit"],
          models: ["deepseek/deepseek-v4-flash"]
        },
        permissions: {
          can_read_scopes: [
            `agent:${resolvedDraft.agentId}`,
            `division:${resolvedDraft.division}`
          ],
          can_write_scopes: [`agent:${resolvedDraft.agentId}`],
          allowed_tools: ["event.emit"],
          denied_tools: ["credential.read", "email.send", "web.fetch"]
        },
        model: "deepseek/deepseek-v4-flash",
        model_policy_id: "policy-openrouter-deepseek-v4-flash",
        allowed_model_ids: ["deepseek/deepseek-v4-flash"],
        created_by: "local-user"
      },
      proposed_soul: {
        id: soulIdForAgent(resolvedDraft.agentId),
        agent_id: resolvedDraft.agentId,
        version: 1,
        identity: resolvedDraft.soulIdentity,
        mission: resolvedDraft.soulMission,
        responsibilities: [
          "Operate inside assigned division scope",
          "Report lifecycle-impacting changes through approvals"
        ],
        operating_principles: [
          "Keep decisions auditable",
          "Escalate unclear scope before external action"
        ],
        boundaries: [
          "Do not request credentials without task context",
          "Do not contact external services without an approved connector scope"
        ],
        escalation_rules: [
          "Escalate missing permission or service ownership to the manager agent"
        ],
        communication_style: "Clear, concise, and auditable.",
        created_by: resolvedDraft.managerId || "local-user",
        active: true
      },
      requires_human_approval: true
    });
  };
  const effectiveLifecycleUpdateRole =
    lifecycleUpdateDraft.role.trim() || selectedLifecycleUpdateAgent?.role || "";
  const effectiveLifecycleUpdateDivision =
    lifecycleUpdateDraft.division.trim() || selectedLifecycleUpdateAgent?.division || "";
  const effectiveLifecycleUpdateSoulIdentity =
    lifecycleUpdateDraft.soulIdentity.trim() ||
    activeSoulForLifecycleUpdate?.identity ||
    "Updated AI employee soul.";
  const effectiveLifecycleUpdateSoulMission =
    lifecycleUpdateDraft.soulMission.trim() ||
    activeSoulForLifecycleUpdate?.mission ||
    "Operate with the updated role and lifecycle-governed constraints.";
  const canUpdateLifecycleRequest =
    !!selectedLifecycleUpdateAgent &&
    effectiveLifecycleUpdateRole.length > 0 &&
    effectiveLifecycleUpdateDivision.length > 0 &&
    lifecycleUpdateDraft.reason.trim().length > 0 &&
    effectiveLifecycleUpdateSoulIdentity.length > 0 &&
    effectiveLifecycleUpdateSoulMission.length > 0 &&
    !lifecycleRequestMutation.isPending;
  const updateLifecycleUpdateDraft = (
    field: keyof LifecycleUpdateDraft,
    value: string
  ) => {
    setLifecycleUpdateDraft((draft) => ({
      ...draft,
      [field]: value
    }));
  };
  const handleLifecycleUpdateTargetChange = (agentId: string) => {
    setLifecycleUpdateDraft({
      ...initialLifecycleUpdateDraft,
      targetAgentId: agentId
    });
    setToolCallDraft((draft) => ({
      ...draft,
      agentId
    }));
  };
  const handleLifecycleUpdateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedLifecycleUpdateAgent || !canUpdateLifecycleRequest) {
      return;
    }

    const nextSoulVersion = (activeSoulForLifecycleUpdate?.version ?? 0) + 1;
    lifecycleRequestMutation.mutate({
      id: lifecycleUpdateRequestId(selectedLifecycleUpdateAgent.id),
      action: "update_agent",
      requested_by_type: "user",
      requested_by_id: "local-user",
      reason: lifecycleUpdateDraft.reason.trim(),
      target_agent_id: selectedLifecycleUpdateAgent.id,
      proposed_agent: {
        ...selectedLifecycleUpdateAgent,
        role: effectiveLifecycleUpdateRole,
        division: effectiveLifecycleUpdateDivision
      },
      proposed_soul: {
        id: soulUpdateIdForAgent(selectedLifecycleUpdateAgent.id, nextSoulVersion),
        agent_id: selectedLifecycleUpdateAgent.id,
        version: nextSoulVersion,
        identity: effectiveLifecycleUpdateSoulIdentity,
        mission: effectiveLifecycleUpdateSoulMission,
        responsibilities: activeSoulForLifecycleUpdate?.responsibilities ?? [
          "Operate inside assigned division scope"
        ],
        operating_principles: activeSoulForLifecycleUpdate?.operating_principles ?? [
          "Keep decisions auditable"
        ],
        boundaries: activeSoulForLifecycleUpdate?.boundaries ?? [
          "Do not execute external actions without an approved connector scope"
        ],
        escalation_rules: activeSoulForLifecycleUpdate?.escalation_rules ?? [
          "Escalate missing permissions to the manager agent"
        ],
        communication_style:
          activeSoulForLifecycleUpdate?.communication_style ??
          "Clear, concise, and auditable.",
        created_by: selectedLifecycleUpdateAgent.manager_id ?? "local-user",
        active: true
      },
      requires_human_approval: true
    });
  };
  const canDeactivateLifecycleRequest =
    !!selectedLifecycleDeactivateAgent &&
    selectedLifecycleDeactivateAgent.status !== "inactive" &&
    lifecycleDeactivateDraft.reason.trim().length > 0 &&
    !lifecycleRequestMutation.isPending;
  const updateLifecycleDeactivateDraft = (
    field: keyof LifecycleDeactivateDraft,
    value: string
  ) => {
    setLifecycleDeactivateDraft((draft) => ({
      ...draft,
      [field]: value
    }));
  };
  const handleLifecycleDeactivateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedLifecycleDeactivateAgent || !canDeactivateLifecycleRequest) {
      return;
    }

    lifecycleRequestMutation.mutate({
      id: lifecycleDeactivateRequestId(selectedLifecycleDeactivateAgent.id),
      action: "deactivate_agent",
      requested_by_type: "user",
      requested_by_id: "local-user",
      reason: lifecycleDeactivateDraft.reason.trim(),
      target_agent_id: selectedLifecycleDeactivateAgent.id,
      requires_human_approval: true
    });
  };
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
                        const isRelationProposal = isMemoryRelationProposal(memoryItem);
                        const relationSourceId = memoryRelationSourceId(memoryItem);
                        const relationRelatedIds = memoryRelationRelatedIds(memoryItem);
                        const isRelationApplied = memoryRelationApplied(memoryItem);
                        const isApplyingRelation =
                          memoryRelationApplyMutation.isPending &&
                          memoryRelationApplyMutation.variables?.proposalId === memoryItem.id;
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
                                {isRelationProposal ? (
                                  <span className="flex items-center gap-1 rounded-md bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info ring-1 ring-info/15">
                                    <GitBranch size={11} />
                                    relation
                                  </span>
                                ) : null}
                                <span className="max-w-full truncate text-xs text-muted">
                                  {memoryItem.id} / {memoryItem.agent_id ?? "agent"} /{" "}
                                  {memoryItem.scope}
                                </span>
                              </div>
                              <BalancedText className="mt-2 text-sm text-muted" font="400 13px Inter Variable" lineHeight={18}>
                                {memoryItem.content}
                              </BalancedText>
                              {isRelationProposal ? (
                                <div className="mt-2 grid gap-1 rounded-md bg-slate-50 px-2 py-2 text-[11px] text-muted ring-1 ring-border">
                                  <span className="truncate">
                                    source {relationSourceId ?? "unknown"}
                                  </span>
                                  <span className="truncate">
                                    targets{" "}
                                    {relationRelatedIds.length > 0
                                      ? relationRelatedIds.join(", ")
                                      : "none"}
                                  </span>
                                  {isRelationApplied ? (
                                    <span className="font-medium text-ok">applied</span>
                                  ) : null}
                                </div>
                              ) : null}
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
                              {isRelationProposal ? (
                                <button
                                  className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-info transition enabled:hover:border-info/40 enabled:hover:bg-info-soft disabled:cursor-not-allowed disabled:opacity-40"
                                  disabled={
                                    memoryItem.status !== "approved" ||
                                    isRelationApplied ||
                                    isApplyingRelation ||
                                    memoryRelationApplyMutation.isPending
                                  }
                                  type="button"
                                  onClick={() =>
                                    memoryRelationApplyMutation.mutate({
                                      proposalId: memoryItem.id
                                    })
                                  }
                                >
                                  <GitBranch size={13} />
                                  <span>
                                    {isApplyingRelation
                                      ? "Applying"
                                      : isRelationApplied
                                        ? "Applied"
                                        : "Apply"}
                                  </span>
                                </button>
                              ) : null}
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
                    {memoryRelationApplyMutation.isError ? (
                      <p className="text-xs font-medium text-risk">
                        {memoryRelationApplyMutation.error instanceof Error
                          ? memoryRelationApplyMutation.error.message
                          : "Memory relation apply failed."}
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
                    {selectedProjectLastTaskRun.lifecycle_requests_created.length > 0 ? (
                      <div className="grid gap-2 rounded-md border border-accent/15 bg-accent-soft/40 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-[11px] font-semibold uppercase text-accent">
                            Lifecycle proposals created
                          </p>
                          <span className="rounded-md bg-white px-2 py-0.5 text-[11px] font-semibold text-accent ring-1 ring-accent/15">
                            {selectedProjectLastTaskRun.lifecycle_requests_created.length}
                          </span>
                        </div>
                        <div className="grid gap-2 xl:grid-cols-2">
                          {selectedProjectLastTaskRun.lifecycle_requests_created.map((request) => (
                            <article
                              key={request.id}
                              className="min-w-0 rounded-md border border-border bg-white p-2"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-muted ring-1 ring-border">
                                  {request.action}
                                </span>
                                <span
                                  className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${approvalStatusClass[request.status]}`}
                                >
                                  {request.status}
                                </span>
                              </div>
                              <p className="mt-1 truncate text-xs font-medium text-ink">
                                {lifecycleRequestTarget(request)}
                              </p>
                              <p className="mt-0.5 truncate text-[11px] text-muted">
                                {request.id} / {lifecycleRequestDetail(request)}
                              </p>
                              <BalancedText className="mt-1 text-[11px] text-muted" font="400 11px Inter Variable" lineHeight={15}>
                                {request.reason}
                              </BalancedText>
                            </article>
                          ))}
                        </div>
                      </div>
                    ) : null}
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
                {projectTimelineTasks.map((task) => {
                  const taskSkips = taskSkipRecordsForTask(projectTimelineQuery.data, task.id);
                  return (
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
                      {taskSkips.length > 0 ? (
                        <div className="mt-3 grid gap-1.5 rounded-md border border-warn/25 bg-warn-soft p-2">
                          {taskSkips.slice(0, 2).map((skip) => (
                            <button
                              key={`${skip.event_id}-${skip.category}`}
                              className="min-w-0 text-left"
                              type="button"
                              onClick={() => {
                                setFocusedTimelineTaskId(task.id);
                                setSelectedTimelineTraceId(skip.trace_id ?? "");
                                setSelectedTimelineEventId(skip.event_id);
                              }}
                            >
                              <p className="truncate text-[11px] font-semibold text-warn">
                                skipped {skip.category} / {traceLabel(skip.trace_id ?? "no-trace")}
                              </p>
                              <p className="mt-0.5 text-[11px] text-muted">
                                {skip.reason}
                              </p>
                            </button>
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
                  );
                })}
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
                      {selectedTimelineEventSkips.length > 0 ? (
                        <div className="mt-2 grid gap-1.5 rounded-md border border-warn/25 bg-warn-soft p-2">
                          {selectedTimelineEventSkips.map((skip) => (
                            <div key={`${skip.task_id}-${skip.category}`}>
                              <p className="truncate text-[11px] font-semibold text-warn">
                                {skip.task_id} / {skip.category}
                              </p>
                              <p className="mt-0.5 text-[11px] text-muted">{skip.reason}</p>
                            </div>
                          ))}
                        </div>
                      ) : null}
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
                      {run.lifecycle_requests_created.length > 0 ? (
                        <div className="grid gap-1.5 rounded-md border border-accent/15 bg-white p-2">
                          <p className="text-[11px] font-semibold text-accent">
                            lifecycle proposals {run.lifecycle_requests_created.length}
                          </p>
                          {run.lifecycle_requests_created.slice(0, 3).map((request) => (
                            <div key={request.id} className="min-w-0">
                              <p className="truncate text-[11px] font-medium text-ink">
                                {request.action} / {lifecycleRequestTarget(request)}
                              </p>
                              <p className="truncate text-[11px] text-muted">
                                {request.id} / {request.status}
                              </p>
                            </div>
                          ))}
                        </div>
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
                const isSelectedConnectorJob = job.id === effectiveSelectedConnectorJobId;
                return (
                  <article
                    key={job.id}
                    className={`grid gap-3 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_190px_210px] ${
                      isSelectedConnectorJob ? "bg-info-soft/30" : ""
                    }`}
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
                        <button
                          className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-medium text-muted transition hover:border-info/40 hover:bg-info-soft hover:text-info"
                          title="Inspect connector job history"
                          type="button"
                          onClick={() => {
                            setSelectedConnectorJobId(job.id);
                            setSelectedConnectorTraceId("");
                          }}
                        >
                          <FileText size={13} />
                          <span>{isSelectedConnectorJob ? "Selected" : "Details"}</span>
                        </button>
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
            {selectedConnectorJob ? (
              <div className="border-t border-border px-4 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                      Historique du job
                    </p>
                    <h3 className="mt-1 truncate text-sm font-semibold text-ink">
                      {selectedConnectorJob.id}
                    </h3>
                    <p className="mt-1 text-xs text-muted">
                      {selectedConnectorJobRuns.length} runs / {selectedConnectorEvents.length}{" "}
                      events / {selectedConnectorAuditLogs.length} audits
                    </p>
                  </div>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-muted ring-1 ring-border">
                    {effectiveSelectedConnectorTraceId
                      ? traceLabel(effectiveSelectedConnectorTraceId)
                      : "all traces"}
                  </span>
                </div>

                {connectorTraceRows.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <button
                      className={`h-7 rounded-md px-2 text-[11px] font-medium ring-1 transition ${
                        effectiveSelectedConnectorTraceId
                          ? "bg-white text-muted ring-border hover:bg-slate-50"
                          : "bg-info-soft text-info ring-info/20"
                      }`}
                      type="button"
                      onClick={() => setSelectedConnectorTraceId("")}
                    >
                      All
                    </button>
                    {connectorTraceRows.slice(0, 8).map((trace) => (
                      <button
                        key={trace.id}
                        className={`h-7 max-w-full truncate rounded-md px-2 text-[11px] font-medium ring-1 transition ${
                          trace.id === effectiveSelectedConnectorTraceId
                            ? "bg-info-soft text-info ring-info/20"
                            : "bg-white text-muted ring-border hover:bg-slate-50"
                        }`}
                        title={`${trace.runCount} runs / ${trace.eventCount} events / ${trace.auditCount} audits`}
                        type="button"
                        onClick={() =>
                          setSelectedConnectorTraceId(
                            trace.id === effectiveSelectedConnectorTraceId ? "" : trace.id
                          )
                        }
                      >
                        {trace.label}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-muted">
                    Aucun trace_id encore rattaché à ce connector job.
                  </p>
                )}

                <div className="mt-4 grid gap-4 xl:grid-cols-3">
                  <div className="min-w-0">
                    <div className="flex items-center justify-between gap-2 border-b border-border pb-2">
                      <p className="text-xs font-semibold text-ink">Runs</p>
                      <span className="text-[11px] text-muted">
                        {visibleSelectedConnectorRuns.length}/{selectedConnectorJobRuns.length}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-3">
                      {visibleSelectedConnectorRuns.length === 0 ? (
                        <p className="text-xs text-muted">Aucun run enregistré.</p>
                      ) : null}
                      {visibleSelectedConnectorRuns.map((run) => (
                        <div key={run.id} className="min-w-0 rounded-md bg-slate-50 p-3 ring-1 ring-border/70">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${
                                connectorJobRunStatusClass[run.status] ??
                                connectorJobRunStatusClass.skipped
                              }`}
                            >
                              {run.status}
                            </span>
                            <span className="min-w-0 truncate text-[11px] text-muted">
                              {formatRelativeTimestamp(run.completed_at)}
                            </span>
                          </div>
                          <p className="mt-2 truncate text-[11px] text-muted">
                            {run.id} / {traceLabel(traceIdForConnectorRecord(run))}
                          </p>
                          <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-white p-2 text-[11px] leading-relaxed text-muted ring-1 ring-border">
                            {formatPayload({ output: run.output, error: run.error })}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center justify-between gap-2 border-b border-border pb-2">
                      <p className="text-xs font-semibold text-ink">Events</p>
                      <span className="text-[11px] text-muted">
                        {visibleSelectedConnectorEvents.length}/{selectedConnectorEvents.length}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-3">
                      {visibleSelectedConnectorEvents.length === 0 ? (
                        <p className="text-xs text-muted">Aucun event lié.</p>
                      ) : null}
                      {visibleSelectedConnectorEvents.map((event) => (
                        <div key={event.id} className="min-w-0 rounded-md bg-slate-50 p-3 ring-1 ring-border/70">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${toneSurface[eventTone(event)]}`}
                            >
                              {event.type}
                            </span>
                            <span className="min-w-0 truncate text-[11px] text-muted">
                              {formatRelativeTimestamp(event.timestamp)}
                            </span>
                          </div>
                          <p className="mt-2 truncate text-[11px] text-muted">
                            {event.id} / {traceLabel(traceIdForEvent(event))}
                          </p>
                          <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-white p-2 text-[11px] leading-relaxed text-muted ring-1 ring-border">
                            {formatPayload(event.payload)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center justify-between gap-2 border-b border-border pb-2">
                      <p className="text-xs font-semibold text-ink">Audits</p>
                      <span className="text-[11px] text-muted">
                        {visibleSelectedConnectorAuditLogs.length}/
                        {selectedConnectorAuditLogs.length}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-3">
                      {visibleSelectedConnectorAuditLogs.length === 0 ? (
                        <p className="text-xs text-muted">Aucun audit lié.</p>
                      ) : null}
                      {visibleSelectedConnectorAuditLogs.map((auditLog) => (
                        <div
                          key={auditLog.id}
                          className="min-w-0 rounded-md bg-slate-50 p-3 ring-1 ring-border/70"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-md bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent ring-1 ring-accent/15">
                              {auditLog.action}
                            </span>
                            <span className="min-w-0 truncate text-[11px] text-muted">
                              {formatRelativeTimestamp(auditLog.created_at)}
                            </span>
                          </div>
                          <p className="mt-2 truncate text-[11px] text-muted">
                            {auditLog.actor_type}:{auditLog.actor_id} /{" "}
                            {traceLabel(traceIdForConnectorRecord(auditLog))}
                          </p>
                          <p className="mt-1 truncate text-[11px] text-muted">
                            {auditLog.target_type}:{auditLog.target_id}
                          </p>
                          <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-white p-2 text-[11px] leading-relaxed text-muted ring-1 ring-border">
                            {formatPayload(auditLog.payload)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
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
                    : auditLogsQuery.error instanceof Error
                      ? auditLogsQuery.error.message
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
                    <div className="mt-3 grid gap-2">
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="font-semibold uppercase text-muted">
                          Model policy
                        </span>
                        <span className="min-w-0 truncate text-muted">
                          {modelPolicyShortLabel(agent.modelPolicyId)}
                        </span>
                      </div>
                      <select
                        className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent disabled:bg-slate-100 disabled:text-muted"
                        aria-label={`Model policy for ${agent.name}`}
                        value={agent.modelPolicyId ?? ""}
                        disabled={
                          agent.source !== "api" ||
                          modelPoliciesQuery.isLoading ||
                          agentModelPolicyMutation.isPending
                        }
                        onChange={(event) =>
                          agentModelPolicyMutation.mutate({
                            agentId: agent.id,
                            modelPolicyId: event.target.value || null
                          })
                        }
                      >
                        <option value="">No policy</option>
                        {modelPolicyOptions.map((policy) => (
                          <option key={policy.id} value={policy.id}>
                            {modelPolicyLabel(policy, modelById)}
                          </option>
                        ))}
                      </select>
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
                  {worldViewQuery.data.soul ? (
                    <div className="grid gap-1.5">
                      <p className="text-[11px] font-semibold uppercase text-muted">
                        Active soul
                      </p>
                      <p className="text-xs font-medium text-ink">
                        {worldViewQuery.data.soul.identity}
                      </p>
                      <BalancedText className="text-xs text-muted" font="400 12px Inter Variable" lineHeight={16}>
                        {worldViewQuery.data.soul.mission}
                      </BalancedText>
                    </div>
                  ) : null}
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
            <form className="grid gap-3 border-b border-border px-4 py-3" onSubmit={handleLifecycleCreateSubmit}>
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle agent id"
                  value={lifecycleCreateDraft.agentId}
                  onChange={(event) =>
                    updateLifecycleCreateDraft("agentId", event.target.value)
                  }
                />
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle agent name"
                  value={lifecycleCreateDraft.name}
                  onChange={(event) => updateLifecycleCreateDraft("name", event.target.value)}
                />
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle agent role"
                  value={lifecycleCreateDraft.role}
                  onChange={(event) => updateLifecycleCreateDraft("role", event.target.value)}
                />
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle agent division"
                  value={lifecycleCreateDraft.division}
                  onChange={(event) =>
                    updateLifecycleCreateDraft("division", event.target.value)
                  }
                />
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle agent manager"
                  value={lifecycleCreateDraft.managerId}
                  onChange={(event) =>
                    updateLifecycleCreateDraft("managerId", event.target.value)
                  }
                />
              </div>
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle request reason"
                value={lifecycleCreateDraft.reason}
                onChange={(event) => updateLifecycleCreateDraft("reason", event.target.value)}
              />
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle soul identity"
                value={lifecycleCreateDraft.soulIdentity}
                onChange={(event) =>
                  updateLifecycleCreateDraft("soulIdentity", event.target.value)
                }
              />
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle soul mission"
                value={lifecycleCreateDraft.soulMission}
                onChange={(event) =>
                  updateLifecycleCreateDraft("soulMission", event.target.value)
                }
              />
              <div className="flex items-center justify-between gap-3">
                <p className="min-w-0 truncate text-xs text-muted">
                  {lastLifecycleRequest
                    ? `${lastLifecycleRequest.id} / ${lastLifecycleRequest.status}`
                    : soulIdForAgent(lifecycleAgentId)}
                </p>
                <button
                  className="flex h-9 shrink-0 items-center justify-center gap-2 rounded-md bg-ink px-3 text-xs font-medium text-white transition enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!canCreateLifecycleRequest}
                  type="submit"
                >
                  <UserRoundPlus size={14} />
                  <span>{lifecycleRequestMutation.isPending ? "Creating..." : "Request agent"}</span>
                </button>
              </div>
              {lifecycleRequestMutation.isError ? (
                <p className="text-xs font-medium text-risk">
                  {lifecycleRequestMutation.error instanceof Error
                    ? lifecycleRequestMutation.error.message
                    : "Lifecycle request failed"}
                </p>
              ) : null}
            </form>
            <form className="grid gap-3 border-b border-border px-4 py-3" onSubmit={handleLifecycleUpdateSubmit}>
              <select
                className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle update target"
                value={effectiveLifecycleUpdateAgentId}
                onChange={(event) => handleLifecycleUpdateTargetChange(event.target.value)}
              >
                {liveAgentRows.length === 0 ? <option value="">No live agent</option> : null}
                {liveAgentRows.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </select>
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle update role"
                  value={effectiveLifecycleUpdateRole}
                  onChange={(event) =>
                    updateLifecycleUpdateDraft("role", event.target.value)
                  }
                />
                <input
                  className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-accent"
                  aria-label="Lifecycle update division"
                  value={effectiveLifecycleUpdateDivision}
                  onChange={(event) =>
                    updateLifecycleUpdateDraft("division", event.target.value)
                  }
                />
              </div>
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle update reason"
                value={lifecycleUpdateDraft.reason}
                onChange={(event) => updateLifecycleUpdateDraft("reason", event.target.value)}
              />
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle update soul identity"
                value={effectiveLifecycleUpdateSoulIdentity}
                onChange={(event) =>
                  updateLifecycleUpdateDraft("soulIdentity", event.target.value)
                }
              />
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-accent"
                aria-label="Lifecycle update soul mission"
                value={effectiveLifecycleUpdateSoulMission}
                onChange={(event) =>
                  updateLifecycleUpdateDraft("soulMission", event.target.value)
                }
              />
              <div className="flex items-center justify-between gap-3">
                <p className="min-w-0 truncate text-xs text-muted">
                  {selectedLifecycleUpdateAgent
                    ? `${selectedLifecycleUpdateAgent.id} / v${(activeSoulForLifecycleUpdate?.version ?? 0) + 1}`
                    : "No update target"}
                </p>
                <button
                  className="flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-border bg-white px-3 text-xs font-medium text-ink transition enabled:hover:border-accent/40 enabled:hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!canUpdateLifecycleRequest}
                  type="submit"
                >
                  <PencilLine size={14} />
                  <span>{lifecycleRequestMutation.isPending ? "Creating..." : "Request update"}</span>
                </button>
              </div>
              {lifecycleRequestMutation.isError ? (
                <p className="text-xs font-medium text-risk">
                  {lifecycleRequestMutation.error instanceof Error
                    ? lifecycleRequestMutation.error.message
                    : "Lifecycle request failed"}
                </p>
              ) : null}
            </form>
            <form className="grid gap-3 border-b border-border px-4 py-3" onSubmit={handleLifecycleDeactivateSubmit}>
              <select
                className="h-9 min-w-0 rounded-md border border-border bg-white px-2 text-xs text-ink outline-none transition focus:border-risk"
                aria-label="Lifecycle deactivate target"
                value={lifecycleDeactivateDraft.targetAgentId}
                onChange={(event) =>
                  updateLifecycleDeactivateDraft("targetAgentId", event.target.value)
                }
              >
                <option value="">Select agent to deactivate</option>
                {liveAgentRows
                  .filter((agent) => agent.status !== "inactive")
                  .map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
              </select>
              <textarea
                className="min-h-16 resize-y rounded-md border border-border bg-white px-2 py-2 text-xs text-ink outline-none transition focus:border-risk"
                aria-label="Lifecycle deactivate reason"
                value={lifecycleDeactivateDraft.reason}
                onChange={(event) =>
                  updateLifecycleDeactivateDraft("reason", event.target.value)
                }
              />
              <div className="flex items-center justify-between gap-3">
                <p className="min-w-0 truncate text-xs text-muted">
                  {selectedLifecycleDeactivateAgent
                    ? `${selectedLifecycleDeactivateAgent.id} / ${selectedLifecycleDeactivateAgent.status}`
                    : "No deactivate target"}
                </p>
                <button
                  className="flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-risk/30 bg-white px-3 text-xs font-medium text-risk transition enabled:hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!canDeactivateLifecycleRequest}
                  type="submit"
                >
                  <UserRoundX size={14} />
                  <span>{lifecycleRequestMutation.isPending ? "Creating..." : "Request deactivate"}</span>
                </button>
              </div>
              {lifecycleRequestMutation.isError ? (
                <p className="text-xs font-medium text-risk">
                  {lifecycleRequestMutation.error instanceof Error
                    ? lifecycleRequestMutation.error.message
                    : "Lifecycle request failed"}
                </p>
              ) : null}
            </form>
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
                      {event.detail ? (
                        <p className="mt-1 truncate text-[11px] text-warn">{event.detail}</p>
                      ) : null}
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
