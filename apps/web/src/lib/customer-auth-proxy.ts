import { loadServerConfig } from "./config";

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

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
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    const location = upstream.headers.get("location");
    if (location) responseHeaders.set("location", location);
    for (const cookie of setCookieHeaders(upstream.headers)) {
      responseHeaders.append("set-cookie", cookie);
    }
    const body = REDIRECT_STATUSES.has(upstream.status)
      ? null
      : await upstream.text();
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
