import { NextRequest, NextResponse } from "next/server";

const STATE_SERVICE_URL = process.env.STATE_SERVICE_URL ?? "http://127.0.0.1:8020";

function stateServiceUrl(path: string, searchParams?: URLSearchParams): URL {
  const url = new URL(path, STATE_SERVICE_URL);
  searchParams?.forEach((value, key) => {
    url.searchParams.append(key, value);
  });
  return url;
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
  try {
    const upstream = await fetch(
      stateServiceUrl("/work-queue/items", request.nextUrl.searchParams),
      {
        cache: "no-store"
      }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "State service unavailable" }, { status: 502 });
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const upstream = await fetch(stateServiceUrl("/work-queue/items"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Synarch-Trace-Id":
          request.headers.get("X-Synarch-Trace-Id") ??
          `trace_frontend_work_queue_${Date.now()}`
      },
      body: await request.text()
    });
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "State service unavailable" }, { status: 502 });
  }
}
