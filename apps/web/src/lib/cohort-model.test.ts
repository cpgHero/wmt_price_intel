import { describe, expect, it } from "vitest";

import {
  comparableCohort,
  comparableCohorts,
  sortComparableCohorts,
} from "./cohort-model";

describe("comparable cohort presentation model", () => {
  const rows = [
    {
      _competitor_id: "aldi_us",
      _profile_id: "private_label",
      _segment_id: "gallon-whole",
      _segment_attributes: { volume_oz: 128, fat_type: "whole" },
      competitor: "ALDI",
      segment: "128 fl oz · whole · non-organic · non-lactose-free",
      _matches: 1500,
      _matched_geographies: 1400,
      _benchmark_lower_rate: 0.35,
      _competitor_lower_rate: 0.65,
      _parity_rate: 0,
      _benchmark_median: 3.34,
      _competitor_median: 2.97,
      _median_gap: -0.37,
      _dominant_outcome: "competitor_lower",
    },
    {
      _competitor_id: "amazon_us_same_day",
      _profile_id: "same_brand_exact",
      _segment_id: "half-gallon-organic",
      competitor: "Amazon Same Day (US)",
      segment: "64 fl oz · whole · organic · non-lactose-free",
      _matches: 1000,
      _matched_geographies: 900,
      _benchmark_lower_rate: 0.2,
      _competitor_lower_rate: 0.7,
      _parity_rate: 0.1,
      _benchmark_median: 12.52,
      _competitor_median: 11.98,
      _median_gap: -0.54,
      _dominant_outcome: "competitor_lower",
    },
    {
      competitor: "ALDI",
      segment: "All comparable items",
      _matches: 9999,
      _dominant_outcome: "benchmark_lower",
    },
  ];

  it("uses projector-supplied deterministic values and omits the all-items rollup", () => {
    const cohorts = comparableCohorts(rows);

    expect(cohorts).toHaveLength(2);
    expect(cohorts[0]).toMatchObject({
      attributes: { volume_oz: 128, fat_type: "whole" },
      overall: false,
      matches: 1500,
      matchedGeographies: 1400,
      medianGap: -0.37,
      outcome: "competitor_lower",
    });
  });

  it("exposes the overall row for a governed included-products drilldown", () => {
    const cohort = comparableCohort(rows[2]);

    expect(cohort).toMatchObject({
      segmentId: "All comparable items",
      overall: true,
      attributes: {},
    });
  });

  it("ranks by evidence, pressure, or absolute gap without changing metrics", () => {
    const cohorts = comparableCohorts(rows);

    expect(sortComparableCohorts(cohorts, "evidence")[0]?.competitor).toBe(
      "ALDI",
    );
    expect(
      sortComparableCohorts(cohorts, "competitor_pressure")[0]?.competitor,
    ).toBe("Amazon Same Day (US)");
    expect(sortComparableCohorts(cohorts, "gap")[0]?.medianGap).toBe(-0.54);
  });

  it("supports current formatted records during a rolling deployment", () => {
    const [cohort] = comparableCohorts([
      {
        competitor: "ALDI",
        segment: "64 fl oz · 2%",
        matches: "1,234",
        "matched geographies": "900",
        "benchmark lower": "59.6%",
        "competitor lower": "40.4%",
        parity: "0.0%",
        "benchmark marginal median": "$4.00",
        "competitor marginal median": "$4.90",
        "paired median gap": "$0.90",
        "dominant outcome": "Benchmark Lower",
      },
    ]);

    expect(cohort).toMatchObject({
      matches: 1234,
      benchmarkLowerRate: 0.596,
      benchmarkMedian: 4,
      outcome: "benchmark_lower",
    });
  });
});
