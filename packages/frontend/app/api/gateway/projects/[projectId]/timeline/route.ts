import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

type ProjectTimelineRouteContext = {
  params: Promise<{
    projectId: string;
  }>;
};

function gatewayUrl(path: string): URL {
  return new URL(path, GATEWAY_URL);
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

export async function GET(
  _request: NextRequest,
  context: ProjectTimelineRouteContext
): Promise<NextResponse> {
  const { projectId } = await context.params;
  try {
    const upstream = await fetch(
      gatewayUrl(`/projects/${encodeURIComponent(projectId)}/timeline`),
      {
        cache: "no-store"
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
