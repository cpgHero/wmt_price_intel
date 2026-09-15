import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET(request: Request) {
  const url = new URL(request.url);
  url.pathname = "/";
  url.search = "";
  return NextResponse.redirect(url);
}
