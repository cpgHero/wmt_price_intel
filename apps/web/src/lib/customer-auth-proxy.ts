import { loadServerConfig } from "./config";

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function acceptsHtml(request: Request): boolean {
  return (request.headers.get("accept") ?? "").includes("text/html");
}

function extractErrorMessage(raw: string): string {
  const customerSafe = (value: string) =>
    value.replaceAll(/workos/gi, "CPGHero identity");
  if (!raw.trim()) return "Customer authentication is not available right now.";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; error?: unknown };
    const detail =
      typeof parsed.detail === "string"
        ? parsed.detail
        : typeof parsed.error === "string"
          ? parsed.error
          : null;
    if (detail) return customerSafe(detail);
  } catch {
    // Fall through to a clipped plain-text response.
  }
  return customerSafe(raw.slice(0, 240));
}

function customerAuthErrorPage(status: number, raw: string): string {
  const message = escapeHtml(extractErrorMessage(raw));
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CPGHero customer access</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { min-height: 100vh; margin: 0; display: grid; place-items: center; background: radial-gradient(circle at 18% 12%, rgba(82, 230, 198, 0.16), transparent 30rem), #071115; color: #eef8fb; }
    main { width: min(34rem, calc(100vw - 2rem)); border: 1px solid rgba(148, 178, 190, 0.28); border-radius: 1.25rem; background: rgba(12, 28, 36, 0.88); box-shadow: 0 2rem 5rem rgba(0, 0, 0, 0.4); padding: 2rem; }
    .brand { color: #5fe6c8; font-size: 0.72rem; font-weight: 850; letter-spacing: 0.16em; text-transform: uppercase; }
    h1 { font-size: clamp(1.7rem, 5vw, 2.6rem); letter-spacing: -0.06em; line-height: 1; margin: 0.55rem 0 0.8rem; }
    p { color: #abc1cb; line-height: 1.55; margin: 0; }
    .detail { color: #eef8fb; margin-top: 1rem; }
    .status { border: 1px solid rgba(148, 178, 190, 0.26); border-radius: 999px; color: #abc1cb; display: inline-flex; font-size: 0.72rem; font-weight: 750; margin-top: 1.2rem; padding: 0.45rem 0.7rem; }
  </style>
</head>
<body>
  <main>
    <div class="brand">CPGHero customer access</div>
    <h1>Customer login is not ready yet.</h1>
    <p>The invitation link reached CPGHero, but customer authentication is still in a controlled rollout.</p>
    <p class="detail">${message}</p>
    <div class="status">Status ${status}</div>
  </main>
</body>
</html>`;
}

function upstreamHeaders(request: Request): Headers {
  const headers = new Headers();
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto) headers.set("x-forwarded-proto", forwardedProto);
  const forwardedHost = request.headers.get("x-forwarded-host");
  if (forwardedHost) headers.set("x-forwarded-host", forwardedHost);
  return headers;
}

function upstreamWebhookHeaders(request: Request): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const workosSignature = request.headers.get("workos-signature");
  if (workosSignature) headers.set("workos-signature", workosSignature);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto) headers.set("x-forwarded-proto", forwardedProto);
  const forwardedHost = request.headers.get("x-forwarded-host");
  if (forwardedHost) headers.set("x-forwarded-host", forwardedHost);
  return headers;
}

function setCookieHeaders(headers: Headers): string[] {
  const readable = headers as Headers & { getSetCookie?: () => string[] };
  const values = readable.getSetCookie?.();
  if (values?.length) return values;
  const fallback = headers.get("set-cookie");
  return fallback ? [fallback] : [];
}

export async function proxyCustomerAuthGet(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  const input = new URL(request.url);
  const upstreamUrl = new URL(upstreamPath, loadServerConfig().apiInternalUrl);
  upstreamUrl.search = input.search;
  try {
    const upstream = await fetch(upstreamUrl, {
      headers: upstreamHeaders(request),
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const responseHeaders = new Headers({
      "cache-control": "private, no-store",
    });
    const location = upstream.headers.get("location");
    if (location) responseHeaders.set("location", location);
    for (const cookie of setCookieHeaders(upstream.headers)) {
      responseHeaders.append("set-cookie", cookie);
    }
    const body = REDIRECT_STATUSES.has(upstream.status)
      ? null
      : await upstream.text();
    if (body !== null && upstream.status >= 400 && acceptsHtml(request)) {
      responseHeaders.set("content-type", "text/html; charset=utf-8");
      return new Response(customerAuthErrorPage(upstream.status, body), {
        status: upstream.status,
        headers: responseHeaders,
      });
    }
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    return new Response(body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { error: "The customer-auth API is not currently reachable." },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}

export async function proxyCustomerAuthWebhookPost(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  const upstreamUrl = new URL(upstreamPath, loadServerConfig().apiInternalUrl);
  const body = await request.text();
  try {
    const upstream = await fetch(upstreamUrl, {
      method: "POST",
      headers: upstreamWebhookHeaders(request),
      body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const responseHeaders = new Headers({
      "cache-control": "private, no-store",
    });
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { error: "The customer-auth webhook API is not currently reachable." },
      { status: 503, headers: { "cache-control": "private, no-store" } },
    );
  }
}
