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
