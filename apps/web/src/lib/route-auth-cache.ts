export const CUSTOMER_ROUTE_CACHE_COOKIE_NAME = "cph_customer_route_auth";
export const CUSTOMER_ROUTE_CACHE_SECONDS = 60;

const TOKEN_VERSION = "v1";

function textBytes(value: string): ArrayBuffer {
  const bytes = new TextEncoder().encode(value);
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
}

function base64UrlEncode(bytes: ArrayBuffer): string {
  let binary = "";
  for (const byte of new Uint8Array(bytes)) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

async function hmacSha256(message: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    textBytes(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return base64UrlEncode(
    await crypto.subtle.sign("HMAC", key, textBytes(message)),
  );
}

function usable(value: string | null | undefined): value is string {
  return Boolean(value?.trim());
}

export async function createCustomerRouteCacheCookie(
  sessionCookie: string | null | undefined,
  secret: string | null | undefined,
  nowSeconds = Math.floor(Date.now() / 1000),
): Promise<string | null> {
  if (!usable(sessionCookie) || !usable(secret)) return null;

  const expiresAt = nowSeconds + CUSTOMER_ROUTE_CACHE_SECONDS;
  const sessionFingerprint = await hmacSha256(
    `session:${sessionCookie}`,
    secret,
  );
  const unsignedPayload = `${TOKEN_VERSION}.${expiresAt}.${sessionFingerprint}`;
  const signature = await hmacSha256(`route-cache:${unsignedPayload}`, secret);

  return `${unsignedPayload}.${signature}`;
}

export async function verifyCustomerRouteCacheCookie(
  cacheCookie: string | null | undefined,
  sessionCookie: string | null | undefined,
  secret: string | null | undefined,
  nowSeconds = Math.floor(Date.now() / 1000),
): Promise<boolean> {
  if (!usable(cacheCookie) || !usable(sessionCookie) || !usable(secret)) {
    return false;
  }

  const [version, expiresAtText, sessionFingerprint, signature, ...extra] =
    cacheCookie.split(".");
  if (
    extra.length > 0 ||
    version !== TOKEN_VERSION ||
    !expiresAtText ||
    !sessionFingerprint ||
    !signature
  ) {
    return false;
  }

  const expiresAt = Number(expiresAtText);
  if (!Number.isSafeInteger(expiresAt) || expiresAt <= nowSeconds) {
    return false;
  }

  const expectedSessionFingerprint = await hmacSha256(
    `session:${sessionCookie}`,
    secret,
  );
  if (sessionFingerprint !== expectedSessionFingerprint) return false;

  const unsignedPayload = `${version}.${expiresAtText}.${sessionFingerprint}`;
  const expectedSignature = await hmacSha256(
    `route-cache:${unsignedPayload}`,
    secret,
  );
  return signature === expectedSignature;
}
