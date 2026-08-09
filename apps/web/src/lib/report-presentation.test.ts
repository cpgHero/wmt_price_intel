import { describe, expect, it } from "vitest";

import type { ReportSectionView } from "./api";
import {
  formatMetric,
  groupReportSections,
  metricBarWidth,
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
});
