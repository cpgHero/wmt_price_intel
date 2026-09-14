import { proxyCustomerAuthGet } from "../../../../lib/customer-auth-proxy";

export const dynamic = "force-dynamic";

function isBackgroundAuthRequest(request: Request): boolean {
  const url = new URL(request.url);
  return (
    url.searchParams.has("_rsc") ||
    request.headers.get("rsc") === "1" ||
    request.headers.get("next-router-prefetch") === "1" ||
    request.headers.get("purpose") === "prefetch" ||
    request.headers.get("sec-purpose") === "prefetch"
  );
}

export async function GET(request: Request) {
  if (isBackgroundAuthRequest(request)) {
    return Response.json(
      { error: "Customer authentication requires a browser navigation." },
      { status: 401, headers: { "cache-control": "private, no-store" } },
    );
  }
  return proxyCustomerAuthGet(request, "/api/auth/login");
}
