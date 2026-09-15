import { NextResponse } from "next/server";

import {
  adminSessionCookie,
  assertSameOrigin,
  createAdminSession,
  verifyAdminPassword,
} from "../../../../lib/admin-session";
import { adminSessionStatus } from "../../../../lib/admin-access";
import {
  cookieValueFromHeaders,
  customerRouteCacheSecret,
} from "../../../../lib/customer-auth-cookies";
import {
  ADMIN_ROUTE_CACHE_COOKIE_NAME,
  ADMIN_ROUTE_CACHE_SECONDS,
  createAdminRouteCacheCookie,
} from "../../../../lib/route-auth-cache";
import { CUSTOMER_SESSION_COOKIE_NAME } from "../../../../lib/route-access-policy";

export async function GET(request: Request) {
  const status = await adminSessionStatus(request);
  const response = NextResponse.json(status, {
    headers: { "cache-control": "private, no-store" },
  });
  if (status.authenticated && status.source === "customer_system") {
    const cacheCookie = await createAdminRouteCacheCookie(
      cookieValueFromHeaders(request.headers, CUSTOMER_SESSION_COOKIE_NAME),
      customerRouteCacheSecret(),
    );
    if (cacheCookie) {
      response.cookies.set(ADMIN_ROUTE_CACHE_COOKIE_NAME, cacheCookie, {
        httpOnly: true,
        maxAge: ADMIN_ROUTE_CACHE_SECONDS,
        path: "/",
        sameSite: "strict",
        secure: process.env.NODE_ENV === "production",
      });
    }
  }
  return response;
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
