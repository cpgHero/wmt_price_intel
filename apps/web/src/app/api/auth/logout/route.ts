import { proxyCustomerAuthGet } from "../../../../lib/customer-auth-proxy";
import { CUSTOMER_ROUTE_CACHE_COOKIE_NAME } from "../../../../lib/route-auth-cache";

export const dynamic = "force-dynamic";

function expiredRouteCacheCookie(): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=; HttpOnly; Max-Age=0; Path=/; SameSite=Strict${secure}`;
}

export async function GET(request: Request) {
  const response = await proxyCustomerAuthGet(request, "/api/auth/logout");
  const headers = new Headers(response.headers);
  headers.append("set-cookie", expiredRouteCacheCookie());
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
