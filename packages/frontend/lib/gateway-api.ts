import type {
  ConnectorJobRecord,
  ConnectorJobRunRecord,
  EventRecord,
  ProjectRecord,
  ServiceDefinition
} from "./state-service-api";
import type { AgentLifecycleRequest } from "./control-plane-api";
import { getOperatorId, operatorHeaders, operatorJsonHeaders } from "./operator-context";

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
  title?: string;
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
  required_tool_scopes: Record<string, string[]>;
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

export type ServiceHealthCheck = {
  service_id: string;
  name: string;
  kind: "internal" | "external" | "ai_provider" | "tool_provider";
  enabled: boolean;
  status: "healthy" | "unhealthy" | "unknown";
  base_url?: string | null;
  health_endpoint?: string | null;
  status_code?: number | null;
  response_time_ms?: number | null;
  error?: string | null;
  capabilities: string[];
  credential_scopes: string[];
  checked_at: string;
};

export type ServiceHealthReport = {
  trace_id: string;
  agent_id?: string | null;
  checks: ServiceHealthCheck[];
  event?: unknown | null;
  audit_log?: unknown | null;
  checked_at: string;
};

export type SystemReadinessStatus = "ready" | "warning" | "blocked";

export type SystemReadinessItem = {
  id: string;
  category: string;
  title: string;
  status: SystemReadinessStatus;
  detail: string;
  manual_action?: string | null;
  evidence: Record<string, unknown>;
};

export type SystemReadinessReport = {
  status: SystemReadinessStatus;
  items: SystemReadinessItem[];
  generated_at: string;
};

export type SecretVaultReencryptResult = {
  backend: string;
  encryption_enabled: boolean;
  scanned_secret_count: number;
  reencrypted_secret_count: number;
  already_encrypted_secret_count: number;
  failed_secret_count: number;
  status_after: Record<string, unknown>;
  audit_log?: unknown | null;
  audit_error?: string | null;
};

export type OperatorActionKind =
  | "human_assistance"
  | "task_review"
  | "credential_access"
  | "connector_job_review";

export type OperatorAction = {
  id: string;
  kind: OperatorActionKind;
  title: string;
  reason: string;
  recommended_action: string;
  priority: GoalPriority;
  status: string;
  target_id: string;
  project_id?: string | null;
  task_id?: string | null;
  agent_id?: string | null;
  service_id?: string | null;
  created_at: string;
  evidence: Record<string, unknown>;
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
  recorded_at: string;
  created_at?: string | null;
};

export type CostSummaryGroupBy = "project" | "agent" | "model" | "provider";

export type CostSummaryGroup = {
  group_key: string;
  record_count: number;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
  currency: string;
};

export type CostSummary = {
  group_by: string;
  groups: CostSummaryGroup[];
  record_count: number;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
  currency: string;
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
  metadata?: Record<string, unknown>;
  created_at: string;
  expires_at?: string | null;
};

export type MemoryRelationApplicationResult = {
  proposal_memory: MemoryItem;
  source_memory: MemoryItem;
  applied_related_memory_ids: string[];
  event: unknown;
};

