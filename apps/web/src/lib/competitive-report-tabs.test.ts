import { describe, expect, it } from "vitest";

import {
  leadershipTab,
  leadershipTabs,
  legacyLeadershipTab,
} from "./competitive-report-tabs";

describe("competitive report leadership navigation", () => {
  it("exposes every leadership workspace as a unique first-class tab", () => {
    expect(leadershipTabs).toHaveLength(8);
    expect(new Set(leadershipTabs.map((tab) => tab.id)).size).toBe(8);
    expect(leadershipTabs.map((tab) => tab.label)).toEqual([
      "Leadership Overview",
      "Competitive Footprint",
      "Match Group Analysis",
      "Price Ladders",
      "Store Comparisons",
      "Market Performance",
      "Competitive Exceptions",
      "Competitive History",
    ]);
  });

  it("maps first-class tab ids to the correct leadership workspace", () => {
    expect(leadershipTab("price-ladders")?.view).toBe("ladders");
    expect(leadershipTab("competitive-history")?.view).toBe("history");
    expect(leadershipTab("overview")).toBeNull();
  });

  it("keeps legacy Product Leadership URLs compatible", () => {
    expect(legacyLeadershipTab("match_group").id).toBe("match-group-analysis");
    expect(legacyLeadershipTab("unsupported").id).toBe("leadership-overview");
    expect(legacyLeadershipTab(null).id).toBe("leadership-overview");
  });
});
