import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

function gatewayUrl(path: string, searchParams?: URLSearchParams): URL {
  const url = new URL(path, GATEWAY_URL);
  searchParams?.forEach((value, key) => {
    url.searchParams.append(key, value);
  });
  return url;
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

export async function POST(request: NextRequest): Promise<NextResponse> {
  const requestUrl = new URL(request.url);
  const projectId = requestUrl.searchParams.get("project_id")?.trim();
  if (!projectId) {
    return NextResponse.json(
      { detail: "project_id is required for frontend-triggered task execution" },
      { status: 400 }
    );
  }

  try {
    const upstream = await fetch(gatewayUrl("/tasks/run-ready", requestUrl.searchParams), {
      method: "POST",
      headers: forwardedHeaders(request)
    });
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
