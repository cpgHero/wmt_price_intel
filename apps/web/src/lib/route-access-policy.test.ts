import { describe, expect, it } from "vitest";

import {
  ADMIN_SESSION_COOKIE_NAME,
  CUSTOMER_SESSION_COOKIE_NAME,
  routeAccessDecision,
  sessionCookieName,
} from "./route-access-policy";

describe("routeAccessDecision", () => {
  it("keeps auth, webhook, health, and framework assets public", () => {
    expect(routeAccessDecision("/")).toEqual({ kind: "public" });
    expect(routeAccessDecision("/api/auth/login")).toEqual({ kind: "public" });
    expect(routeAccessDecision("/api/auth/callback")).toEqual({
      kind: "public",
    });
    expect(routeAccessDecision("/api/auth/me")).toEqual({ kind: "public" });
    expect(routeAccessDecision("/api/admin/session")).toEqual({
      kind: "public",
    });
    expect(routeAccessDecision("/api/webhooks/workos")).toEqual({
      kind: "public",
    });
    expect(routeAccessDecision("/health")).toEqual({ kind: "public" });
    expect(routeAccessDecision("/health/ready")).toEqual({ kind: "public" });
    expect(routeAccessDecision("/_next/static/app.js")).toEqual({
      kind: "public",
    });
    expect(routeAccessDecision("/favicon.ico")).toEqual({ kind: "public" });
  });

  it("requires an administrator session for admin pages", () => {
    expect(routeAccessDecision("/admin/customer-auth")).toEqual({
      kind: "protected",
      mode: "redirect",
      session: "admin",
    });
    expect(routeAccessDecision("/admin/product-packs/drafts/draft-1")).toEqual({
      kind: "protected",
      mode: "redirect",
      session: "admin",
    });
  });

  it("keeps the dedicated admin login page public", () => {
    expect(routeAccessDecision("/admin/login")).toEqual({ kind: "public" });
    expect(routeAccessDecision("/admin/login/")).toEqual({ kind: "public" });
  });

  it("requires a customer session for app pages and app analytics", () => {
    for (const path of [
      "/customer",
      "/customer/reports/report-access-1",
      "/proximity",
      "/price-intelligence",
      "/price-monitoring/analysis-1",
      "/collections",
      "/data-quality",
      "/automation",
      "/workspace/matches",
    ]) {
      expect(routeAccessDecision(path)).toEqual({
        kind: "protected",
        mode: "redirect",
        session: "customer",
      });
    }
  });

  it("requires JSON authentication failures for protected API routes", () => {
    expect(routeAccessDecision("/api/customer/reports")).toEqual({
      kind: "protected",
      mode: "json",
      session: "customer",
    });
    expect(routeAccessDecision("/api/admin/customer-auth")).toEqual({
      kind: "protected",
      mode: "json",
      session: "admin",
    });
    expect(routeAccessDecision("/api/proximity/retailers")).toEqual({
      kind: "protected",
      mode: "json",
      session: "customer",
    });
    expect(routeAccessDecision("/api/price-monitoring/analysis-1")).toEqual({
      kind: "protected",
      mode: "json",
      session: "customer",
    });
    expect(
      routeAccessDecision("/api/price-monitoring/analysis-1/evidence.csv"),
    ).toEqual({
      kind: "protected",
      mode: "json",
      session: "customer",
    });
    expect(
      routeAccessDecision(
        "/api/customer/reports/access-1/price-monitoring/evidence.csv",
      ),
    ).toEqual({
      kind: "protected",
      mode: "json",
      session: "customer",
    });
  });
});

describe("sessionCookieName", () => {
  it("uses the existing admin and customer session cookie names", () => {
    expect(sessionCookieName("admin")).toBe(ADMIN_SESSION_COOKIE_NAME);
    expect(sessionCookieName("customer")).toBe(CUSTOMER_SESSION_COOKIE_NAME);
  });
});
