export type ProjectStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "blocked"
  | "failed"
  | "needs_review";

export type Priority = "low" | "medium" | "high" | "critical";
export type ConnectorJobKind = "cron" | "webhook";
export type ConnectorJobStatus = "active" | "stopped";
export type ConnectorJobRunStatus = "completed" | "failed" | "blocked" | "skipped";
export type ConnectorActorType = "user" | "agent" | "system" | "service";
export type ServiceKind = "internal" | "external" | "ai_provider" | "tool_provider";

export type ProjectRecord = {
  id: string;
  title: string;
  goal: string;
  status: ProjectStatus;
  priority: Priority;
  owner_agent_id: string;
  created_at: string;
};

export type EventRecord = {
  id: string;
  type: string;
  source_agent_id?: string | null;
  target?: string | null;
  payload: Record<string, unknown>;
  timestamp: string;
  trace_id?: string | null;
};

export type ConnectorJobRecord = {
  id: string;
  service_id: string;
  project_id?: string | null;
  task_id?: string | null;
  owner_agent_id: string;
  kind: ConnectorJobKind;
  status: ConnectorJobStatus;
  schedule?: string | null;
  webhook_path?: string | null;
  purpose: string;
  created_by_type: ConnectorActorType;
  created_by_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  next_run_at?: string | null;
  stopped_at?: string | null;
};

export type ConnectorJobRunRecord = {
  id: string;
  job_id: string;
  service_id: string;
  project_id?: string | null;
  task_id?: string | null;
  owner_agent_id: string;
  status: ConnectorJobRunStatus;
  triggered_by_type: ConnectorActorType;
  triggered_by_id: string;
  trace_id?: string | null;
  output: Record<string, unknown>;
  error?: string | null;
  started_at: string;
  completed_at: string;
};

export type WorkQueueStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "dead_lettered";

export type WorkQueueItem = {
  id: string;
  queue_name: string;
  status: WorkQueueStatus;
  payload: Record<string, unknown>;
  priority: number;
  run_after_at?: string | null;
  lease_owner_id?: string | null;
  lease_expires_at?: string | null;
  attempt_count: number;
  max_attempts: number;
  result?: Record<string, unknown> | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
};

export type WorkQueueItemCreateRequest = {
  queue_name: string;
  payload: Record<string, unknown>;
  priority?: number;
  max_attempts?: number;
  run_after_at?: string | null;
};

export type WorkQueueReviewDecision = {
  action: "retry" | "dead_letter";
  reviewed_by_type: ConnectorActorType;
  reviewed_by_id: string;
  reason: string;
  retry_after_at?: string | null;
};

export type ServiceDefinition = {
  id: string;
  name: string;
  kind: ServiceKind;
  base_url?: string | null;
  health_endpoint?: string | null;
  capabilities: string[];
  credential_scopes: string[];
  owner_agent_id?: string | null;
  allowed_agent_ids: string[];
  allowed_divisions: string[];
  audit_required: boolean;
  metadata: Record<string, unknown>;
  enabled: boolean;
};

export type AuditLogRecord = {
  id: string;
  actor_type: ConnectorActorType;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  payload: Record<string, unknown>;
  trace_id?: string | null;
  created_at: string;
};

export type AiProviderType = "local" | "openrouter" | "openai" | "anthropic" | "custom";

export type ModelProviderConfig = {
  id: string;
  name: string;
  provider_type: AiProviderType;
  base_url?: string | null;
  api_key_env_var?: string | null;
  default_model_id?: string | null;
  enabled: boolean;
};

export type ModelDefinition = {
  id: string;
  provider_id: string;
  display_name: string;
  context_window?: number | null;
  input_cost_per_million_tokens: number;
  output_cost_per_million_tokens: number;
  currency: string;
  supports_tool_calling: boolean;
  supports_structured_output: boolean;
  enabled: boolean;
};

export type ModelPolicy = {
  id: string;
  name: string;
  default_model_id: string;
  allowed_model_ids: string[];
  max_cost_per_task?: number | null;
  max_cost_per_day?: number | null;
  currency: string;
  require_human_approval_above?: number | null;
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

export async function listProjects(): Promise<ProjectRecord[]> {
  const response = await fetch("/api/state-service/projects", {
    cache: "no-store"
  });
  return parseJsonResponse<ProjectRecord[]>(response);
}

export async function listServices(): Promise<ServiceDefinition[]> {
  const response = await fetch("/api/state-service/services", {
    cache: "no-store"
  });
  return parseJsonResponse<ServiceDefinition[]>(response);
}

export async function listEvents(): Promise<EventRecord[]> {
  const response = await fetch("/api/state-service/events", {
    cache: "no-store"
  });
  return parseJsonResponse<EventRecord[]>(response);
}

export async function listAuditLogs(): Promise<AuditLogRecord[]> {
  const response = await fetch("/api/state-service/audit-logs", {
    cache: "no-store"
  });
  return parseJsonResponse<AuditLogRecord[]>(response);
}

export async function listModelProviders(): Promise<ModelProviderConfig[]> {
  const response = await fetch("/api/state-service/model-providers", {
    cache: "no-store"
  });
  return parseJsonResponse<ModelProviderConfig[]>(response);
}

export async function listModelDefinitions(): Promise<ModelDefinition[]> {
  const response = await fetch("/api/state-service/model-definitions", {
    cache: "no-store"
  });
  return parseJsonResponse<ModelDefinition[]>(response);
}

export async function listModelPolicies(): Promise<ModelPolicy[]> {
  const response = await fetch("/api/state-service/model-policies", {
    cache: "no-store"
  });
  return parseJsonResponse<ModelPolicy[]>(response);
}

export async function listConnectorJobs(): Promise<ConnectorJobRecord[]> {
  const response = await fetch("/api/state-service/connector-jobs", {
    cache: "no-store"
  });
  return parseJsonResponse<ConnectorJobRecord[]>(response);
}

export async function listConnectorJobRuns(): Promise<ConnectorJobRunRecord[]> {
  const response = await fetch("/api/state-service/connector-job-runs", {
    cache: "no-store"
  });
  return parseJsonResponse<ConnectorJobRunRecord[]>(response);
}

export async function listWorkQueueItems(queueName?: string): Promise<WorkQueueItem[]> {
  const params = new URLSearchParams();
  if (queueName) {
    params.set("queue_name", queueName);
  }
  const query = params.toString();
  const response = await fetch(
    `/api/state-service/work-queue/items${query ? `?${query}` : ""}`,
    {
      cache: "no-store"
    }
  );
  return parseJsonResponse<WorkQueueItem[]>(response);
}

export async function createWorkQueueItem(
  item: WorkQueueItemCreateRequest
): Promise<WorkQueueItem> {
  const response = await fetch("/api/state-service/work-queue/items", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Synarch-Trace-Id": `trace_frontend_work_queue_${Date.now()}`
    },
    body: JSON.stringify(item)
  });
  return parseJsonResponse<WorkQueueItem>(response);
}

export async function reviewWorkQueueItem(
  itemId: string,
  decision: WorkQueueReviewDecision
): Promise<WorkQueueItem> {
  const response = await fetch(
    `/api/state-service/work-queue/items/${encodeURIComponent(itemId)}/review-decisions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Synarch-Actor-Type": decision.reviewed_by_type,
        "X-Synarch-Actor-Id": decision.reviewed_by_id,
        "X-Synarch-Trace-Id": `trace_frontend_work_queue_review_${Date.now()}`
      },
      body: JSON.stringify(decision)
    }
  );
  return parseJsonResponse<WorkQueueItem>(response);
}
