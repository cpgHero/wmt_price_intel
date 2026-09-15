import { proxyCustomerAuthGet } from "../../../../lib/customer-auth-proxy";
import {
  ADMIN_ROUTE_CACHE_COOKIE_NAME,
  CUSTOMER_ROUTE_CACHE_COOKIE_NAME,
} from "../../../../lib/route-auth-cache";

export const dynamic = "force-dynamic";

function expiredRouteCacheCookie(name: string): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${name}=; HttpOnly; Max-Age=0; Path=/; SameSite=Strict${secure}`;
}

function isBackgroundAuthRequest(request: Request): boolean {
  const url = new URL(request.url);
  const accept = request.headers.get("accept") ?? "";
  const secFetchMode = request.headers.get("sec-fetch-mode") ?? "";
  const secFetchDest = request.headers.get("sec-fetch-dest") ?? "";
  return (
    url.searchParams.has("_rsc") ||
    request.headers.get("rsc") === "1" ||
    request.headers.get("next-router-prefetch") === "1" ||
    request.headers.get("purpose") === "prefetch" ||
    request.headers.get("sec-purpose") === "prefetch" ||
    (secFetchMode !== "" && secFetchMode !== "navigate") ||
    (secFetchDest !== "" && secFetchDest !== "document") ||
    (accept !== "" && !accept.includes("text/html"))
  );
}

export async function GET(request: Request) {
  if (isBackgroundAuthRequest(request)) {
    return Response.json(
      { error: "Customer logout requires a browser navigation." },
      { status: 401, headers: { "cache-control": "private, no-store" } },
    );
  }

  const response = await proxyCustomerAuthGet(request, "/api/auth/logout");
  const headers = new Headers(response.headers);
  headers.append(
    "set-cookie",
    expiredRouteCacheCookie(CUSTOMER_ROUTE_CACHE_COOKIE_NAME),
  );
  headers.append(
    "set-cookie",
    expiredRouteCacheCookie(ADMIN_ROUTE_CACHE_COOKIE_NAME),
  );
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
