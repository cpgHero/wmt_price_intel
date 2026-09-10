import { describe, expect, it } from "vitest";

import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";

import {
  canonicalReportChecklist,
  canonicalReportIntegrityIssues,
} from "./canonical-report-qa";

type CanonicalDataset = RetailCompetitiveIntelligenceCanonicalReportDataset;

function dataset(overrides: Partial<CanonicalDataset> = {}): CanonicalDataset {
  return {
    schema_version: "1.0.0",
    report_id: "report-1",
    analysis_id: "analysis-1",
    generated_at: "2026-09-09T18:00:00Z",
    evidence_observed_at: "2026-09-09T17:00:00Z",
    benchmark_retailer: { id: "walmart_us", name: "Walmart (US)" },
    competitors: [{ id: "aldi_us", name: "ALDI (US)" }],
    product_pack: { id: "fresh_bananas", name: "Bananas", version: "1.0.0" },
    retailer_packs: [],
    contracts: {
      distribution: {
        version: "1.0.0",
        basis: "positive_price_store_search_result",
        grain: "retailer_product_id_x_store_id",
        deduplication: "distinct_store_id_per_product",
        price_rule: "price_gt_zero",
        inventory_claim: false,
        stock_status_used: false,
        sponsorship_used: false,
        extrapolation: false,
      },
      service_area_presence: {
        version: "1.0.0",
        basis: "positive_price_service_area_search_result",
        grain: "retailer_product_id_x_service_area",
        price_rule: "price_gt_zero",
        presented_as_store_count: false,
      },
    },
    readiness: { status: "ready", blocking_reasons: [], warnings: [] },
    seller_governance: {
      status: "passed",
      benchmark_requirement: "qualified_seller_or_not_applicable",
      unverified_product_count: 0,
      excluded_product_count: 0,
    },
    price_normalization: {
      status: "passed",
      unit_basis: "package",
      zero_price_sentinel_rule: "zero_regular_or_discounted_price_is_missing",
      invalid_price_record_count: 0,
    },
    summary: {
      relationship_count: 0,
      walmart_win_count: 0,
      competitor_win_count: 0,
      parity_count: 0,
      unscored_count: 0,
      excluded_relationship_count: 0,
    },
    product_relationships: [],
    excluded_relationships: [],
    qa: {
      included_relationship_count: 0,
      excluded_relationship_count: 0,
      invalid_price_record_count: 0,
      unverified_seller_product_count: 0,
      products_without_image_count: 0,
      products_without_valid_distribution_count: 0,
      match_certification_complete: true,
      product_pack_coverage_status: "passed",
      retailer_coverage_status: "passed",
    },
    ...overrides,
  };
}

function relationship(
  overrides: Partial<CanonicalDataset["product_relationships"][number]> = {},
): CanonicalDataset["product_relationships"][number] {
  return {
    relationship_id: "relationship-1",
    benchmark_product: {
      retailer_id: "walmart_us",
      retailer_product_id: "44390948",
      title: "Fresh Banana, Each",
      url: "https://www.walmart.com/ip/44390948",
      image_url: "https://i5.walmartimages.com/banana.jpeg",
      brand: "Great Value",
      brand_type: "private_label",
      seller_status: "qualified",
      package: { label: "package", unit_basis: "package" },
      price: {
        reporting_price: 0.2,
        reporting_price_label: "$0.20/package",
        package_price: 0.2,
        normalized_unit_price: null,
        regular_price: null,
        discounted_price: null,
        currency: "USD",
      },
      distribution: {
        physical_store_distribution_count: 4_294,
        service_area_presence_count: 0,
        searched_store_count: null,
      },
    },
    competitor_product: {
      retailer_id: "aldi_us",
      retailer_product_id: "banana-each",
      title: "Banana, Each",
      url: "https://www.aldi.us/banana",
      image_url: "https://www.aldi.us/banana.jpeg",
      brand: "ALDI",
      brand_type: "private_label",
      seller_status: "not_applicable",
      package: { label: "package", unit_basis: "package" },
      price: {
        reporting_price: 0.27,
        reporting_price_label: "$0.27/package",
        package_price: 0.27,
        normalized_unit_price: null,
        regular_price: null,
        discounted_price: null,
        currency: "USD",
      },
      distribution: {
        physical_store_distribution_count: 2_100,
        service_area_presence_count: 0,
        searched_store_count: null,
      },
    },
    comparison: {
      comparison_basis: "spec_equivalent",
      unit_basis: "package",
      price_delta: -0.07,
      price_delta_percent: -0.2592592593,
      outcome: "walmart_wins",
      match_certification: {
        status: "certified_comparable",
        source: "matching_v2_gold_set",
      },
    },
    evidence_refs: [{ kind: "match_decision", id: "relationship-1" }],
    ...overrides,
  };
}

