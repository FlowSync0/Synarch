import { NextRequest, NextResponse } from "next/server";

const CONTROL_PLANE_URL = process.env.CONTROL_PLANE_URL ?? "http://127.0.0.1:8010";

type ModelPolicyRouteContext = {
  params: Promise<{
    agentId: string;
  }>;
};

function controlPlaneUrl(path: string): URL {
  return new URL(path, CONTROL_PLANE_URL);
}

function forwardedHeaders(request: NextRequest): Headers {
  const headers = new Headers({
    "Content-Type": request.headers.get("content-type") ?? "application/json"
  });
  for (const header of [
    "x-synarch-actor-type",
    "x-synarch-actor-id",
    "x-synarch-trace-id"
  ]) {
    const value = request.headers.get(header);
    if (value !== null) {
      headers.set(header, value);
    }
  }
  return headers;
}

async function proxyResponse(upstream: Response): Promise<NextResponse> {
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json"
    }
  });
}

export async function PATCH(
  request: NextRequest,
  context: ModelPolicyRouteContext
): Promise<NextResponse> {
  const { agentId } = await context.params;
  try {
    const upstream = await fetch(
      controlPlaneUrl(`/agents/${encodeURIComponent(agentId)}/model-policy`),
      {
        method: "PATCH",
        headers: forwardedHeaders(request),
        body: await request.text()
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Control plane unavailable" }, { status: 502 });
  }
}
