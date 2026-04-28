export type ProjectStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "blocked"
  | "failed"
  | "needs_review";

export type Priority = "low" | "medium" | "high" | "critical";

export type ProjectRecord = {
  id: string;
  title: string;
  goal: string;
  status: ProjectStatus;
  priority: Priority;
  owner_agent_id: string;
  created_at: string;
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
