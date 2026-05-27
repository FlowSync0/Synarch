import { NextRequest, NextResponse } from "next/server";

const STATE_SERVICE_URL = process.env.STATE_SERVICE_URL ?? "http://127.0.0.1:8020";

type ReviewDecisionRouteContext = {
  params: Promise<{
    itemId: string;
  }>;
};

function stateServiceUrl(path: string): URL {
  return new URL(path, STATE_SERVICE_URL);
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
  context: ReviewDecisionRouteContext
): Promise<NextResponse> {
  const { itemId } = await context.params;
  try {
    const upstream = await fetch(
      stateServiceUrl(`/work-queue/items/${encodeURIComponent(itemId)}/review-decisions`),
      {
        method: "POST",
        headers: forwardedHeaders(request),
        body: await request.text()
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "State service unavailable" }, { status: 502 });
  }
}
