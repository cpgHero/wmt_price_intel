import { describe, expect, it } from "vitest";

import type { MatchReview } from "@/lib/api";

import {
  evidenceForProfile,
  productDetailRows,
  scopeMatchReview,
} from "./match-review-model";

const review: MatchReview = {
  analysis_id: "analysis",
  product_pack_id: "fresh_ground_beef",
  product_pack_version: "1.0.0",
  revision: 0,
  future_application: null,
  benchmark_retailer: { id: "walmart_us", name: "Walmart" },
  competitors: [{ id: "aldi_us", name: "ALDI" }],
  profiles: [
    {
      id: "strict",
      label: "Exact package",
      geography: "exact_zip",
      comparison_metric: "package_price",
    },
    {
      id: "unit",
      label: "Price per pound",
      geography: "exact_zip",
      comparison_metric: "price_per_lb",
    },
  ],
  products: [
    {
      retailer_id: "walmart_us",
      product_id: "w1",
      canonical_product_id: "walmart_us:w1",
      name: "Walmart beef",
      specification: { weight: "1 lb" },
    },
    {
      retailer_id: "walmart_us",
      product_id: "w2",
      canonical_product_id: "walmart_us:w2",
      name: "Walmart unmatched",
    },
    {
      retailer_id: "aldi_us",
      product_id: "a1",
      canonical_product_id: "aldi_us:a1",
      name: "ALDI beef",
    },
  ],
  connections: [
    {
      competitor_retailer_id: "aldi_us",
      source_profile_id: "strict",
      eligible_profile_ids: ["strict", "unit"],
      benchmark_product_id: "w1",
      competitor_product_id: "a1",
      status: "suggested",
      origin: "automatic",
      match_basis: "multiple",
      profile_evidence: [
        {
          profile_id: "strict",
          profile_label: "Exact package",
          comparison_metric: "package_price",
          match_basis: "exact_package",
          matches: 12,
          geographies: 10,
          match_attributes: { weight: "1 lb" },
          rationale: "Product Pack attributes align on weight",
        },
        {
          profile_id: "unit",
          profile_label: "Price per pound",
          comparison_metric: "price_per_lb",
          match_basis: "normalized_unit",
          matches: 11,
          geographies: 9,
          match_attributes: { form: "fresh" },
          rationale: "Product Pack attributes align on form",
        },
      ],
    },
  ],
  summary: { suggested: 1, confirmed: 0, rejected: 0, unmatched: 1 },
};

describe("match review scope", () => {
  it("scopes relationships and unmatched counts to retailer and lens", () => {
    const scope = scopeMatchReview(review, "aldi_us", "unit");

    expect(scope.connections).toHaveLength(1);
    expect(scope.summary).toEqual({
      suggested: 1,
      confirmed: 0,
      rejected: 0,
      unmatched: 1,
    });
    expect(
      scope.unmatchedBenchmarkProducts.map((row) => row.product_id),
    ).toEqual(["w2"]);
    expect(scope.unmatchedCompetitorProducts).toEqual([]);
  });

  it("returns the selected lens evidence and PDP detail rows", () => {
    expect(evidenceForProfile(review.connections[0], "unit")?.matches).toBe(11);
    expect(productDetailRows(review.products[0])).toContainEqual({
      section: "Specifications",
      label: "Weight",
      value: "1 lb",
    });
  });

  it("returns rejected products to manual matching", () => {
    const rejected = structuredClone(review);
    rejected.connections[0].status = "rejected";

    const scope = scopeMatchReview(rejected, "aldi_us", "strict");

    expect(
      scope.unmatchedBenchmarkProducts.map((row) => row.product_id),
    ).toEqual(["w1", "w2"]);
    expect(
      scope.unmatchedCompetitorProducts.map((row) => row.product_id),
    ).toEqual(["a1"]);
  });

  it("labels manual-pool products that are active in another lens", () => {
    const otherLens = structuredClone(review);
    otherLens.connections[0].eligible_profile_ids = ["unit"];

    const scope = scopeMatchReview(otherLens, "aldi_us", "strict");

    expect(
      scope.unmatchedBenchmarkProducts.map((row) => row.product_id),
    ).toContain("w1");
    expect(scope.crossLensMemberships["walmart_us:w1"]).toEqual([
      {
        profileId: "unit",
        profileLabel: "Price per pound",
        status: "suggested",
        counterpartProductId: "a1",
      },
    ]);
  });
});
