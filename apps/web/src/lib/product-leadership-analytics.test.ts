import { describe, expect, it } from "vitest";

import type { CompetitiveProductLeadership } from "./api";
import {
  leadershipExceptions,
  marketPerformance,
  relationshipEvidence,
  summarizeMatchGroup,
} from "./product-leadership-analytics";

type Outcome = CompetitiveProductLeadership["outcomes"][number];
type Relationship = CompetitiveProductLeadership["relationships"][number];

const baseLocation: Outcome["benchmark"] = {
  retailer_id: "walmart_us",
  retailer_name: "Walmart (US)",
  product_id: "w-1",
  product_name: "Benchmark milk",
  brand: "Great Value",
  brand_type: "private_label",
  brand_origin: "retailer_pack",
  brand_status: "suggested",
  image_url: null,
  product_url: null,
  scope_key: "walmart_us|store|1",
  location_kind: "store",
  store_number: "1",
  store_name: "Store 1",
  zipcode: "72712",
  city: "Bentonville",
  state: "AR",
  country: "USA",
  latitude: 36.37,
  longitude: -94.21,
  package_price: 3.49,
  regular_price: 3.49,
  discounted_price: null,
  is_sponsored: false,
  in_stock: true,
  offer_id: "offer-1",
  comparison_value: 3.49,
  observed_at: "2026-08-07T05:00:00Z",
};

function outcome(
  status: Outcome["status"],
  relationshipId: string | null,
): Outcome {
  return {
    id: `${status}-${relationshipId ?? "none"}`,
    status,
    benchmark: baseLocation,
    competitor:
      status === "unscored"
        ? null
        : {
            ...baseLocation,
            retailer_id: "aldi_us",
            retailer_name: "ALDI",
            product_id: "a-1",
            product_name: "Friendly Farms milk",
            brand: "Friendly Farms",
            scope_key: "aldi_us|store|2",
            store_number: "2",
            package_price: 3.19,
            comparison_value: 3.19,
          },
    relationship_id: relationshipId,
    distance_miles: status === "unscored" ? null : 1.2,
    competitor_minus_benchmark: status === "unscored" ? null : -0.3,
    comparison_value_reduction_to_lead: status === "losing" ? 0.31 : null,
  };
}

const relationships: Relationship[] = [
  {
    relationship_id: "r-1",
    competitor_id: "aldi_us",
    competitor_name: "ALDI",
    benchmark_product_id: "w-1",
    competitor_product_id: "a-1",
    profile_id: "strict",
    profile_label: "Strict package",
    comparison_metric: "package_price",
    comparison_unit: "USD/package",
    scope_mode: "global",
    scoped_benchmark_locations: 0,
  },
  {
    relationship_id: "r-2",
    competitor_id: "aldi_us",
    competitor_name: "ALDI",
    benchmark_product_id: "w-1",
    competitor_product_id: "a-2",
    profile_id: "strict",
    profile_label: "Strict package",
    comparison_metric: "package_price",
    comparison_unit: "USD/package",
    scope_mode: "location_scoped",
    scoped_benchmark_locations: 12,
  },
];

describe("product leadership analytics", () => {
  it("reconciles match-group coverage without treating configured matches as observed", () => {
    const rows = [outcome("losing", "r-1"), outcome("unscored", null)];
    expect(summarizeMatchGroup(relationships, rows)).toEqual({
      relationships: 2,
      competitorProducts: 2,
      competitorRetailers: 1,
      globalRelationships: 1,
      locationScopedRelationships: 1,
      relationshipsWithEvidence: 1,
    });
    expect(relationshipEvidence(relationships, rows)[0]).toMatchObject({
      benchmarkLocations: 1,
      competitorProductName: "Friendly Farms milk",
      competitorBrand: "Friendly Farms",
    });
  });

  it("orders current-snapshot exceptions by decision priority and size", () => {
    const rows = [
      outcome("unscored", null),
      outcome("at_risk", "r-1"),
      outcome("losing", "r-1"),
    ];
    expect(leadershipExceptions(rows).map((row) => row.type)).toEqual([
      "competitor_undercut",
      "narrow_lead",
      "insufficient_evidence",
    ]);
  });

  it("uses scored stores for market loss rates and observed stores for coverage", () => {
    const rows = marketPerformance([
      {
        id: "state:AR",
        level: "state",
        label: "AR",
        benchmark_observed_stores: 10,
        scored_stores: 8,
        coverage_rate: 0.8,
        leader_stores: 3,
        tied_stores: 1,
        at_risk_stores: 0,
        losing_stores: 4,
        unscored_stores: 2,
        leader_rate: 0.375,
        average_gap: -0.05,
        average_losing_gap: 0.2,
        maximum_losing_gap: 0.4,
      },
    ]);
    expect(rows[0]?.scoredRate).toBe(0.8);
    expect(rows[0]?.lossRate).toBe(0.5);
  });
});
