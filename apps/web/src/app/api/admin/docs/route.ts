import { NextResponse } from "next/server";

import { verifyAdminAccess } from "@/lib/admin-access";
import { platformDocumentation } from "@/lib/platform-docs";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!(await verifyAdminAccess(request))) {
    return NextResponse.json(
      { error: "Administrator authentication is required." },
      { status: 401 },
    );
  }
  return NextResponse.json(platformDocumentation, {
    headers: { "cache-control": "private, no-store" },
  });
}
