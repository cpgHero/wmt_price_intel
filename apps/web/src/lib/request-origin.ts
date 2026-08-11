function firstHeaderValue(value: string | null): string | null {
  const first = value?.split(",", 1)[0]?.trim();
  return first || null;
}

function normalizedWebOrigin(value: string): string | null {
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

function addHostOrigin(
  origins: Set<string>,
  protocol: string,
  host: string | null,
): void {
  if (!host || (protocol !== "http:" && protocol !== "https:")) return;
  const candidate = normalizedWebOrigin(`${protocol}//${host}`);
  if (candidate) origins.add(candidate);
}

function addConfiguredOrigin(origins: Set<string>, value: string): void {
  const trimmed = value.trim();
  if (!trimmed) return;
  const candidate = normalizedWebOrigin(
    trimmed.includes("://") ? trimmed : `https://${trimmed}`,
  );
  if (candidate) origins.add(candidate);
}

/**
 * Validate browser mutations against the public request origin.
 *
 * Railway terminates TLS at its proxy, so `request.url` can contain an
 * internal HTTP origin while the browser correctly sends the public HTTPS
 * origin. We accept only exact origins derived from the request/proxy headers
 * or explicitly supplied deployment domains; wildcards are never allowed.
 */
export function assertSameOrigin(request: Request): boolean {
  const supplied = request.headers.get("origin");
  if (!supplied) return true;
  const suppliedOrigin = normalizedWebOrigin(supplied);
  if (!suppliedOrigin) return false;

  const requestUrl = new URL(request.url);
  const allowed = new Set<string>([requestUrl.origin]);
  const forwardedProtocol =
    firstHeaderValue(request.headers.get("x-forwarded-proto")) ??
    requestUrl.protocol;
  const protocol = forwardedProtocol.endsWith(":")
    ? forwardedProtocol
    : `${forwardedProtocol}:`;

  addHostOrigin(
    allowed,
    protocol,
    firstHeaderValue(request.headers.get("x-forwarded-host")),
  );
  addHostOrigin(
    allowed,
    protocol,
    firstHeaderValue(request.headers.get("host")),
  );

  for (const value of [
    process.env.RAILWAY_PUBLIC_DOMAIN,
    process.env.RAILWAY_STATIC_URL,
    process.env.RAILWAY_SERVICE_WEB_URL,
  ]) {
    if (value) addConfiguredOrigin(allowed, value);
  }
  for (const value of (process.env.PRODUCT_PACK_ALLOWED_ORIGINS ?? "").split(
    ",",
  )) {
    addConfiguredOrigin(allowed, value);
  }

  return allowed.has(suppliedOrigin);
}
