import { NextRequest, NextResponse } from "next/server";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";

function gatewayUrl(path: string, searchParams?: URLSearchParams): URL {
  const url = new URL(path, GATEWAY_URL);
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
      gatewayUrl("/connector-connections", request.nextUrl.searchParams),
      { cache: "no-store" }
    );
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Gateway unavailable" }, { status: 502 });
  }
}
