import { NextResponse } from "next/server";

import { verifyAdminAccess } from "@/lib/admin-access";
import { loadServerConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!(await verifyAdminAccess(request))) {
    return NextResponse.json(
      { error: "Administrator authentication is required." },
      { status: 401 },
    );
  }
  const input = new URL(request.url);
  const upstreamUrl = new URL(
    "/api/v1/admin/customer-provisioning/account-foundation",
    loadServerConfig().apiInternalUrl,
  );
  upstreamUrl.search = input.search;
  try {
    const upstream = await fetch(upstreamUrl, {
      headers: process.env.PRODUCT_PACK_ADMIN_TOKEN
        ? { "X-RCI-Admin-Token": process.env.PRODUCT_PACK_ADMIN_TOKEN }
        : {},
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
      {
        error:
          "The customer account foundation API is not currently reachable.",
      },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}
