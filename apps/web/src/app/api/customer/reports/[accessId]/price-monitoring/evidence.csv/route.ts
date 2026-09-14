import { NextResponse } from "next/server";

import { loadServerConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

function upstreamHeaders(request: Request): Headers {
  const headers = new Headers({ accept: "text/csv" });
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  return headers;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ accessId: string }> },
) {
  const { accessId } = await context.params;
  const query = new URL(request.url).searchParams.toString();
  const upstreamUrl = new URL(
    `/api/v1/customer/reports/${encodeURIComponent(accessId)}/price-monitoring/evidence.csv?${query}`,
    loadServerConfig().apiInternalUrl,
  );
  try {
    const upstream = await fetch(upstreamUrl, {
      headers: upstreamHeaders(request),
      cache: "no-store",
      signal: AbortSignal.timeout(120_000),
    });
    const contentType = upstream.headers.get("content-type");
    if (!upstream.ok) {
      return new NextResponse(await upstream.text(), {
        status: upstream.status,
        headers: {
          "cache-control": "private, no-store",
          "content-type": contentType ?? "application/json",
        },
      });
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Cache-Control": "private, no-store",
        "Content-Disposition":
          upstream.headers.get("content-disposition") ??
          'attachment; filename="price-evidence.csv"',
        "Content-Type": contentType ?? "text/csv; charset=utf-8",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: "The customer evidence CSV API is not currently reachable.",
      },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}
