import { NextResponse } from "next/server";

import { assertSameOrigin, verifyAdminSession } from "@/lib/admin-session";
import { loadServerConfig } from "@/lib/config";

interface RouteContext {
  params: Promise<{ path?: string[] }>;
}

const SAFE_SEGMENT = /^[a-zA-Z0-9._-]+$/;

async function proxy(request: Request, context: RouteContext) {
  if (!verifyAdminSession(request)) {
    return NextResponse.json(
      { error: "Administrator authentication is required." },
      { status: 401 },
    );
  }
  if (request.method !== "GET" && !assertSameOrigin(request)) {
    return NextResponse.json(
      { error: "Invalid request origin." },
      { status: 403 },
    );
  }
  const { path = [] } = await context.params;
  if (path.some((segment) => !SAFE_SEGMENT.test(segment))) {
    return NextResponse.json(
      { error: "Invalid Matching v2 review path." },
      { status: 400 },
    );
  }
  const upstreamUrl = new URL(
    `/api/v1/matching-v2/${path.join("/")}`,
    loadServerConfig().apiInternalUrl,
  );
  upstreamUrl.search = new URL(request.url).search;
  const body = request.method === "GET" ? undefined : await request.text();
  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: {
        ...(body ? { "content-type": "application/json" } : {}),
        ...(process.env.PRODUCT_PACK_ADMIN_TOKEN
          ? { "X-RCI-Admin-Token": process.env.PRODUCT_PACK_ADMIN_TOKEN }
          : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(90_000),
    });
    const payload = await upstream.text();
    return new NextResponse(payload, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "The Matching v2 review API is not currently reachable." },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
