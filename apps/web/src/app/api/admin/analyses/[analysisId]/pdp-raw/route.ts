import { NextResponse } from "next/server";

import { verifyAdminSession } from "@/lib/admin-session";
import { loadServerConfig } from "@/lib/config";

interface RouteContext {
  params: Promise<{ analysisId: string }>;
}

const SAFE_IDENTIFIER = /^[a-zA-Z0-9._-]+$/;

export async function GET(request: Request, context: RouteContext) {
  if (!verifyAdminSession(request)) {
    return NextResponse.json(
      { error: "Administrator authentication is required." },
      { status: 401 },
    );
  }
  const { analysisId } = await context.params;
  if (!SAFE_IDENTIFIER.test(analysisId)) {
    return NextResponse.json(
      { error: "Invalid analysis identifier." },
      { status: 400 },
    );
  }
  const upstreamUrl = new URL(
    `/api/v1/admin/analyses/${encodeURIComponent(analysisId)}/pdp-raw-export`,
    loadServerConfig().apiInternalUrl,
  );
  try {
    const upstream = await fetch(upstreamUrl, {
      method: "GET",
      headers: {
        ...(process.env.PRODUCT_PACK_ADMIN_TOKEN
          ? { "X-RCI-Admin-Token": process.env.PRODUCT_PACK_ADMIN_TOKEN }
          : {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(120_000),
    });
    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text();
      return new NextResponse(detail, {
        status: upstream.status,
        headers: {
          "content-type":
            upstream.headers.get("content-type") ?? "application/json",
          "cache-control": "private, no-store",
        },
      });
    }
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": "application/zip",
        "content-disposition":
          upstream.headers.get("content-disposition") ??
          'attachment; filename="raw_pdp_export.zip"',
        "cache-control": "private, no-store",
        "x-rci-pdp-snapshot-count":
          upstream.headers.get("x-rci-pdp-snapshot-count") ?? "0",
        "x-rci-pdp-successful-count":
          upstream.headers.get("x-rci-pdp-successful-count") ?? "0",
        "x-rci-provider-calls": "0",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "The raw Product Details export is not currently reachable." },
      { status: 503 },
    );
  }
}
