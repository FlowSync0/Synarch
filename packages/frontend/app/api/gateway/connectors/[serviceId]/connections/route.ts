import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

type ConnectorConnectionsRouteContext = {
  params: Promise<{
    serviceId: string;
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

export async function POST(
  request: NextRequest,
  context: ConnectorConnectionsRouteContext
): Promise<NextResponse> {
  const { serviceId } = await context.params;
  try {
    const upstream = await fetch(
      gatewayUrl(`/connectors/${encodeURIComponent(serviceId)}/connections`),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Synarch-Actor-Type": request.headers.get("X-Synarch-Actor-Type") ?? "user",
          "X-Synarch-Actor-Id": request.headers.get("X-Synarch-Actor-Id") ?? "local-user",
          "X-Synarch-Trace-Id":
            request.headers.get("X-Synarch-Trace-Id") ??
            `trace_frontend_connector_connect_${Date.now()}`
        },
        body: await request.text()
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
