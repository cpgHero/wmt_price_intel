import { describe, expect, it } from "vitest";

import {
  BROAD_WALMART_DISTRIBUTION_THRESHOLD,
  DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
  type CanonicalProductRelationship,
  canonicalCompetitorOptions,
  filterCanonicalRelationships,
  groupCanonicalRelationshipsByOutcome,
  relationshipSearchText,
  summarizeCanonicalBrandTypes,
} from "./canonical-report-focus";

function relationship(overrides: {
  id: string;
  title: string;
  outcome: CanonicalProductRelationship["comparison"]["outcome"];
  brandType?: CanonicalProductRelationship["benchmark_product"]["brand_type"];
  competitor?: string;
  distribution?: number;
  priceDeltaPercent?: number;
}): CanonicalProductRelationship {
  const competitor = overrides.competitor ?? "aldi_us";
  return {
    relationship_id: overrides.id,
    benchmark_product: {
      retailer_id: "walmart_us",
      retailer_product_id: `wmt-${overrides.id}`,
      title: overrides.title,
      url: null,
      image_url: null,
      brand: "Great Value",
      brand_type: overrides.brandType ?? "private_label",
      seller_status: "qualified",
      package: {
        label: "package",
        unit_basis: "package",
      },
      price: {
        reporting_price: 1,
        reporting_price_label: "$1.00/package",
        package_price: 1,
        normalized_unit_price: null,
        regular_price: null,
        discounted_price: null,
        currency: "USD",
      },
      distribution: {
        physical_store_distribution_count: overrides.distribution ?? 100,
        service_area_presence_count: 0,
        searched_store_count: null,
      },
    },
    competitor_product: {
      retailer_id: competitor,
      retailer_product_id: `${competitor}-${overrides.id}`,
      title: `${overrides.title} competitor`,
      url: null,
      image_url: null,
      brand: "Competitor brand",
      brand_type: "private_label",
      seller_status: "not_applicable",
      package: {
        label: "package",
        unit_basis: "package",
      },
      price: {
        reporting_price: 1.1,
        reporting_price_label: "$1.10/package",
        package_price: 1.1,
        normalized_unit_price: null,
        regular_price: null,
        discounted_price: null,
        currency: "USD",
      },
      distribution: {
        physical_store_distribution_count: 90,
        service_area_presence_count: 0,
        searched_store_count: null,
      },
    },
    comparison: {
      comparison_basis: "spec_equivalent",
      unit_basis: "package",
      price_delta: -0.1,
      price_delta_percent: overrides.priceDeltaPercent ?? -0.1,
      outcome: overrides.outcome,
      match_certification: {
        status: "certified_comparable",
        source: "matching_v2_gold_set",
      },
    },
    evidence_refs: [{ kind: "match_decision", id: overrides.id }],
  };
}

describe("canonical report relationship focus helpers", () => {
  const rows = [
    relationship({
      id: "loss-broad-small-gap",
      title: "Broad Walmart Loss",
      outcome: "competitor_wins",
      distribution: 4_200,
      priceDeltaPercent: 0.03,
    }),
    relationship({
      id: "win-broad-large-gap",
      title: "Broad Walmart Win",
      outcome: "walmart_wins",
      distribution: 4_500,
      priceDeltaPercent: -0.2,
    }),
    relationship({
      id: "loss-limited-large-gap",
      title: "Limited Walmart Loss",
      outcome: "competitor_wins",
      brandType: "national",
      competitor: "target_us",
      distribution: 250,
      priceDeltaPercent: 0.5,
    }),
    relationship({
      id: "parity",
      title: "Parity Item",
      outcome: "parity",
      distribution: 2_000,
      priceDeltaPercent: 0,
    }),
  ];

  it("defaults to an action-priority sort that leads with Walmart losses", () => {
    const filtered = filterCanonicalRelationships(rows, {
      ...DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
    });

    expect(filtered.map((row) => row.relationship_id)).toEqual([
      "loss-broad-small-gap",
      "loss-limited-large-gap",
      "win-broad-large-gap",
      "parity",
    ]);
  });

  it("filters by outcome, brand type, competitor, distribution, and search text", () => {
    const filtered = filterCanonicalRelationships(rows, {
      ...DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
      query: "limited",
      outcome: "competitor_wins",
      brandType: "national",
      competitorRetailerId: "target_us",
      minimumWalmartDistribution: 200,
    });

    expect(filtered.map((row) => row.relationship_id)).toEqual([
      "loss-limited-large-gap",
    ]);
  });

  it("can isolate broad positive-price Walmart products", () => {
    const filtered = filterCanonicalRelationships(rows, {
      ...DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
      minimumWalmartDistribution: BROAD_WALMART_DISTRIBUTION_THRESHOLD,
      sort: "distribution_desc",
    });

    expect(filtered.map((row) => row.relationship_id)).toEqual([
      "win-broad-large-gap",
      "loss-broad-small-gap",
      "parity",
    ]);
  });

  it("groups filtered relationships by buyer-facing outcome", () => {
    expect(groupCanonicalRelationshipsByOutcome(rows)).toMatchObject({
      walmartLosses: [
        { relationship_id: "loss-broad-small-gap" },
        { relationship_id: "loss-limited-large-gap" },
      ],
      walmartWins: [{ relationship_id: "win-broad-large-gap" }],
      parity: [{ relationship_id: "parity" }],
    });
  });

  it("searches product names, ids, brand types, competitors, and outcomes", () => {
    expect(relationshipSearchText(rows[2]!)).toContain("target_us");
    expect(relationshipSearchText(rows[2]!)).toContain("national");
    expect(relationshipSearchText(rows[2]!)).toContain("limited walmart loss");
    expect(relationshipSearchText(rows[2]!)).toContain("competitor_wins");
  });

  it("returns stable sorted competitor options", () => {
    expect(canonicalCompetitorOptions(rows)).toEqual(["aldi_us", "target_us"]);
  });

  it("summarizes included relationships by Walmart brand role", () => {
    expect(summarizeCanonicalBrandTypes(rows)).toEqual([
      {
        brandType: "private_label",
        broadWalmartLosses: 1,
        relationships: 3,
        walmartLosses: 1,
        walmartWins: 1,
      },
      {
        brandType: "national",
        broadWalmartLosses: 0,
        relationships: 1,
        walmartLosses: 1,
        walmartWins: 0,
      },
    ]);
  });
});
