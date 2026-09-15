import { NextResponse } from "next/server";
import { publicRequestOrigin } from "../../../../lib/request-origin";

export const dynamic = "force-dynamic";

export function GET(request: Request) {
  const url = new URL("/", publicRequestOrigin(request));
  return NextResponse.redirect(url);
}
