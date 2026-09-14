export const ADMIN_SESSION_COOKIE_NAME = "rci_product_pack_admin";
export const CUSTOMER_SESSION_COOKIE_NAME = "cph_customer_session";

export type ProtectedSessionKind = "admin" | "customer";
export type ProtectedResponseMode = "json" | "redirect";

export type RouteAccessDecision =
  | { kind: "public" }
  | {
      kind: "protected";
      mode: ProtectedResponseMode;
      session: ProtectedSessionKind;
    };

const PUBLIC_EXACT_PATHS = new Set([
  "/",
  "/admin/login",
  "/api/admin/session",
  "/api/auth/callback",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/me",
  "/api/webhooks/workos",
  "/health",
  "/health/ready",
  "/robots.txt",
  "/sitemap.xml",
  "/favicon.ico",
]);

const PUBLIC_PREFIXES = [
  "/_next/",
  "/assets/",
  "/images/",
  "/public/",
  "/static/",
];

function normalizePathname(pathname: string): string {
  if (!pathname) return "/";
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

function isPublicAsset(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isApiRoute(pathname: string): boolean {
  return pathname === "/api" || pathname.startsWith("/api/");
}

export function routeAccessDecision(pathname: string): RouteAccessDecision {
  const normalizedPathname = normalizePathname(pathname);
  if (
    PUBLIC_EXACT_PATHS.has(normalizedPathname) ||
    isPublicAsset(normalizedPathname)
  ) {
    return { kind: "public" };
  }

  if (normalizedPathname.startsWith("/admin/")) {
    return { kind: "protected", mode: "redirect", session: "admin" };
  }

  if (normalizedPathname.startsWith("/api/admin/")) {
    return { kind: "protected", mode: "json", session: "admin" };
  }

  if (isApiRoute(normalizedPathname)) {
    return { kind: "protected", mode: "json", session: "customer" };
  }

  return { kind: "protected", mode: "redirect", session: "customer" };
}

export function sessionCookieName(session: ProtectedSessionKind): string {
  return session === "admin"
    ? ADMIN_SESSION_COOKIE_NAME
    : CUSTOMER_SESSION_COOKIE_NAME;
}
