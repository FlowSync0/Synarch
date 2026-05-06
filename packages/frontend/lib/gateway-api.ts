import type { EventRecord, ProjectRecord } from "./state-service-api";

export type TaskStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "blocked"
  | "failed"
  | "needs_review";

export type GoalPriority = "low" | "medium" | "high" | "critical";

export type GoalEnvelope = {
  goal: string;
  priority: GoalPriority;
  context?: Record<string, unknown>;
  constraints: string[];
  requester: string;
};

export type TaskRecord = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  assigned_agent_id: string;
  depends_on: string[];
  required_tools: string[];
  acceptance_criteria: string[];
  parent_task_id?: string | null;
  sequence: number;
  result?: Record<string, unknown> | null;
  attempt_count: number;
  max_attempts: number;
  lease_owner_id?: string | null;
  lease_expires_at?: string | null;
  last_heartbeat_at?: string | null;
  retry_after_at?: string | null;
  dead_letter_reason?: string | null;
  dead_lettered_at?: string | null;
  created_at: string;
};

export type GoalProjectRecord = {
  id: string;
  title: string;
  goal: string;
  status: TaskStatus;
  priority: GoalPriority;
  owner_agent_id: string;
  created_at: string;
};

export type GoalSubmissionResult = {
  trace_id: string;
  routing_decision: unknown;
  project: GoalProjectRecord;
  workspace: unknown;
  assignments: unknown[];
  tasks: TaskRecord[];
  events: unknown[];
  complexity_assessment?: unknown | null;
};

export type TaskReviewAction = "retry" | "cancel" | "update";

export type TaskReviewDecision = {
  action: TaskReviewAction;
  reason: string;
  title?: string;
  description?: string;
  assigned_agent_id?: string;
  acceptance_criteria?: string[];
  max_attempts?: number;
  retry_after_at?: string | null;
};

export type TaskReviewResult = {
  task: TaskRecord;
  event: unknown;
  audit_log?: unknown | null;
};

export type ToolCallRequest = {
  agent_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  reason: string;
  service_id?: string | null;
  project_id?: string | null;
  task_id?: string | null;
  trace_id?: string | null;
};

export type ToolResult = {
  tool_name: string;
  status: TaskStatus;
  output: Record<string, unknown>;
  error?: string | null;
};

export type ToolAdapterManifest = {
  tool_name: string;
  adapter: string;
  required_arguments: string[];
  optional_arguments: string[];
  credential_scopes: string[];
  risk_level: "low" | "medium" | "high";
  requires_credentials: boolean;
  network_access: boolean;
  audit_required: boolean;
};

export type ToolCredentialStatus = {
  agent_id: string;
  service_id: string;
  tool_name: string;
  status: "not_required" | "ready" | "missing_scopes";
  required_scopes: string[];
  available_scopes: string[];
  missing_scopes: string[];
};

export type CostRecord = {
  id: string;
  project_id?: string | null;
  task_id?: string | null;
  agent_id?: string | null;
  provider_id: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
  currency: string;
  trace_id?: string | null;
  created_at: string;
};

export type MemoryStatus = "proposed" | "approved" | "rejected";

export type MemoryItem = {
  id: string;
  scope: string;
  content: string;
  status: MemoryStatus;
  agent_id?: string | null;
  project_id?: string | null;
  embedding?: number[] | null;
  created_at: string;
  expires_at?: string | null;
};

export type MemoryContext = {
  agent_id: string;
  project_id?: string | null;
  token_budget: number;
  allowed_scopes: string[];
  items: MemoryItem[];
  summary: string;
  tokens_used: number;
};

export type ProjectTimeline = {
  project_id: string;
  project: ProjectRecord;
  tasks: TaskRecord[];
  events: EventRecord[];
  cost_records: CostRecord[];
  audit_logs: unknown[];
  memory_items: MemoryItem[];
  total_cost: number;
  currency: string;
};

export type RunReadyRequest = {
  projectId: string;
  maxTasks: number;
};

export type TaskRunBatchResult = {
  trace_id: string;
  max_tasks: number;
  project_id?: string | null;
  stop_reason: string;
  runs: TaskRunResult[];
  skipped_task_ids: string[];
  lease_recovery?: unknown | null;
  scheduler_event?: unknown | null;
  scheduler_audit_log?: unknown | null;
};

export type TaskRunResult = {
  trace_id: string;
  task: TaskRecord;
  project?: ProjectRecord | null;
  world_view: unknown;
  memory_context: MemoryContext;
  agent_result: {
    agent_id: string;
    task_id: string;
    status: TaskStatus;
    summary: string;
    tool_calls_requested?: ToolCallRequest[];
    tool_results?: ToolResult[];
  };
  model_call_events: EventRecord[];
  created_sub_tasks: TaskRecord[];
  sub_task_events: EventRecord[];
  memory_events: EventRecord[];
  tool_results: ToolResult[];
  cost_records: CostRecord[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseJsonResponse<ResponseT>(response: Response): Promise<ResponseT> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String(payload.detail)
        : response.statusText;
    throw new ApiError(detail, response.status);
  }
  return payload as ResponseT;
}

