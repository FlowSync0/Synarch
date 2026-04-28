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
  const requestUrl = new URL(request.url);
  try {
    const upstream = await fetch(stateServiceUrl("/events", requestUrl.searchParams), {
      cache: "no-store"
    });
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "State service unavailable" }, { status: 502 });
  }
}
