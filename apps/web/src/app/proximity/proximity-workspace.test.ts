import { describe, expect, it } from "vitest";

import type { LocationRetailer } from "@/lib/api";

import {
  recommendedComparisonScopeForStateCounts,
  selectCompetitorForProximityLoad,
} from "../../lib/proximity-workspace-model";

function retailer(
  id: string,
  displayName: string,
  locationCount: number,
): LocationRetailer {
  return {
    active: true,
    catalogued: true,
    country: "USA",
    display_name: displayName,
    id,
    location_count: locationCount,
  };
}

describe("proximity workspace selection rules", () => {
  const competitors = [
    retailer("cvs_us", "CVS", 9841),
    retailer("heb_us", "H-E-B", 365),
  ];

  it("preserves the selected competitor when only the radius changes", () => {
    expect(
      selectCompetitorForProximityLoad({
        competitorOptions: competitors,
        countryChanged: false,
        currentCompetitorRetailerId: "heb_us",
      }),
    ).toBe("heb_us");
  });

  it("uses the requested competitor when the user changes retailers", () => {
    expect(
      selectCompetitorForProximityLoad({
        competitorOptions: competitors,
        countryChanged: false,
        currentCompetitorRetailerId: "cvs_us",
        requestedCompetitorRetailerId: "heb_us",
      }),
    ).toBe("heb_us");
  });

  it("falls back to the first valid retailer when country changes invalidate the current retailer", () => {
    expect(
      selectCompetitorForProximityLoad({
        competitorOptions: competitors,
        countryChanged: true,
        currentCompetitorRetailerId: "canadian_tire_ca",
      }),
    ).toBe("cvs_us");
  });

  it("recommends competitor-footprint scope for sourced regional competitors", () => {
    expect(recommendedComparisonScopeForStateCounts(1, 52)).toBe(
      "competitor-footprint",
    );
    expect(recommendedComparisonScopeForStateCounts(9, 52)).toBe(
      "competitor-footprint",
    );
  });

  it("keeps all-Walmart scope for broad national competitors", () => {
    expect(recommendedComparisonScopeForStateCounts(45, 52)).toBe(
      "all-walmart",
    );
  });
});
