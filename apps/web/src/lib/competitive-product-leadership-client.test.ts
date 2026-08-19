import { describe, expect, it } from "vitest";

import { competitiveProductLeadershipPath } from "./competitive-product-leadership-client";

describe("competitive product leadership client", () => {
  it("builds one canonical request path for prewarm and visible views", () => {
    expect(
      competitiveProductLeadershipPath({
        analysisId: "egg report/1",
        competitorId: "target_us",
        profileId: "compatible",
        productId: "10449724",
        radiusMiles: 5,
        stateFilter: "TX",
        cityFilter: "Dallas",
      }),
    ).toBe(
      "/api/analyses/egg%20report%2F1/competitive-product-leadership?competitor=target_us&profile=compatible&product=10449724&radius_miles=5&state=TX&city=Dallas",
    );
  });

  it("never applies a city without its state", () => {
    expect(
      competitiveProductLeadershipPath({
        analysisId: "egg-report",
        competitorId: "all",
        profileId: "strict",
        productId: "391346672",
        radiusMiles: 3,
        cityFilter: "Bentonville",
      }),
    ).not.toContain("city=");
  });
});
