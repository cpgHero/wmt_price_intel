import { NextResponse } from "next/server";

import { verifyAdminSession } from "@/lib/admin-session";
import { platformDocumentation } from "@/lib/platform-docs";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!verifyAdminSession(request)) {
    return NextResponse.json(
      { error: "Administrator authentication is required." },
      { status: 401 },
    );
  }
  return NextResponse.json(platformDocumentation, {
    headers: { "cache-control": "private, no-store" },
  });
}
