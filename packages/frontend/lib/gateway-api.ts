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

export type ProjectTimeline = {
  project_id: string;
  project: ProjectRecord;
  tasks: TaskRecord[];
  events: EventRecord[];
  cost_records: CostRecord[];
  audit_logs: unknown[];
  memory_items: unknown[];
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
  runs: Array<{
    trace_id: string;
    task: TaskRecord;
    agent_result: {
      agent_id: string;
      task_id: string;
      status: TaskStatus;
      summary: string;
    };
    cost_records?: Array<{
      total_cost?: number;
      currency?: string;
    }>;
  }>;
  skipped_task_ids: string[];
  lease_recovery?: unknown | null;
  scheduler_event?: unknown | null;
  scheduler_audit_log?: unknown | null;
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
