import {
  cookieValueFromHeaders,
  customerRouteCacheSecret,
} from "../../../../lib/customer-auth-cookies";
import { proxyCustomerAuthGet } from "../../../../lib/customer-auth-proxy";
import {
  CUSTOMER_ROUTE_CACHE_COOKIE_NAME,
  CUSTOMER_ROUTE_CACHE_SECONDS,
  createCustomerRouteCacheCookie,
} from "../../../../lib/route-auth-cache";
import { CUSTOMER_SESSION_COOKIE_NAME } from "../../../../lib/route-access-policy";

export const dynamic = "force-dynamic";

function serializedRouteCacheCookie(cacheCookie: string): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return (
    [
      `${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=${cacheCookie}`,
      "HttpOnly",
      `Max-Age=${CUSTOMER_ROUTE_CACHE_SECONDS}`,
      "Path=/",
      "SameSite=Strict",
    ].join("; ") + secure
  );
}

export async function GET(request: Request) {
  const response = await proxyCustomerAuthGet(request, "/api/v1/me");
  if (!response.ok) return response;

  const sessionCookie = cookieValueFromHeaders(
    request.headers,
    CUSTOMER_SESSION_COOKIE_NAME,
  );
  const routeCacheCookie = await createCustomerRouteCacheCookie(
    sessionCookie,
    customerRouteCacheSecret(),
  );
  if (!routeCacheCookie) return response;

  const headers = new Headers(response.headers);
  headers.append("set-cookie", serializedRouteCacheCookie(routeCacheCookie));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