export type MemoryContext = {
  agent_id: string;
  project_id?: string | null;
  token_budget: number;
  allowed_scopes: string[];
  allowed_project_ids: string[];
  max_related_items: number;
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

export type ProjectBriefAction = {
  kind:
    | "task_review"
    | "human_assistance"
    | "connector_job_review"
    | "task_next"
    | "project_planning";
  target_id?: string | null;
  title: string;
  reason: string;
};

export type ProjectBrief = {
  project_id: string;
  project: ProjectRecord;
  task_counts: Record<string, number>;
  next_tasks: TaskRecord[];
  review_tasks: TaskRecord[];
  blocked_connector_jobs: ConnectorJobRecord[];
  human_assistance_requests: HumanAssistanceRequest[];
  latest_events: EventRecord[];
  reminders: string[];
  next_action: ProjectBriefAction;
};

export type RunReadyRequest = {
  projectId: string;
  maxTasks: number;
};

export type TaskSkipRecord = {
  task_id: string;
  category: string;
  reason: string;
};

export type CredentialAccessRequest = {
  id: string;
  task_id: string;
  project_id: string;
  agent_id: string;
  tool_name: string;
  requested_scopes: string[];
  candidate_service_ids: string[];
  reason: string;
  requested_by_type: "user" | "agent" | "system" | "service";
  requested_by_id: string;
  status: "requested" | "approved" | "rejected" | "applied";
  created_at: string;
};

export type CredentialAccessDecision = {
  request_id: string;
  status: "approved" | "rejected";
  decided_by_type: "user" | "agent" | "system" | "service";
  decided_by_id: string;
  rationale: string;
  events_emitted: unknown[];
  decided_at: string;
};

export type CredentialGrant = {
  id: string;
  request_id: string;
  service_id: string;
  agent_id: string;
  project_id: string;
  task_id: string;
  tool_name: string;
  scopes: string[];
  granted_by_type: "user" | "agent" | "system" | "service";
  granted_by_id: string;
  rationale: string;
  secret_ref?: string | null;
  active: boolean;
  created_at: string;
};

export type CredentialGrantApplication = {
  request_id: string;
  service_id: string;
  access_request: CredentialAccessRequest;
  grant: CredentialGrant;
  service: ServiceDefinition;
  events_emitted: unknown[];
  applied_at: string;
};

export type ConnectorConnectionMode = "no_key" | "api_key" | "oauth" | "credentials";

export type SecretReference = {
  ref: string;
  vault: string;
  fingerprint: string;
  created_at: string;
};

export type ConnectorConnectRequest = {
  mode: ConnectorConnectionMode;
  api_key?: string;
  username?: string;
  password?: string;
  login_url?: string;
  credential_scopes: string[];
  project_id?: string | null;
  agent_id?: string | null;
  rationale?: string;
};

export type ConnectorConnectionRecord = {
  id: string;
  service_id: string;
  mode: ConnectorConnectionMode;
  status: "active" | "needs_oauth" | "disabled";
  credential_scopes: string[];
  secret_ref?: string | null;
  secret_fingerprint?: string | null;
  setup_url?: string | null;
  callback_url?: string | null;
  external_state?: string | null;
  connected_by_type: "user" | "agent" | "system" | "service";
  connected_by_id: string;
  project_id?: string | null;
  agent_id?: string | null;
  rationale: string;
  created_at: string;
  updated_at: string;
};

export type ConnectorConnectionResult = {
  connection: ConnectorConnectionRecord;
  service: ServiceDefinition;
  event: unknown;
  audit_log?: unknown | null;
};

export type WebProviderStatus = {
  provider_id: string;
  name: string;
  category: string;
  implemented: boolean;
  requires_api_key: boolean;
  api_key_env_var?: string | null;
  python_module?: string | null;
  configured: boolean;
  configured_by: string[];
  capabilities: string[];
  risk_level: "low" | "medium" | "high";
  requires_human_approval: boolean;
  notes: string;
};

export type ConnectorConnectionDisableRequest = {
  rationale: string;
};

export type HumanAssistanceKind =
  | "captcha"
  | "pdf_review"
  | "error_resolution"
  | "key_decision"
  | "manual_action"
  | "other";

export type HumanAssistanceStatus = "requested" | "answered" | "dismissed";

export type HumanAssistanceRequest = {
  id: string;
  project_id: string;
  task_id?: string | null;
  agent_id: string;
  kind: HumanAssistanceKind;
  title: string;
  description: string;
  urgency: GoalPriority;
  evidence: Record<string, unknown>;
  requested_by_type: "user" | "agent" | "system" | "service";
  requested_by_id: string;
  status: HumanAssistanceStatus;
  response?: string | null;
  resolved_by_type?: "user" | "agent" | "system" | "service" | null;
  resolved_by_id?: string | null;
  created_at: string;
  resolved_at?: string | null;
};

export type HumanAssistanceResolution = {
  request_id: string;
  status: "answered" | "dismissed";
  response: string;
  resolved_by_type: "user" | "agent" | "system" | "service";
  resolved_by_id: string;
  events_emitted: unknown[];
  resolved_at: string;
};

export type TaskRunBatchResult = {
  trace_id: string;
  max_tasks: number;
  project_id?: string | null;
  stop_reason: string;
  runs: TaskRunResult[];
  skipped_task_ids: string[];
  skipped_tasks: TaskSkipRecord[];
  credential_access_requests: CredentialAccessRequest[];
  credential_resumed_task_ids: string[];
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
    lifecycle_requests_created: AgentLifecycleRequest[];
    tool_calls_requested?: ToolCallRequest[];
    tool_results?: ToolResult[];
  };
  model_call_events: EventRecord[];
  created_sub_tasks: TaskRecord[];
  sub_task_events: EventRecord[];
  lifecycle_requests_created: AgentLifecycleRequest[];
  memory_events: EventRecord[];
  tool_results: ToolResult[];
  cost_records: CostRecord[];
};

