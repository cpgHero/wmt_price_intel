import { proxyCustomerAuthWebhookPost } from "@/lib/customer-auth-proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return proxyCustomerAuthWebhookPost(request, "/api/webhooks/workos");
}
