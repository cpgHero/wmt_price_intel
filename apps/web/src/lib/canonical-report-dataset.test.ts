import { describe, expect, it } from "vitest";

import type { AnalysisRecord, AnalysisReportView } from "./api";
import { canonicalReportDatasetFromReportView } from "./canonical-report-dataset";

function analysis(
  result: AnalysisRecord["result"] = {} as AnalysisRecord["result"],
): AnalysisRecord {
  return {
    id: "analysis-row-1",
    analysis_run_id: "run-1",
    analysis_id: "fresh_bananas-active",
    collection_run_id: "collection-1",
    status: "ready",
    reporting_status: "ready",
    product_pack_id: "fresh_bananas",
    product_pack_version: "1.0.0",
    schema_version: "2.0.0",
    checksum: "a".repeat(64),
    result,
    created_at: "2026-09-09T18:00:00Z",
  };
}

function reportView(): AnalysisReportView {
  return {
    schema_version: "1.1.0",
    analysis_id: "fresh_bananas-active",
    generated_at: "2026-09-09T18:00:00Z",
    benchmark_retailer: "Walmart (US)",
    competitors: ["ALDI (US)"],
    retailer_scope: {
      benchmark: { id: "walmart_us", name: "Walmart (US)" },
      competitors: [{ id: "aldi_us", name: "ALDI (US)" }],
    },
    retailer_scorecards: [
      {
        competitor_id: "aldi_us",
        competitor: "ALDI (US)",
        benchmark_retailer_id: "walmart_us",
        benchmark_retailer: "Walmart (US)",
        profile_id: "spec_equivalent",
        comparison_lens: "Specification-equivalent",
        comparison_metric: "package_price",
        price_unit: "USD/package",
        package_basis: "exact_package",
        geography: "United States",
        basis_status: "preferred",
        matches: 100,
        matched_geographies: 80,
        qualifying_geographies: 100,
        benchmark_lower_rate: 0.8,
        competitor_lower_rate: 0.1,
        parity_rate: 0.1,
        benchmark_median: 0.2,
        competitor_median: 0.27,
        median_gap: -0.07,
        benchmark_median_statistic: "marginal_median",
        competitor_median_statistic: "marginal_median",
        median_gap_statistic: "paired_median_gap",
        minimum_observations: 1,
        minimum_geographies: 1,
        readiness_reason: "Ready",
        evidence_state: "reported",
        dominant_outcome: "benchmark_lower",
        price_position: "Walmart lower",
        status: "ready",
      },
    ],
    product_pack: {
      id: "fresh_bananas",
      name: "Fresh Bananas & Plantains",
      version: "1.0.0",
      recommended_charts: [],
    },
    blueprint: { id: "decision-led", version: "1.0.0" },
    comparison_bases: [],
    match_governance: {
      mode: "governed",
      match_revision_id: "match-revision-1",
      matching_v2_gold_set_release_id: "gold-set-1",
      applied_policy_revision_id: null,
      staged_revision_id: null,
      suggested: 0,
      confirmed: 1,
      rejected: 0,
      ambiguous: 0,
    },
    report_readiness: {
      status: "ready",
      blocking_reasons: [],
      warnings: [],
      suppressed_decisions: 0,
    },
    groups: [],
    sections: [],
    result_checksum: "a".repeat(64),
    publication: null,
    certification_coverage: {
      authority: "matching_v2",
      queue_case_count: 1,
      certified_label_count: 1,
      certified_comparable_count: 1,
      certified_not_comparable_count: 0,
      unresolved_excluded_count: 0,
      pending_unreviewed_count: 0,
      automatic_fallback_enabled: false,
    },
    match_candidates: [
      {
        id: "candidate-1",
        relationship_id: "relationship-1",
        relationship_status: "confirmed",
        qa_status: "ready",
        profile_id: "spec_equivalent",
        comparison_metric: "package_price",
        benchmark_product_id: "44390948",
        benchmark_product_name: "Fresh Banana, Each",
        benchmark_image_url: "https://i5.walmartimages.com/example-banana.jpeg",
        benchmark_product_url: "https://www.walmart.com/ip/44390948",
        competitor: "ALDI (US)",
        competitor_product_id: "banana-each",
        competitor_product_name: "Banana, Each",
        competitor_image_url: "https://www.aldi.us/example-banana.jpeg",
        competitor_product_url:
          "https://www.aldi.us/store/aldi/products/banana-each",
        geographies: 80,
        matches: 100,
        benchmark_lower: 80,
        competitor_lower: 10,
        parity: 10,
        benchmark_lower_share: 0.8,
        competitor_lower_share: 0.1,
        median_benchmark_price: 0.2,
        median_competitor_price: 0.27,
        median_gap: -0.07,
      },
    ],
    product_decisions: [
      {
        id: "decision-1",
        relationship_id: "relationship-1",
        relationship_status: "confirmed",
        profile_id: "spec_equivalent",
        comparison_metric: "package_price",
        qa_status: "ready",
        priority: "protect",
        benchmark_product_id: "44390948",
        benchmark_product_name: "Fresh Banana, Each",
        benchmark_image_url: "https://i5.walmartimages.com/example-banana.jpeg",
        benchmark_product_url: "https://www.walmart.com/ip/44390948",
        competitor: "ALDI (US)",
        competitor_product_id: "banana-each",
        competitor_product_name: "Banana, Each",
        competitor_image_url: "https://www.aldi.us/example-banana.jpeg",
        competitor_product_url:
          "https://www.aldi.us/store/aldi/products/banana-each",
        matches: 100,
        geographies: 80,
        benchmark_lower: 80,
        competitor_lower: 10,
        parity: 10,
        benchmark_lower_share: 0.8,
        competitor_lower_share: 0.1,
        median_benchmark_price: 0.2,
        median_competitor_price: 0.27,
        median_gap: -0.07,
        plain_insight: "Walmart is lower.",
        top_locations: [],
      },
    ],
    assortment_analysis: {
      source: "Search",
      grain: "retailer product x location",
      distribution_contract: {
        version: "1.0.0",
        basis: "positive_price_store_search_result",
        grain: "retailer_product_id_x_store_id",
        deduplication: "distinct_store_id_per_product",
        price_rule: "price_gt_zero",
        inventory_claim: false,
        stock_status_used: false,
        sponsorship_used: false,
      },
      benchmark_retailer: "walmart_us",
      retailers: [
        {
          retailer: "walmart_us",
          distinct_products: 1,
          observed_locations: 4294,
          observed_zipcodes: 0,
          distribution_store_count: 4294,
          service_area_presence_count: 0,
          median_products_per_location: 1,
          products: [
            {
              product_id: "44390948",
              canonical_product_id: "44390948",
              name: "Fresh Banana, Each",
              brand: null,
              observed_brand: null,
              brand_type: "unclassified",
              image_url: "https://i5.walmartimages.com/example-banana.jpeg",
              url: "https://www.walmart.com/ip/44390948",
              seller: "Walmart.com",
              observed_locations: 4294,
              observed_zipcodes: 0,
              distribution_store_count: 4294,
              service_area_presence_count: 0,
            },
          ],
        },
        {
          retailer: "aldi_us",
          distinct_products: 1,
          observed_locations: 2100,
          observed_zipcodes: 0,
          distribution_store_count: 2100,
          service_area_presence_count: 0,
          median_products_per_location: 1,
          products: [
            {
              product_id: "banana-each",
              canonical_product_id: "banana-each",
              name: "Banana, Each",
              brand: null,
              brand_type: "unclassified",
              image_url: "https://www.aldi.us/example-banana.jpeg",
              url: "https://www.aldi.us/store/aldi/products/banana-each",
              observed_locations: 2100,
              observed_zipcodes: 0,
              distribution_store_count: 2100,
              service_area_presence_count: 0,
            },
          ],
        },
      ],
      comparisons: [],
    },
  } as unknown as AnalysisReportView;
}

