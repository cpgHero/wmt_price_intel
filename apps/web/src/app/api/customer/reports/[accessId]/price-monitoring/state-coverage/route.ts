import { NextResponse } from "next/server";

import type { JsonObject } from "@/lib/api";
import { loadServerConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

function upstreamHeaders(request: Request): Headers {
  const headers = new Headers({
    accept: "application/json",
    "content-type": "application/json",
  });
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  return headers;
}

export async function POST(
  request: Request,
  context: { params: Promise<{ accessId: string }> },
) {
  const { accessId } = await context.params;
  const upstreamUrl = new URL(
    `/api/v1/customer/reports/${encodeURIComponent(accessId)}/price-monitoring/state-coverage`,
    loadServerConfig().apiInternalUrl,
  );
  try {
    const upstream = await fetch(upstreamUrl, {
      body: JSON.stringify((await request.json()) as JsonObject),
      headers: upstreamHeaders(request),
      cache: "no-store",
      method: "POST",
      signal: AbortSignal.timeout(120_000),
    });
    const payload = (await upstream.json()) as JsonObject;
    return NextResponse.json(payload, {
      status: upstream.status,
      headers: { "cache-control": "private, no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        error: "The customer state coverage API is not currently reachable.",
      },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}
