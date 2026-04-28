import { NextResponse } from "next/server";

const CONTROL_PLANE_URL = process.env.CONTROL_PLANE_URL ?? "http://127.0.0.1:8010";

function controlPlaneUrl(path: string): URL {
  return new URL(path, CONTROL_PLANE_URL);
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

export async function GET(): Promise<NextResponse> {
  try {
    const upstream = await fetch(controlPlaneUrl("/agents"), {
      cache: "no-store"
    });
    return proxyResponse(upstream);
  } catch {
    return NextResponse.json({ detail: "Control plane unavailable" }, { status: 502 });
  }
}
