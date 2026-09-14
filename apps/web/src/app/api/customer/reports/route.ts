import { NextResponse } from "next/server";

import { loadServerConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

function upstreamHeaders(request: Request): Headers {
  const headers = new Headers({ accept: "application/json" });
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  return headers;
}

export async function GET(request: Request) {
  const input = new URL(request.url);
  const upstreamUrl = new URL(
    "/api/v1/customer/reports",
    loadServerConfig().apiInternalUrl,
  );
  upstreamUrl.search = input.search;
  try {
    const upstream = await fetch(upstreamUrl, {
      headers: upstreamHeaders(request),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "private, no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "The customer report API is not currently reachable." },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}
