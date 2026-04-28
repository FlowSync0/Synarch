export type LifecycleAction = "create_agent" | "update_agent" | "deactivate_agent";
export type ActorType = "user" | "agent" | "system" | "service";
export type ApprovalStatus = "requested" | "approved" | "rejected" | "applied";

export type AgentDefinition = {
  id: string;
  name: string;
  role: string;
  division: string;
  manager_id?: string | null;
  status?: string;
};

export type AgentLifecycleRequest = {
  id: string;
  action: LifecycleAction;
  requested_by_type: ActorType;
  requested_by_id: string;
  reason: string;
  proposed_agent?: AgentDefinition | null;
  target_agent_id?: string | null;
  status: ApprovalStatus;
  requires_human_approval: boolean;
  created_at: string;
};

export type AgentLifecycleDecision = {
  request_id: string;
  status: ApprovalStatus;
  decided_by_type: ActorType;
  decided_by_id: string;
  rationale: string;
  events_emitted: unknown[];
  decided_at: string;
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
