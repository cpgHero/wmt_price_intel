import { describe, expect, it } from "vitest";

import type {
  ProductDecision,
  ProductMatchCandidate,
  ReportSectionView,
  RetailerScorecard,
} from "./api";
import {
  cohortProductSummaries,
  comparisonBasisDescription,
  compactMetricName,
  formatMetric,
  formatMapValueLabel,
  formatPriceForBasis,
  governedOutcomeCounts,
  groupReportSections,
  metricBarWidth,
  priceUnitLabel,
  primaryComparisonRows,
  productDecisionStance,
  scorecardProductSummaries,
} from "./report-presentation";

function section(id: string, kind: string): ReportSectionView {
  return {
    id,
    title: id,
    kind,
    visualization: "table",
    required: true,
    empty: false,
    metrics: [],
    records: [],
    evidence_sets: [],
    narrative: null,
  };
}

describe("report presentation", () => {
  it("groups blueprint sections by generic presentation kind", () => {
    const grouped = groupReportSections([
      section("kpis", "kpi_strip"),
      section("coverage", "coverage"),
      section("normalized", "segment_analysis"),
      section("assortment", "assortment"),
      section("actions", "recommendations"),
    ]);

    expect(
      grouped.find((group) => group.id === "overview")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "geography")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "price-segments")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "quality-methodology")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "assortment")?.sections,
    ).toHaveLength(1);
  });

  it("uses the server presentation contract when supplied", () => {
    const summary = section("summary-copy", "executive_summary");
    const price = section("price-table", "price_position");

    const grouped = groupReportSections(
      [summary, price],
      [
        { id: "overview", label: "Overview", section_ids: ["summary-copy"] },
        {
          id: "price-segments",
          label: "Price & Segments",
          section_ids: ["price-table"],
        },
      ],
    );

    expect(grouped.map((group) => group.label)).toEqual([
      "Overview",
      "Price & Segments",
    ]);
    expect(grouped[0]?.sections).toEqual([summary]);
    expect(grouped[1]?.sections).toEqual([price]);
  });

  it("omits retired report tabs from the server presentation contract", () => {
    const summary = section("summary-copy", "executive_summary");

    const grouped = groupReportSections(
      [summary],
      [
        { id: "overview", label: "Overview", section_ids: ["summary-copy"] },
        { id: "match-review", label: "Match Evidence", section_ids: [] },
        { id: "exports", label: "Exports", section_ids: [] },
      ],
    );

    expect(grouped.map((group) => group.id)).toEqual(["overview"]);
  });

  it("formats deterministic metric values without changing them", () => {
    expect(formatMetric(0.8414189413, "rate")).toBe("84.1%");
    expect(formatMetric(-1.48, "USD_per_lb")).toBe("-$1.48 / lb");
    expect(formatMetric(225791, "rows")).toBe("225,791 rows");
  });

  it("scales bars only for presentation", () => {
    expect(metricBarWidth(50, [100, 50])).toBe(50);
    expect(metricBarWidth(-25, [100, -25])).toBe(25);
    expect(metricBarWidth("unknown", [100])).toBe(0);
  });

  it("turns comparison metric internals into merchant-facing labels", () => {
    expect(
      compactMetricName(
        {
          name: "ALDI Strict same-ZIP and exact-package comparison All comparable items benchmark_lower_rate",
        },
        "Walmart (US)",
      ),
    ).toBe("ALDI · Walmart (US) lower rate");
    expect(
      compactMetricName(
        {
          name: "ALDI Strict same-ZIP and exact-package comparison 80% lean / 20% fat / 2.25 lb / non-organic / non-grass-fed / standard median_gap",
        },
        "Walmart (US)",
      ),
    ).toBe(
      "ALDI · 80% lean / 20% fat / 2.25 lb / non-organic / non-grass-fed · Paired median price difference",
    );
  });

  it("formats values with the governed comparison unit", () => {
    expect(formatPriceForBasis(3.457, "USD/package")).toBe("$3.46 / package");
    expect(formatPriceForBasis(2.997, "USD/lb")).toBe("$3.00 / lb");
    expect(formatPriceForBasis(4.497, "USD/dozen")).toBe("$4.50 / dozen");
    expect(priceUnitLabel("USD/gallon")).toBe("per gallon");
    expect(
      formatMapValueLabel(
        "Competitor lower · paired difference $0.56 /gallon",
        "USD/gallon",
      ),
    ).toBe("Competitor lower · paired difference $0.56 / gal");
    expect(
      comparisonBasisDescription({
        profile_id: "milk-gallon",
        label: "Comparable gallon",
        geography: "exact_zip",
        comparison_metric: "price_per_gallon",
        price_unit: "USD/gallon",
        package_basis: "normalized_unit",
        availability_policy: "search_presence",
        population_basis: "relationship_resolved_products",
      }),
    ).toContain("resolved product relationships");
  });

  it("derives full governed map outcomes from product decisions rather than sampled points", () => {
    const decisions = [
      {
        benchmark_product_id: "w1",
        matches: 100,
        benchmark_lower: 20,
        competitor_lower: 70,
        parity: 10,
      },
      {
        benchmark_product_id: "w2",
        matches: 60,
        benchmark_lower: 40,
        competitor_lower: 15,
        parity: 5,
      },
    ] as ProductDecision[];

    expect(governedOutcomeCounts(decisions)).toEqual({
      benchmark_lower: 60,
      competitor_lower: 85,
      parity: 15,
      total: 160,
    });
    expect(governedOutcomeCounts(decisions, "w1").total).toBe(100);
  });

  it("does not promote a plurality or tied median into a directional product win", () => {
    expect(
      productDecisionStance({
        matches: 901,
        benchmark_lower_share: 298 / 901,
        competitor_lower_share: 326 / 901,
        parity: 277,
      }),
    ).toBe("mixed");
    expect(
      productDecisionStance({
        matches: 100,
        benchmark_lower_share: 0.15,
        competitor_lower_share: 0.7,
        parity: 15,
      }),
    ).toBe("attention");
    expect(
      productDecisionStance({
        matches: 100,
        benchmark_lower_share: 0.2,
        competitor_lower_share: 0.15,
        parity: 65,
      }),
    ).toBe("parity");
  });

  it("selects overall exact-price rows for the executive and geography views", () => {
    const exact = section("exact", "price_position");
    exact.records = [
      { competitor: "ALDI", segment: "All comparable items", matches: "9,049" },
      { competitor: "ALDI", segment: "80 / 20", matches: "1,456" },
    ];
    const normalized = section("normalized", "segment_analysis");
    normalized.records = [
      { competitor: "ALDI", segment: "All comparable items", matches: "7,622" },
    ];

    expect(primaryComparisonRows([normalized, exact])).toEqual([
      exact.records[0],
    ]);
  });

  it("lists only admitted product relationships from the scorecard profile", () => {
    const scorecard = {
      competitor_id: "aldi_us",
      competitor: "ALDI",
      profile_id: "strict",
    } as RetailerScorecard;
    const base = {
      id: "candidate-1",
      relationship_id: "relationship-1",
      relationship_status: "suggested",
      qa_status: "ready",
      profile_id: "strict",
      comparison_metric: "package_price",
      benchmark_product_id: "w1",
      benchmark_product_name: "Walmart milk",
      competitor: "aldi_us",
      competitor_product_id: "a1",
      competitor_product_name: "ALDI milk",
      matches: 40,
      geographies: 30,
      benchmark_lower: 10,
      competitor_lower: 25,
      parity: 5,
      benchmark_lower_share: 0.25,
      competitor_lower_share: 0.625,
      median_benchmark_price: 3.98,
      median_competitor_price: 3.75,
      median_gap: -0.23,
    } satisfies ProductMatchCandidate;
    const candidates = [
      base,
      { ...base, id: "unmatched", relationship_status: "unmatched" as const },
      { ...base, id: "other-lens", profile_id: "per-gallon" },
      { ...base, id: "other-retailer", competitor: "amazon_us" },
    ];

    const rows = scorecardProductSummaries(scorecard, candidates, []);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      relationship_id: "relationship-1",
      matches: 40,
      stance: "attention",
      benchmark_product_name: "Walmart milk",
      competitor_product_name: "ALDI milk",
    });
  });

  it("uses server-reconciled decision rows for a governed-products fallback scorecard", () => {
    const scorecard = {
      competitor_id: "aldi_us",
      competitor: "ALDI",
      profile_id: "governed_products",
    } as RetailerScorecard;
    const decision = {
      id: "decision-1",
      relationship_id: "relationship-1",
      relationship_status: "confirmed",
      qa_status: "ready",
      profile_id: "strict",
      benchmark_product_id: "w1",
      benchmark_product_name: "Walmart milk",
      competitor: "aldi_us",
      competitor_product_id: "a1",
      competitor_product_name: "ALDI milk",
      matches: 20,
      geographies: 18,
      benchmark_lower: 12,
      competitor_lower: 6,
      parity: 2,
      benchmark_lower_share: 0.6,
      competitor_lower_share: 0.3,
      median_benchmark_price: 3.5,
      median_competitor_price: 3.8,
      median_gap: 0.3,
    } as ProductDecision;

    expect(scorecardProductSummaries(scorecard, [], [decision])).toMatchObject([
      { relationship_id: "relationship-1", stance: "protect", matches: 20 },
    ]);
  });

  it("uses the governed relationship ledger when a decision omits duplicate status fields", () => {
    const scorecard = {
      competitor_id: "shoprite_us",
      competitor: "ShopRite",
      profile_id: "compatible",
    } as RetailerScorecard;
    const decision = {
      id: "decision-1",
      relationship_id: "relationship-1",
      profile_id: "compatible",
      benchmark_product_id: "w1",
      benchmark_product_name: "Walmart eggs",
      competitor: "shoprite_us",
      competitor_product_id: "s1",
      competitor_product_name: "ShopRite eggs",
      matches: 94,
      geographies: 54,
      benchmark_lower: 50,
      competitor_lower: 44,
      parity: 0,
      benchmark_lower_share: 50 / 94,
      competitor_lower_share: 44 / 94,
      median_benchmark_price: 3.49,
      median_competitor_price: 3.54,
      median_gap: 0.05,
    } as ProductDecision;

    expect(
      scorecardProductSummaries(
        scorecard,
        [],
        [decision],
        [
          {
            relationship_id: "relationship-1",
            competitor_id: "shoprite_us",
            eligible_profile_ids: ["compatible"],
            status: "confirmed",
            qa_status: "ready",
          },
        ],
      ),
    ).toMatchObject([
      { relationship_id: "relationship-1", matches: 94, stance: "protect" },
    ]);
  });

  it("resolves only the governed product relationships inside a Product Pack cohort", () => {
    const base = {
      id: "candidate-1",
      relationship_id: "relationship-1",
      relationship_status: "suggested",
      qa_status: "ready",
      profile_id: "strict",
      comparison_metric: "package_price",
      benchmark_product_id: "w1",
      benchmark_product_name: "Walmart whole milk",
      competitor: "aldi_us",
      competitor_product_id: "a1",
      competitor_product_name: "ALDI whole milk",
      matches: 40,
      geographies: 30,
      benchmark_lower: 10,
      competitor_lower: 25,
      parity: 5,
      match_attributes: { volume_oz: 128, fat_type: "whole" },
    } satisfies ProductMatchCandidate;
    const candidates = [
      base,
      {
        ...base,
        id: "candidate-2",
        relationship_id: "relationship-2",
        benchmark_product_id: "w2",
        competitor_product_id: "a2",
        match_attributes: { volume_oz: 128, fat_type: "2%" },
      },
    ];

    const products = cohortProductSummaries(
      {
        competitorId: "aldi_us",
        competitor: "ALDI",
        profileId: "strict",
        overall: false,
        attributes: { volume_oz: 128, fat_type: "whole" },
      },
      candidates,
      [],
    );

    expect(products).toHaveLength(1);
    expect(products[0]?.relationship_id).toBe("relationship-1");
  });

  it("shows analysis-source product pairs when automatic candidates remain unmatched", () => {
    const unmatchedCandidate = {
      id: "candidate-1",
      relationship_status: "unmatched",
      qa_status: "ready",
      profile_id: "strict",
      benchmark_product_id: "w1",
      benchmark_product_name: "Walmart whole milk",
      competitor: "aldi_us",
      competitor_product_id: "a1",
      competitor_product_name: "ALDI whole milk",
      matches: 40,
      match_attributes: { volume_oz: 128, fat_type: "whole" },
    } satisfies ProductMatchCandidate;
    const products = cohortProductSummaries(
      {
        competitorId: "aldi_us",
        competitor: "ALDI",
        profileId: "strict",
        overall: false,
        attributes: { volume_oz: 128, fat_type: "whole" },
      },
      [unmatchedCandidate],
      [],
    );

    expect(products).toMatchObject([
      {
        relationship_id: null,
        relationship_status: "unmatched",
        benchmark_product_id: "w1",
        competitor_product_id: "a1",
        matches: 40,
      },
    ]);
  });
});
