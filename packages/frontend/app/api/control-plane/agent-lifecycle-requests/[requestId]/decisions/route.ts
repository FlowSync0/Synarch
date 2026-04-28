import { NextRequest, NextResponse } from "next/server";

const CONTROL_PLANE_URL = process.env.CONTROL_PLANE_URL ?? "http://127.0.0.1:8010";

type DecisionRouteContext = {
  params: Promise<{
    requestId: string;
  }>;
};

function controlPlaneUrl(path: string): URL {
  return new URL(path, CONTROL_PLANE_URL);
}

function forwardedHeaders(request: NextRequest): HeadersInit {
  const headers = new Headers();
  for (const header of [
    "content-type",
    "x-synarch-actor-type",
    "x-synarch-actor-id",
    "x-synarch-trace-id"
  ]) {
    const value = request.headers.get(header);
    if (value) {
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

export async function POST(
  request: NextRequest,
  context: DecisionRouteContext
): Promise<NextResponse> {
  const { requestId } = await context.params;
  try {
    const upstream = await fetch(
      controlPlaneUrl(
        `/agent-lifecycle-requests/${encodeURIComponent(requestId)}/decisions`
      ),
      {
        method: "POST",
        headers: forwardedHeaders(request),
        body: await request.text()
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Control plane unavailable" }, { status: 502 });
  }
}
