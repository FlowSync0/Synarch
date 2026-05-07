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

export async function POST(request: NextRequest): Promise<NextResponse> {
  const url = gatewayUrl("/services/health-checks");
  const agentId = request.nextUrl.searchParams.get("agent_id");
  if (agentId) {
    url.searchParams.set("agent_id", agentId);
  }

  try {
    const upstream = await fetch(url, {
      method: "POST",
      cache: "no-store",
      headers: {
        "X-Synarch-Trace-Id":
          request.headers.get("x-synarch-trace-id") ??
          `trace_frontend_service_health_${Date.now()}`
      }
    });
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