describe("canonical report dataset adapter", () => {
  it("projects fully evidenced product decisions into product win/loss relationships", () => {
    const dataset = canonicalReportDatasetFromReportView(
      analysis(),
      reportView(),
    );

    expect(dataset.schema_version).toBe("1.0.0");
    expect(dataset.product_relationships).toHaveLength(1);
    expect(dataset.excluded_relationships).toHaveLength(0);
    expect(dataset.summary).toMatchObject({
      relationship_count: 1,
      walmart_win_count: 1,
      competitor_win_count: 0,
      parity_count: 0,
      excluded_relationship_count: 0,
    });
    expect(dataset.contracts.distribution).toMatchObject({
      basis: "positive_price_store_search_result",
      inventory_claim: false,
      stock_status_used: false,
      sponsorship_used: false,
      extrapolation: false,
    });
    expect(dataset.product_relationships[0]?.benchmark_product).toMatchObject({
      retailer_product_id: "44390948",
      seller_status: "qualified",
      distribution: {
        physical_store_distribution_count: 4294,
        service_area_presence_count: 0,
      },
    });
    expect(
      dataset.product_relationships[0]?.benchmark_product.price,
    ).toMatchObject({
      reporting_price: 0.2,
      package_price: 0.2,
      normalized_unit_price: null,
    });
    expect(dataset.product_relationships[0]?.comparison).toMatchObject({
      outcome: "walmart_wins",
      price_delta: -0.07,
    });
  });

  it("uses source observed_end as the canonical evidence timestamp when available", () => {
    const dataset = canonicalReportDatasetFromReportView(
      analysis({
        source: { observed_end: "2026-09-08T23:59:59Z" },
      } as AnalysisRecord["result"]),
      reportView(),
    );

    expect(dataset.generated_at).toBe("2026-09-09T18:00:00Z");
    expect(dataset.evidence_observed_at).toBe("2026-09-08T23:59:59Z");
  });

  it("derives card outcomes from the displayed price delta, not older lower-share fields", () => {
    const view = reportView();
    view.product_decisions![0]!.benchmark_lower_share = 0.8;
    view.product_decisions![0]!.competitor_lower_share = 0.1;
    view.product_decisions![0]!.benchmark_lower = 80;
    view.product_decisions![0]!.competitor_lower = 10;
    view.product_decisions![0]!.median_benchmark_price = 0.3;
    view.product_decisions![0]!.median_competitor_price = 0.2;
    view.product_decisions![0]!.median_gap = 0.1;

    const dataset = canonicalReportDatasetFromReportView(analysis(), view);

    expect(dataset.product_relationships).toHaveLength(1);
    expect(dataset.product_relationships[0]?.comparison).toMatchObject({
      outcome: "competitor_wins",
      price_delta: 0.09999999999999998,
    });
    expect(dataset.summary).toMatchObject({
      walmart_win_count: 0,
      competitor_win_count: 1,
      parity_count: 0,
    });
  });

  it("excludes Walmart benchmark products that are not seller-qualified", () => {
    const view = reportView();
    view.assortment_analysis!.retailers[0]!.products![0]!.seller =
      "Marketplace seller";

    const dataset = canonicalReportDatasetFromReportView(analysis(), view);

    expect(dataset.product_relationships).toHaveLength(0);
    expect(dataset.excluded_relationships).toHaveLength(1);
    expect(dataset.excluded_relationships[0]?.reason_code).toBe(
      "benchmark_seller_not_qualified",
    );
    expect(dataset.seller_governance.status).toBe("blocked");
  });

  it("excludes decisions with missing or zero reportable prices", () => {
    const view = reportView();
    view.product_decisions![0]!.median_benchmark_price = 0;

    const dataset = canonicalReportDatasetFromReportView(analysis(), view);

    expect(dataset.product_relationships).toHaveLength(0);
    expect(dataset.excluded_relationships).toHaveLength(1);
    expect(dataset.excluded_relationships[0]?.reason_code).toBe(
      "invalid_or_missing_price",
    );
    expect(dataset.price_normalization.status).toBe("passed_with_exclusions");
  });

  it("excludes relationships with missing competitor distribution evidence", () => {
    const view = reportView();
    view.assortment_analysis!.retailers[1]!.products = [];

    const dataset = canonicalReportDatasetFromReportView(analysis(), view);

    expect(dataset.product_relationships).toHaveLength(0);
    expect(dataset.excluded_relationships).toHaveLength(1);
    expect(dataset.excluded_relationships[0]?.reason_code).toBe(
      "missing_competitor_distribution",
    );
    expect(dataset.qa.products_without_valid_distribution_count).toBe(1);
  });
});
