import { NextResponse } from "next/server";

import {
  adminAuthenticationConfigured,
  adminSessionCookie,
  assertSameOrigin,
  createAdminSession,
  verifyAdminPassword,
  verifyAdminSession,
} from "@/lib/admin-session";

export async function GET(request: Request) {
  return NextResponse.json({
    configured: adminAuthenticationConfigured(),
    authenticated: verifyAdminSession(request),
  });
}

export async function POST(request: Request) {
  if (!assertSameOrigin(request)) {
    return NextResponse.json(
      { error: "Invalid request origin." },
      { status: 403 },
    );
  }
  const body = (await request.json()) as { password?: unknown };
  if (
    typeof body.password !== "string" ||
    !verifyAdminPassword(body.password)
  ) {
    return NextResponse.json(
      { error: "Administrator credentials were not accepted." },
      { status: 401 },
    );
  }
  const response = NextResponse.json({ authenticated: true });
  response.cookies.set(adminSessionCookie.name, createAdminSession(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: adminSessionCookie.maxAge,
  });
  return response;
}

export async function DELETE(request: Request) {
  if (!assertSameOrigin(request)) {
    return NextResponse.json(
      { error: "Invalid request origin." },
      { status: 403 },
    );
  }
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(adminSessionCookie.name, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
