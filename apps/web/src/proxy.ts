import { NextResponse, type NextRequest } from "next/server";

/*
 * Legacy restore mode.
 *
 * The WorkOS/customer route boundary is intentionally disabled because it
 * caused repeated browser redirect loops. App shell and analytics pages load
 * directly. Dormant customer page routes are hard-redirected to legacy app
 * destinations without validating WorkOS or route-cache cookies. Administrator
 * API handlers continue to enforce the legacy CPGHero admin password session
 * via verifyAdminAccess().
 */
export function proxy(request: NextRequest): NextResponse {
  const pathname = request.nextUrl.pathname;
  if (pathname === "/customer" || pathname === "/customer/") {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }
  if (
    pathname === "/customer/reports" ||
    pathname.startsWith("/customer/reports/")
  ) {
    const url = request.nextUrl.clone();
    url.pathname = "/analyses";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
