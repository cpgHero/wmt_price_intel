import { describe, expect, it } from "vitest";

import {
  ADMIN_SESSION_COOKIE_NAME,
  CUSTOMER_SESSION_COOKIE_NAME,
  routeAccessDecision,
  sessionCookieName,
} from "./route-access-policy";

describe("routeAccessDecision", () => {
  it("keeps route-boundary authentication disabled in legacy restore mode", () => {
    for (const path of [
      "/",
      "/proximity",
      "/price-intelligence",
      "/price-monitoring/analysis-1",
      "/analyses",
      "/analyses/analysis-1",
      "/collections",
      "/data-quality",
      "/automation",
      "/workspace/matches",
      "/admin/matching-v2",
      "/admin/product-packs/drafts/draft-1",
      "/api/proximity/retailers",
      "/api/price-monitoring/analysis-1",
      "/api/admin/matching-v2/review-queues",
    ]) {
      expect(routeAccessDecision(path)).toEqual({ kind: "public" });
    }
  });
});

describe("sessionCookieName", () => {
  it("retains the existing cookie names for dormant auth helpers", () => {
    expect(sessionCookieName("admin")).toBe(ADMIN_SESSION_COOKIE_NAME);
    expect(sessionCookieName("customer")).toBe(CUSTOMER_SESSION_COOKIE_NAME);
  });
});
