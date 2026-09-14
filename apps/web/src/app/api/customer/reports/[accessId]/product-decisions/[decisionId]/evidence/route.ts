import { NextResponse } from "next/server";

import type { ProductEvidenceResponse } from "@/lib/api";
import { loadServerConfig } from "@/lib/config";
import {
  productEvidenceCsv,
  productEvidenceFilename,
} from "@/lib/evidence-csv";

export const dynamic = "force-dynamic";

function upstreamHeaders(request: Request): Headers {
  const headers = new Headers({ accept: "application/json" });
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  return headers;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ accessId: string; decisionId: string }> },
) {
  const { accessId, decisionId } = await context.params;
  const upstreamUrl = new URL(
    `/api/v1/customer/reports/${encodeURIComponent(accessId)}/product-decisions/${encodeURIComponent(decisionId)}/evidence`,
    loadServerConfig().apiInternalUrl,
  );
  try {
    const upstream = await fetch(upstreamUrl, {
      headers: upstreamHeaders(request),
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
    const payload = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(payload, {
        status: upstream.status,
        headers: { "cache-control": "private, no-store" },
      });
    }
    if (new URL(request.url).searchParams.get("format") === "csv") {
      const evidence = payload as ProductEvidenceResponse;
      return new Response(productEvidenceCsv(evidence), {
        headers: {
          "Cache-Control": "private, no-store",
          "Content-Disposition": `attachment; filename="${productEvidenceFilename(evidence)}"`,
          "Content-Type": "text/csv; charset=utf-8",
        },
      });
    }
    return NextResponse.json(payload, {
      headers: { "cache-control": "private, no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        error: "The customer product evidence API is not currently reachable.",
      },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}
