import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

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

export async function GET(request: NextRequest): Promise<NextResponse> {
  const agentId = request.nextUrl.searchParams.get("agent_id");
  if (!agentId) {
    return NextResponse.json({ detail: "agent_id is required" }, { status: 422 });
  }

  try {
    const upstream = await fetch(
      gatewayUrl(`/tools/credential-status?agent_id=${encodeURIComponent(agentId)}`),
      { cache: "no-store" }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
