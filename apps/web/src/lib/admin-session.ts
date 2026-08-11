import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";

export { assertSameOrigin } from "./request-origin";

const COOKIE_NAME = "rci_product_pack_admin";
const SESSION_SECONDS = 8 * 60 * 60;

function secret(): string | null {
  return process.env.PRODUCT_PACK_SESSION_SECRET ?? null;
}

function signature(payload: string, key: string): string {
  return createHmac("sha256", key).update(payload).digest("base64url");
}

function safeEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return (
    leftBytes.length === rightBytes.length &&
    timingSafeEqual(leftBytes, rightBytes)
  );
}

export function adminAuthenticationConfigured(): boolean {
  return Boolean(process.env.PRODUCT_PACK_ADMIN_PASSWORD && secret());
}

export function verifyAdminPassword(value: string): boolean {
  const expected = process.env.PRODUCT_PACK_ADMIN_PASSWORD;
  return Boolean(expected && safeEqual(value, expected));
}

export function createAdminSession(): string {
  const key = secret();
  if (!key)
    throw new Error("Product Pack administrator sessions are not configured.");
  const payload = Buffer.from(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS }),
  ).toString("base64url");
  return `${payload}.${signature(payload, key)}`;
}

export function verifyAdminSession(request: Request): boolean {
  if (!adminAuthenticationConfigured()) {
    return process.env.NODE_ENV !== "production";
  }
  const cookie = request.headers
    .get("cookie")
    ?.split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(`${COOKIE_NAME}=`))
    ?.slice(COOKIE_NAME.length + 1);
  const key = secret();
  if (!cookie || !key) return false;
  const [payload, suppliedSignature] = cookie.split(".");
  if (!payload || !suppliedSignature) return false;
  if (!safeEqual(signature(payload, key), suppliedSignature)) return false;
  try {
    const session = JSON.parse(
      Buffer.from(payload, "base64url").toString(),
    ) as {
      exp?: unknown;
    };
    return (
      typeof session.exp === "number" &&
      session.exp > Math.floor(Date.now() / 1000)
    );
  } catch {
    return false;
  }
}

export const adminSessionCookie = {
  name: COOKIE_NAME,
  maxAge: SESSION_SECONDS,
} as const;
