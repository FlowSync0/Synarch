import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

type MemoryRelationApplyRouteContext = {
  params: Promise<{
    proposalId: string;
  }>;
};

function gatewayUrl(path: string): URL {
  return new URL(path, GATEWAY_URL);
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
  context: MemoryRelationApplyRouteContext
): Promise<NextResponse> {
  const { proposalId } = await context.params;
  try {
    const upstream = await fetch(
      gatewayUrl(`/memory-items/relation-proposals/${encodeURIComponent(proposalId)}/apply`),
      {
        method: "POST",
        headers: forwardedHeaders(request)
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