export type ConnectorJobAction = "run" | "stop" | "resume";

export type ConnectorJobMutationResult = {
  job: ConnectorJobRecord;
  event: unknown;
  audit_log?: unknown | null;
};

export type ConnectorJobRunResult = {
  run: ConnectorJobRunRecord;
  event: unknown;
  audit_log?: unknown | null;
};

export type ConnectorJobActionResult = ConnectorJobMutationResult | ConnectorJobRunResult;

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
    headers: operatorJsonHeaders(`trace_frontend_run_ready_${Date.now()}`)
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

export async function listProjectBriefs(projectId?: string): Promise<ProjectBrief[]> {
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
  }
  const query = params.toString();
  const response = await fetch(`/api/gateway/projects/briefs${query ? `?${query}` : ""}`, {
    cache: "no-store"
  });
  return parseJsonResponse<ProjectBrief[]>(response);
}

export async function listOperatorActions(projectId?: string): Promise<OperatorAction[]> {
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
  }
  const query = params.toString();
  const response = await fetch(`/api/gateway/operator-actions${query ? `?${query}` : ""}`, {
    cache: "no-store"
  });
  return parseJsonResponse<OperatorAction[]>(response);
}

export async function runTask(taskId: string): Promise<TaskRunResult> {
  const response = await fetch(`/api/gateway/tasks/${encodeURIComponent(taskId)}/run`, {
    method: "POST",
    headers: operatorJsonHeaders(`trace_frontend_task_run_${Date.now()}`)
  });
  return parseJsonResponse<TaskRunResult>(response);
}

export async function runConnectorJobNow({
  jobId
}: {
  jobId: string;
}): Promise<ConnectorJobRunResult> {
  const response = await fetch(
    `/api/gateway/connector-jobs/${encodeURIComponent(jobId)}/execute`,
    {
      method: "POST",
      headers: operatorHeaders(`trace_frontend_connector_job_run_${Date.now()}`)
    }
  );
  return parseJsonResponse<ConnectorJobRunResult>(response);
}

export async function stopConnectorJob({
  jobId
}: {
  jobId: string;
}): Promise<ConnectorJobMutationResult> {
  const operatorId = getOperatorId();
  const response = await fetch(
    `/api/gateway/connector-jobs/${encodeURIComponent(jobId)}/stop`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_connector_job_stop_${Date.now()}`),
      body: JSON.stringify({
        stopped_by_type: "user",
        stopped_by_id: operatorId,
        reason: "Stopped from Synarch dashboard."
      })
    }
  );
  return parseJsonResponse<ConnectorJobMutationResult>(response);
}

export async function resumeConnectorJob({
  jobId
}: {
  jobId: string;
}): Promise<ConnectorJobMutationResult> {
  const operatorId = getOperatorId();
  const response = await fetch(
    `/api/gateway/connector-jobs/${encodeURIComponent(jobId)}/resume`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_connector_job_resume_${Date.now()}`),
      body: JSON.stringify({
        resumed_by_type: "user",
        resumed_by_id: operatorId,
        reason: "Resumed from Synarch dashboard."
      })
    }
  );
  return parseJsonResponse<ConnectorJobMutationResult>(response);
}

