import { proxyCustomerAuthGet } from "@/lib/customer-auth-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyCustomerAuthGet(request, "/api/auth/callback");
}
