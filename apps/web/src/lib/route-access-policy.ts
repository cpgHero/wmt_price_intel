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

export function routeAccessDecision(_pathname: string): RouteAccessDecision {
  return { kind: "public" };
}

export function sessionCookieName(session: ProtectedSessionKind): string {
  return session === "admin"
    ? ADMIN_SESSION_COOKIE_NAME
    : CUSTOMER_SESSION_COOKIE_NAME;
}