export async function callTool(toolCall: ToolCallRequest): Promise<ToolResult> {
  const response = await fetch("/api/gateway/tools/call", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...operatorHeaders(),
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

export async function checkServiceHealth(agentId?: string): Promise<ServiceHealthReport> {
  const params = new URLSearchParams();
  if (agentId) {
    params.set("agent_id", agentId);
  }
  const query = params.toString();
  const response = await fetch(
    `/api/gateway/services/health-checks${query ? `?${query}` : ""}`,
    {
      method: "POST",
      headers: {
        "X-Synarch-Trace-Id": `trace_frontend_service_health_${Date.now()}`
      }
    }
  );
  return parseJsonResponse<ServiceHealthReport>(response);
}

export async function getSystemReadiness(): Promise<SystemReadinessReport> {
  const response = await fetch("/api/gateway/readiness", {
    cache: "no-store"
  });
  return parseJsonResponse<SystemReadinessReport>(response);
}

export async function reencryptSecretVault(): Promise<SecretVaultReencryptResult> {
  const response = await fetch("/api/gateway/secret-vault/reencrypt", {
    method: "POST",
    headers: operatorHeaders(`trace_frontend_secret_vault_reencrypt_${Date.now()}`)
  });
  return parseJsonResponse<SecretVaultReencryptResult>(response);
}

export async function listConnectorConnections(): Promise<ConnectorConnectionRecord[]> {
  const response = await fetch("/api/gateway/connector-connections", {
    cache: "no-store"
  });
  return parseJsonResponse<ConnectorConnectionRecord[]>(response);
}

export async function listWebProviders(): Promise<WebProviderStatus[]> {
  const response = await fetch("/api/gateway/web/providers", {
    cache: "no-store"
  });
  return parseJsonResponse<WebProviderStatus[]>(response);
}

export async function listCostRecords(filters: {
  projectId?: string | null;
  agentId?: string | null;
  providerId?: string | null;
  modelId?: string | null;
  traceId?: string | null;
} = {}): Promise<CostRecord[]> {
  const params = new URLSearchParams();
  if (filters.projectId) {
    params.set("project_id", filters.projectId);
  }
  if (filters.agentId) {
    params.set("agent_id", filters.agentId);
  }
  if (filters.providerId) {
    params.set("provider_id", filters.providerId);
  }
  if (filters.modelId) {
    params.set("model_id", filters.modelId);
  }
  if (filters.traceId) {
    params.set("trace_id", filters.traceId);
  }
  const query = params.toString();
  const response = await fetch(`/api/gateway/cost-records${query ? `?${query}` : ""}`, {
    cache: "no-store"
  });
  return parseJsonResponse<CostRecord[]>(response);
}

export async function getCostSummary({
  groupBy,
  projectId,
  agentId,
  providerId,
  modelId,
  traceId
}: {
  groupBy: CostSummaryGroupBy;
  projectId?: string | null;
  agentId?: string | null;
  providerId?: string | null;
  modelId?: string | null;
  traceId?: string | null;
}): Promise<CostSummary> {
  const params = new URLSearchParams({ group_by: groupBy });
  if (projectId) {
    params.set("project_id", projectId);
  }
  if (agentId) {
    params.set("agent_id", agentId);
  }
  if (providerId) {
    params.set("provider_id", providerId);
  }
  if (modelId) {
    params.set("model_id", modelId);
  }
  if (traceId) {
    params.set("trace_id", traceId);
  }
  const response = await fetch(`/api/gateway/cost-records/summary?${params.toString()}`, {
    cache: "no-store"
  });
  return parseJsonResponse<CostSummary>(response);
}

export async function connectConnectorService({
  serviceId,
  request
}: {
  serviceId: string;
  request: ConnectorConnectRequest;
}): Promise<ConnectorConnectionResult> {
  const response = await fetch(
    `/api/gateway/connectors/${encodeURIComponent(serviceId)}/connections`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_connector_connect_${Date.now()}`),
      body: JSON.stringify(request)
    }
  );
  return parseJsonResponse<ConnectorConnectionResult>(response);
}

export async function disableConnectorConnection({
  connectionId,
  request
}: {
  connectionId: string;
  request: ConnectorConnectionDisableRequest;
}): Promise<ConnectorConnectionResult> {
  const response = await fetch(
    `/api/gateway/connector-connections/${encodeURIComponent(connectionId)}/disable`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_connector_disable_${Date.now()}`),
      body: JSON.stringify(request)
    }
  );
  return parseJsonResponse<ConnectorConnectionResult>(response);
}

