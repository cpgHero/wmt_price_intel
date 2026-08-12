import { NextResponse } from "next/server";

import { assertSameOrigin, verifyAdminSession } from "@/lib/admin-session";
import { loadServerConfig } from "@/lib/config";

async function proxy(request: Request) {
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
  const upstreamUrl = new URL(
    "/api/v1/admin/studies",
    loadServerConfig().apiInternalUrl,
  );
  const body = request.method === "GET" ? undefined : await request.text();
  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: {
        ...(body ? { "content-type": "application/json" } : {}),
        "X-RCI-Actor": "authenticated-study-admin",
        ...(process.env.PRODUCT_PACK_ADMIN_TOKEN
          ? { "X-RCI-Admin-Token": process.env.PRODUCT_PACK_ADMIN_TOKEN }
          : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
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
      { error: "The study-discovery API is not currently reachable." },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
