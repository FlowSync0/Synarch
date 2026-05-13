export type LifecycleAction = "create_agent" | "update_agent" | "deactivate_agent";
export type ActorType = "user" | "agent" | "system" | "service";
export type ApprovalStatus = "requested" | "approved" | "rejected" | "applied";

export type AgentDefinition = {
  id: string;
  name: string;
  role: string;
  division: string;
  manager_id?: string | null;
  status: string;
  capabilities: {
    skills: string[];
    tools: string[];
    models: string[];
  };
  permissions: {
    can_read_scopes: string[];
    can_write_scopes: string[];
    allowed_tools: string[];
    denied_tools: string[];
  };
  model: string;
  model_policy_id?: string | null;
  allowed_model_ids: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type AgentSoul = {
  id: string;
  agent_id: string;
  version: number;
  identity: string;
  mission: string;
  responsibilities: string[];
  operating_principles: string[];
  boundaries: string[];
  escalation_rules: string[];
  communication_style: string;
  created_by: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type LocalWorldView = {
  agent_id: string;
  name?: string | null;
  role: string;
  division: string;
  peers: string[];
  manager?: string | null;
  manager_agent_id?: string | null;
  peer_agent_ids: string[];
  direct_report_agent_ids: string[];
  soul?: AgentSoul | null;
  active_projects: string[];
  permissions: AgentDefinition["permissions"];
  capabilities: AgentDefinition["capabilities"];
  policies: string[];
  available_services: string[];
  available_service_capabilities: Record<string, string[]>;
  available_service_credential_scopes: Record<string, string[]>;
  available_connector_ids: string[];
  available_skill_ids: string[];
};

export type AgentLifecycleRequest = {
  id: string;
  action: LifecycleAction;
  requested_by_type: ActorType;
  requested_by_id: string;
  reason: string;
  proposed_agent?: AgentDefinition | null;
  proposed_soul?: AgentSoul | null;
  target_agent_id?: string | null;
  status: ApprovalStatus;
  requires_human_approval: boolean;
  created_at: string;
};

export type AgentDefinitionDraft = Pick<
  AgentDefinition,
  "id" | "name" | "role" | "division"
> &
  Partial<
    Pick<
      AgentDefinition,
      | "manager_id"
      | "status"
      | "capabilities"
      | "permissions"
      | "model"
      | "model_policy_id"
      | "allowed_model_ids"
      | "created_by"
    >
  >;

export type AgentSoulDraft = Pick<
  AgentSoul,
  "id" | "agent_id" | "identity" | "mission" | "created_by"
> &
  Partial<
    Pick<
      AgentSoul,
      | "version"
      | "responsibilities"
      | "operating_principles"
      | "boundaries"
      | "escalation_rules"
      | "communication_style"
      | "active"
    >
  >;

export type CreateAgentLifecycleRequestInput = {
  id: string;
  action: "create_agent";
  requested_by_type: ActorType;
  requested_by_id: string;
  reason: string;
  proposed_agent: AgentDefinitionDraft;
  proposed_soul?: AgentSoulDraft | null;
  requires_human_approval?: boolean;
};

export type UpdateAgentLifecycleRequestInput = {
  id: string;
  action: "update_agent";
  requested_by_type: ActorType;
  requested_by_id: string;
  reason: string;
  target_agent_id: string;
  proposed_agent: AgentDefinitionDraft;
  proposed_soul?: AgentSoulDraft | null;
  requires_human_approval?: boolean;
};

export type DeactivateAgentLifecycleRequestInput = {
  id: string;
  action: "deactivate_agent";
  requested_by_type: ActorType;
  requested_by_id: string;
  reason: string;
  target_agent_id: string;
  requires_human_approval?: boolean;
};

export type AgentLifecycleRequestInput =
  | CreateAgentLifecycleRequestInput
  | UpdateAgentLifecycleRequestInput
  | DeactivateAgentLifecycleRequestInput;

export type AgentLifecycleDecision = {
  request_id: string;
  status: ApprovalStatus;
  decided_by_type: ActorType;
  decided_by_id: string;
  rationale: string;
  events_emitted: unknown[];
  decided_at: string;
};

export type AgentModelPolicyUpdate = {
  model_policy_id: string | null;
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

export async function listAgentLifecycleRequests(): Promise<AgentLifecycleRequest[]> {
  const response = await fetch("/api/control-plane/agent-lifecycle-requests", {
    cache: "no-store"
  });
  return parseJsonResponse<AgentLifecycleRequest[]>(response);
}

export async function createAgentLifecycleRequest(
  lifecycleRequest: AgentLifecycleRequestInput
): Promise<AgentLifecycleRequest> {
  const response = await fetch("/api/control-plane/agent-lifecycle-requests", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Synarch-Actor-Type": "user",
      "X-Synarch-Actor-Id": "local-user",
      "X-Synarch-Trace-Id": `trace_frontend_lifecycle_create_${Date.now()}`
    },
    body: JSON.stringify(lifecycleRequest)
  });
  return parseJsonResponse<AgentLifecycleRequest>(response);
}

export async function listAgents(): Promise<AgentDefinition[]> {
  const response = await fetch("/api/control-plane/agents", {
    cache: "no-store"
  });
  return parseJsonResponse<AgentDefinition[]>(response);
}

export async function getAgentWorldView(agentId: string): Promise<LocalWorldView> {
  const response = await fetch(
    `/api/control-plane/agents/${encodeURIComponent(agentId)}/world-view`,
    {
      cache: "no-store"
    }
  );
  return parseJsonResponse<LocalWorldView>(response);
}

export async function updateAgentModelPolicy(
  agentId: string,
  modelPolicyId: string | null
): Promise<AgentDefinition> {
  const response = await fetch(
    `/api/control-plane/agents/${encodeURIComponent(agentId)}/model-policy`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-Synarch-Actor-Type": "user",
        "X-Synarch-Actor-Id": "local-user",
        "X-Synarch-Trace-Id": `trace_frontend_model_policy_${Date.now()}`
      },
      body: JSON.stringify({ model_policy_id: modelPolicyId } satisfies AgentModelPolicyUpdate)
    }
  );
  return parseJsonResponse<AgentDefinition>(response);
}

export async function decideAgentLifecycleRequest({
  requestId,
  status
}: {
  requestId: string;
  status: "approved" | "rejected";
}): Promise<AgentLifecycleDecision> {
  const response = await fetch(
    `/api/control-plane/agent-lifecycle-requests/${encodeURIComponent(requestId)}/decisions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Synarch-Actor-Type": "user",
        "X-Synarch-Actor-Id": "local-user",
        "X-Synarch-Trace-Id": `trace_frontend_lifecycle_${Date.now()}`
      },
      body: JSON.stringify({
        request_id: requestId,
        status,
        decided_by_type: "user",
        decided_by_id: "local-user",
        rationale:
          status === "approved"
            ? "Approved from Synarch dashboard."
            : "Rejected from Synarch dashboard."
      })
    }
  );
  return parseJsonResponse<AgentLifecycleDecision>(response);
}
