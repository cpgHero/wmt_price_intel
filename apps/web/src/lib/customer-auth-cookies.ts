import type { NextRequest } from "next/server";

export function customerRouteCacheSecret(): string | null {
  return process.env.PRODUCT_PACK_SESSION_SECRET?.trim() || null;
}

export function unquoteCookieValue(
  value: string | undefined,
): string | undefined {
  if (value === undefined) return undefined;
  if (value.length >= 2 && value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1);
  }
  return value;
}

export function cookieValueFromCookieHeader(
  cookieHeader: string | null,
  name: string,
): string | undefined {
  if (!cookieHeader) return undefined;
  for (const segment of cookieHeader.split(";")) {
    const trimmed = segment.trim();
    if (!trimmed.startsWith(`${name}=`)) continue;
    return unquoteCookieValue(trimmed.slice(name.length + 1).trim());
  }
  return undefined;
}

export function cookieValueFromHeaders(
  headers: Headers,
  name: string,
): string | undefined {
  return cookieValueFromCookieHeader(headers.get("cookie"), name);
}

export function cookieValueFromRequest(
  request: NextRequest,
  name: string,
): string | undefined {
  const parsed = unquoteCookieValue(request.cookies.get(name)?.value);
  return parsed || cookieValueFromHeaders(request.headers, name);
}