describe("canonicalReportChecklist", () => {
  it("marks a clean canonical dataset as passed", () => {
    expect(
      canonicalReportChecklist(dataset()).map((item) => item.status),
    ).toEqual(["passed", "passed", "passed", "passed", "passed", "passed"]);
  });

  it("blocks when readiness or seller governance blocks the report", () => {
    const checklist = canonicalReportChecklist(
      dataset({
        readiness: {
          status: "blocked",
          blocking_reasons: [
            {
              code: "missing_report",
              message: "Report data is incomplete.",
            },
          ],
          warnings: [],
        },
        seller_governance: {
          status: "blocked",
          benchmark_requirement: "qualified_seller_or_not_applicable",
          unverified_product_count: 1,
          excluded_product_count: 1,
        },
      }),
    );

    expect(checklist.find((item) => item.id === "readiness")).toMatchObject({
      status: "blocked",
      detail: "Report data is incomplete.",
    });
    expect(
      checklist.find((item) => item.id === "seller-governance"),
    ).toMatchObject({
      status: "blocked",
      detail:
        "1 benchmark products excluded because seller qualification failed.",
    });
  });

  it("warns for exclusions, pending certification, and missing images", () => {
    const checklist = canonicalReportChecklist(
      dataset({
        price_normalization: {
          status: "passed_with_exclusions",
          unit_basis: "package",
          zero_price_sentinel_rule:
            "zero_regular_or_discounted_price_is_missing",
          invalid_price_record_count: 2,
        },
        qa: {
          included_relationship_count: 3,
          excluded_relationship_count: 3,
          invalid_price_record_count: 2,
          unverified_seller_product_count: 0,
          products_without_image_count: 1,
          products_without_valid_distribution_count: 1,
          match_certification_complete: false,
          product_pack_coverage_status: "passed",
          retailer_coverage_status: "passed_with_exclusions",
        },
      }),
    );

    expect(
      checklist
        .filter((item) => item.status === "warning")
        .map((item) => item.id),
    ).toEqual([
      "price-normalization",
      "distribution-evidence",
      "match-certification",
      "product-images",
    ]);
  });
});