export async function listCredentialAccessRequests(): Promise<CredentialAccessRequest[]> {
  const response = await fetch("/api/gateway/credential-access-requests", {
    cache: "no-store"
  });
  return parseJsonResponse<CredentialAccessRequest[]>(response);
}

export async function listHumanAssistanceRequests(): Promise<HumanAssistanceRequest[]> {
  const response = await fetch("/api/gateway/human-assistance-requests", {
    cache: "no-store"
  });
  return parseJsonResponse<HumanAssistanceRequest[]>(response);
}

export async function resolveHumanAssistanceRequest({
  requestId,
  status,
  response
}: {
  requestId: string;
  status: "answered" | "dismissed";
  response: string;
}): Promise<HumanAssistanceResolution> {
  const operatorId = getOperatorId();
  const upstream = await fetch(
    `/api/gateway/human-assistance-requests/${encodeURIComponent(requestId)}/resolutions`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_human_assistance_${Date.now()}`),
      body: JSON.stringify({
        request_id: requestId,
        status,
        response,
        resolved_by_type: "user",
        resolved_by_id: operatorId
      })
    }
  );
  return parseJsonResponse<HumanAssistanceResolution>(upstream);
}

export async function decideCredentialAccessRequest({
  requestId,
  status
}: {
  requestId: string;
  status: "approved" | "rejected";
}): Promise<CredentialAccessDecision> {
  const operatorId = getOperatorId();
  const response = await fetch(
    `/api/gateway/credential-access-requests/${encodeURIComponent(requestId)}/decisions`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_credential_access_${Date.now()}`),
      body: JSON.stringify({
        request_id: requestId,
        status,
        decided_by_type: "user",
        decided_by_id: operatorId,
        rationale:
          status === "approved"
            ? "Credential access approved from Synarch dashboard."
            : "Credential access rejected from Synarch dashboard."
      })
    }
  );
  return parseJsonResponse<CredentialAccessDecision>(response);
}

export async function applyCredentialAccessGrant({
  requestId,
  serviceId
}: {
  requestId: string;
  serviceId: string;
}): Promise<CredentialGrantApplication> {
  const operatorId = getOperatorId();
  const response = await fetch(
    `/api/gateway/credential-access-requests/${encodeURIComponent(requestId)}/grant-applications`,
    {
      method: "POST",
      headers: operatorJsonHeaders(`trace_frontend_credential_grant_${Date.now()}`),
      body: JSON.stringify({
        request_id: requestId,
        service_id: serviceId,
        applied_by_type: "user",
        applied_by_id: operatorId,
        rationale: "Credential grant applied from Synarch dashboard."
      })
    }
  );
  return parseJsonResponse<CredentialGrantApplication>(response);
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
      headers: operatorJsonHeaders(`trace_frontend_memory_review_${Date.now()}`),
      body: JSON.stringify({ status })
    }
  );
  return parseJsonResponse<MemoryItem>(response);
}

export async function applyMemoryRelationProposal({
  proposalId
}: {
  proposalId: string;
}): Promise<MemoryRelationApplicationResult> {
  const response = await fetch(
    `/api/gateway/memory-items/relation-proposals/${encodeURIComponent(proposalId)}/apply`,
    {
      method: "POST",
      headers: operatorHeaders(`trace_frontend_memory_relation_apply_${Date.now()}`)
    }
  );
  return parseJsonResponse<MemoryRelationApplicationResult>(response);
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
      headers: operatorJsonHeaders(`trace_frontend_task_review_${Date.now()}`),
      body: JSON.stringify(decision)
    }
  );
  return parseJsonResponse<TaskReviewResult>(response);
}
