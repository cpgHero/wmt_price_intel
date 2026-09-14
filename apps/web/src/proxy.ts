import { NextResponse, type NextRequest } from "next/server";

import {
  routeAccessDecision,
  sessionCookieName,
  type ProtectedSessionKind,
} from "@/lib/route-access-policy";

function returnTo(request: NextRequest): string {
  return `${request.nextUrl.pathname}${request.nextUrl.search}`;
}

function redirectToAdminLogin(request: NextRequest): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = "/admin/login";
  url.search = "";
  url.searchParams.set("return_to", returnTo(request));
  return NextResponse.redirect(url);
}

function redirectToCustomerLogin(request: NextRequest): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = "/api/auth/login";
  url.search = "";
  url.searchParams.set("return_to", returnTo(request));
  return NextResponse.redirect(url);
}

function unauthorizedJson(session: "admin" | "customer"): NextResponse {
  const subject = session === "admin" ? "Administrator" : "Customer";
  return NextResponse.json(
    { error: `${subject} authentication is required.` },
    { status: 401, headers: { "cache-control": "private, no-store" } },
  );
}

function hasTestRouteBypass(request: NextRequest): boolean {
  const token = process.env.CPGHERO_WEB_ROUTE_AUTH_TEST_BYPASS_TOKEN?.trim();
  return Boolean(
    token && request.headers.get("x-cpghero-route-auth-test") === token,
  );
}

async function validateSession(
  request: NextRequest,
  session: ProtectedSessionKind,
): Promise<boolean> {
  const validationUrl = request.nextUrl.clone();
  validationUrl.pathname =
    session === "admin" ? "/api/admin/session" : "/api/auth/me";
  validationUrl.search = "";

  try {
    const response = await fetch(validationUrl, {
      cache: "no-store",
      headers: {
        accept: "application/json",
        cookie: request.headers.get("cookie") ?? "",
      },
    });
    if (!response.ok) return false;
    if (session === "customer") return true;

    const payload = (await response.json()) as { authenticated?: unknown };
    return payload.authenticated === true;
  } catch {
    return false;
  }
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  if (hasTestRouteBypass(request)) {
    return NextResponse.next();
  }

  const decision = routeAccessDecision(request.nextUrl.pathname);
  if (decision.kind === "public") {
    return NextResponse.next();
  }

  const cookieName = sessionCookieName(decision.session);
  if (
    request.cookies.has(cookieName) &&
    (await validateSession(request, decision.session))
  ) {
    return NextResponse.next();
  }

  if (decision.mode === "json") {
    return unauthorizedJson(decision.session);
  }

  if (decision.session === "admin") {
    return redirectToAdminLogin(request);
  }

  return redirectToCustomerLogin(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