describe("canonicalReportIntegrityIssues", () => {
  it("accepts a clean canonical dataset", () => {
    expect(
      canonicalReportIntegrityIssues(
        dataset({
          summary: {
            relationship_count: 1,
            walmart_win_count: 1,
            competitor_win_count: 0,
            parity_count: 0,
            unscored_count: 0,
            excluded_relationship_count: 0,
          },
          product_relationships: [relationship()],
          qa: {
            included_relationship_count: 1,
            excluded_relationship_count: 0,
            invalid_price_record_count: 0,
            unverified_seller_product_count: 0,
            products_without_image_count: 0,
            products_without_valid_distribution_count: 0,
            match_certification_complete: true,
            product_pack_coverage_status: "passed",
            retailer_coverage_status: "passed",
          },
        }),
      ),
    ).toEqual([]);
  });

  it("flags summary, outcome, price, distribution, and seller contradictions", () => {
    const brokenRelationship = relationship({
      comparison: {
        comparison_basis: "spec_equivalent",
        unit_basis: "package",
        price_delta: 0.07,
        price_delta_percent: 0.259,
        outcome: "walmart_wins",
        match_certification: {
          status: "certified_comparable",
          source: "matching_v2_gold_set",
        },
      },
      benchmark_product: {
        ...relationship().benchmark_product,
        seller_status: "unverified",
        distribution: {
          physical_store_distribution_count: -1,
          service_area_presence_count: 0,
          searched_store_count: null,
        },
      } as unknown as CanonicalDataset["product_relationships"][number]["benchmark_product"],
    }) as unknown as CanonicalDataset["product_relationships"][number];

    const issues = canonicalReportIntegrityIssues(
      dataset({
        contracts: {
          distribution: {
            version: "1.0.0",
            basis: "positive_price_store_search_result",
            grain: "retailer_product_id_x_store_id",
            deduplication: "distinct_store_id_per_product",
            price_rule: "price_gt_zero",
            inventory_claim: true,
            stock_status_used: false,
            sponsorship_used: false,
            extrapolation: false,
          } as unknown as CanonicalDataset["contracts"]["distribution"],
          service_area_presence: {
            version: "1.0.0",
            basis: "positive_price_service_area_search_result",
            grain: "retailer_product_id_x_service_area",
            price_rule: "price_gt_zero",
            presented_as_store_count: true,
          } as unknown as CanonicalDataset["contracts"]["service_area_presence"],
        },
        summary: {
          relationship_count: 2,
          walmart_win_count: 0,
          competitor_win_count: 0,
          parity_count: 0,
          unscored_count: 0,
          excluded_relationship_count: 0,
        },
        product_relationships: [brokenRelationship],
        qa: {
          included_relationship_count: 2,
          excluded_relationship_count: 0,
          invalid_price_record_count: 0,
          unverified_seller_product_count: 1,
          products_without_image_count: 0,
          products_without_valid_distribution_count: 0,
          match_certification_complete: true,
          product_pack_coverage_status: "passed",
          retailer_coverage_status: "passed",
        },
      }),
    );

    expect(issues.map((issue) => issue.code)).toEqual([
      "summary_relationship_count_mismatch",
      "qa_included_relationship_count_mismatch",
      "walmart_win_count_mismatch",
      "invalid_distribution_contract",
      "service_area_presented_as_store_count",
      "price_delta_mismatch",
      "walmart_win_positive_delta",
      "benchmark_seller_not_qualified",
      "negative_distribution_count",
    ]);
  });

  it("flags duplicate relationship ids and competitor-win negative deltas", () => {
    const first = relationship();
    const second = relationship({
      comparison: {
        comparison_basis: "spec_equivalent",
        unit_basis: "package",
        price_delta: -0.07,
        price_delta_percent: -0.259,
        outcome: "competitor_wins",
        match_certification: {
          status: "certified_comparable",
          source: "matching_v2_gold_set",
        },
      },
    });

    const issues = canonicalReportIntegrityIssues(
      dataset({
        summary: {
          relationship_count: 2,
          walmart_win_count: 1,
          competitor_win_count: 1,
          parity_count: 0,
          unscored_count: 0,
          excluded_relationship_count: 0,
        },
        product_relationships: [first, second],
        qa: {
          included_relationship_count: 2,
          excluded_relationship_count: 0,
          invalid_price_record_count: 0,
          unverified_seller_product_count: 0,
          products_without_image_count: 0,
          products_without_valid_distribution_count: 0,
          match_certification_complete: true,
          product_pack_coverage_status: "passed",
          retailer_coverage_status: "passed",
        },
      }),
    );

    expect(issues.map((issue) => issue.code)).toContain(
      "duplicate_relationship_id",
    );
    expect(issues.map((issue) => issue.code)).toContain(
      "competitor_win_negative_delta",
    );
  });
});
