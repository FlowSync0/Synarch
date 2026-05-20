import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

type HumanAssistanceResolutionRouteContext = {
  params: Promise<{
    requestId: string;
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
  context: HumanAssistanceResolutionRouteContext
): Promise<NextResponse> {
  const { requestId } = await context.params;
  try {
    const upstream = await fetch(
      gatewayUrl(`/human-assistance-requests/${encodeURIComponent(requestId)}/resolutions`),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Synarch-Actor-Type": request.headers.get("x-synarch-actor-type") ?? "user",
          "X-Synarch-Actor-Id": request.headers.get("x-synarch-actor-id") ?? "local-user",
          "X-Synarch-Trace-Id":
            request.headers.get("x-synarch-trace-id") ??
            `trace_frontend_human_assistance_${Date.now()}`
        },
        body: await request.text()
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