export async function listTaskReviewQueue(): Promise<TaskRecord[]> {
  const response = await fetch("/api/gateway/tasks/review-queue", {
    cache: "no-store"
  });
  return parseJsonResponse<TaskRecord[]>(response);
}

export async function submitGoal(envelope: GoalEnvelope): Promise<GoalSubmissionResult> {
  const response = await fetch("/api/gateway/goals/submit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Synarch-Actor-Type": "user",
      "X-Synarch-Actor-Id": envelope.requester,
      "X-Synarch-Trace-Id": `trace_frontend_goal_${Date.now()}`
    },
    body: JSON.stringify(envelope)
  });
  return parseJsonResponse<GoalSubmissionResult>(response);
}

export async function runReadyTasks({
  projectId,
  maxTasks
}: RunReadyRequest): Promise<TaskRunBatchResult> {
  const params = new URLSearchParams({
    project_id: projectId,
    max_tasks: String(maxTasks)
  });
  const response = await fetch(`/api/gateway/tasks/run-ready?${params.toString()}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Synarch-Actor-Type": "user",
      "X-Synarch-Actor-Id": "local-user",
      "X-Synarch-Trace-Id": `trace_frontend_run_ready_${Date.now()}`
    }
  });
  return parseJsonResponse<TaskRunBatchResult>(response);
}

export async function getProjectTimeline(projectId: string): Promise<ProjectTimeline> {
  const response = await fetch(
    `/api/gateway/projects/${encodeURIComponent(projectId)}/timeline`,
    {
      cache: "no-store"
    }
  );
  return parseJsonResponse<ProjectTimeline>(response);
}

export async function runTask(taskId: string): Promise<TaskRunResult> {
  const response = await fetch(`/api/gateway/tasks/${encodeURIComponent(taskId)}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Synarch-Actor-Type": "user",
      "X-Synarch-Actor-Id": "local-user",
      "X-Synarch-Trace-Id": `trace_frontend_task_run_${Date.now()}`
    }
  });
  return parseJsonResponse<TaskRunResult>(response);
}

export async function callTool(toolCall: ToolCallRequest): Promise<ToolResult> {
  const response = await fetch("/api/gateway/tools/call", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Synarch-Actor-Type": "user",
      "X-Synarch-Actor-Id": "local-user",
      "X-Synarch-Trace-Id": toolCall.trace_id ?? `trace_frontend_tool_gate_${Date.now()}`
    },
    body: JSON.stringify(toolCall)
  });
  return parseJsonResponse<ToolResult>(response);
}

export async function listToolAdapterManifests(): Promise<ToolAdapterManifest[]> {
  const response = await fetch("/api/gateway/tools/registry", {
    cache: "no-store"
  });
  const payload = await parseJsonResponse<{ tools: ToolAdapterManifest[] }>(response);
  return payload.tools;
}

export async function listToolCredentialStatuses(
  agentId: string
): Promise<ToolCredentialStatus[]> {
  const params = new URLSearchParams({ agent_id: agentId });
  const response = await fetch(`/api/gateway/tools/credential-status?${params}`, {
    cache: "no-store"
  });
  const payload = await parseJsonResponse<{
    credential_statuses: ToolCredentialStatus[];
  }>(response);
  return payload.credential_statuses;
}

export async function updateMemoryStatus({
  itemId,
  status
}: {
  itemId: string;
  status: MemoryStatus;
}): Promise<MemoryItem> {
  const response = await fetch(
    `/api/gateway/memory-items/${encodeURIComponent(itemId)}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-Synarch-Actor-Type": "user",
        "X-Synarch-Actor-Id": "local-user",
        "X-Synarch-Trace-Id": `trace_frontend_memory_review_${Date.now()}`
      },
      body: JSON.stringify({ status })
    }
  );
  return parseJsonResponse<MemoryItem>(response);
}

export async function decideTaskReview({
  taskId,
  decision
}: {
  taskId: string;
  decision: TaskReviewDecision;
}): Promise<TaskReviewResult> {
  const response = await fetch(
    `/api/gateway/tasks/${encodeURIComponent(taskId)}/review-decisions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Synarch-Actor-Type": "user",
        "X-Synarch-Actor-Id": "local-user",
        "X-Synarch-Trace-Id": `trace_frontend_task_review_${Date.now()}`
      },
      body: JSON.stringify(decision)
    }
  );
  return parseJsonResponse<TaskReviewResult>(response);
}
