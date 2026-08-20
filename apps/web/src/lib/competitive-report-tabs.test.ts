import { describe, expect, it } from "vitest";

import {
  leadershipTab,
  leadershipTabs,
  legacyLeadershipTab,
} from "./competitive-report-tabs";

describe("competitive report leadership navigation", () => {
  it("exposes every leadership workspace as a unique first-class tab", () => {
    expect(leadershipTabs).toHaveLength(6);
    expect(new Set(leadershipTabs.map((tab) => tab.id)).size).toBe(6);
    expect(leadershipTabs.map((tab) => tab.label)).toEqual([
      "Competitive Footprint",
      "Matched Price Matrix",
      "Match Summary",
      "Price Ladders",
      "Store Comparisons",
      "Competitive History",
    ]);
  });

  it("maps first-class tab ids to the correct leadership workspace", () => {
    expect(leadershipTab("price-ladders")?.view).toBe("ladders");
    expect(leadershipTab("competitive-history")?.view).toBe("history");
    expect(leadershipTab("overview")).toBeNull();
  });

  it("keeps legacy Product Leadership URLs compatible", () => {
    expect(legacyLeadershipTab("match_group").id).toBe("match-summary");
    expect(legacyLeadershipTab("footprint").id).toBe("competitive-footprint");
    expect(legacyLeadershipTab("exceptions").id).toBe("store-comparisons");
    expect(legacyLeadershipTab("unsupported").id).toBe("competitive-footprint");
    expect(legacyLeadershipTab(null).id).toBe("competitive-footprint");
  });
});
