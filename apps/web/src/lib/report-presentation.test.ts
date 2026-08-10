import { describe, expect, it } from "vitest";

import type { ReportSectionView } from "./api";
import {
  compactMetricName,
  formatMetric,
  groupReportSections,
  metricBarWidth,
  primaryComparisonRows,
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
      section("actions", "recommendations"),
    ]);

    expect(
      grouped.find((group) => group.id === "summary")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "geography")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "segments")?.sections,
    ).toHaveLength(1);
    expect(
      grouped.find((group) => group.id === "opportunities")?.sections,
    ).toHaveLength(1);
  });

  it("uses the server presentation contract when supplied", () => {
    const summary = section("summary-copy", "executive_summary");
    const price = section("price-table", "price_position");

    const grouped = groupReportSections(
      [summary, price],
      [
        { id: "summary", label: "Overview", section_ids: ["summary-copy"] },
        { id: "price", label: "Price", section_ids: ["price-table"] },
      ],
    );

    expect(grouped.map((group) => group.label)).toEqual(["Overview", "Price"]);
    expect(grouped[0]?.sections).toEqual([summary]);
    expect(grouped[1]?.sections).toEqual([price]);
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
      "ALDI · 80% lean / 20% fat / 2.25 lb / non-organic / non-grass-fed · Typical price difference",
    );
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
});
