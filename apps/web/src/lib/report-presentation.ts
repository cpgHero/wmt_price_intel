import type { ReportSectionView } from "./api";
import { displayValue } from "./presentation";

export const reportGroups = [
  { id: "summary", label: "Summary" },
  { id: "geography", label: "Geography" },
  { id: "price", label: "Price" },
  { id: "segments", label: "Segments" },
  { id: "products", label: "Products" },
  { id: "assortment", label: "Assortment" },
  { id: "opportunities", label: "Opportunities" },
  { id: "quality", label: "Quality" },
  { id: "methodology", label: "Methodology" },
] as const;

export type ReportGroupId = (typeof reportGroups)[number]["id"];

const groupByKind: Record<string, ReportGroupId> = {
  executive_summary: "summary",
  kpi_strip: "summary",
  coverage: "geography",
  geographic_sensitivity: "geography",
  price_position: "price",
  segment_analysis: "segments",
  product_table: "products",
  assortment: "assortment",
  recommendations: "opportunities",
  data_quality: "quality",
  methodology: "methodology",
};

export function groupReportSections(
  sections: ReportSectionView[],
  contractGroups?: Array<{
    id: string;
    label: string;
    section_ids: string[];
  }>,
) {
  if (contractGroups?.length) {
    const byId = new Map(sections.map((section) => [section.id, section]));
    return contractGroups.map((group) => ({
      id: group.id as ReportGroupId,
      label: group.label,
      sections: group.section_ids
        .map((id) => byId.get(id))
        .filter((section): section is ReportSectionView => Boolean(section)),
    }));
  }
  const grouped = new Map<ReportGroupId, ReportSectionView[]>();
  for (const group of reportGroups) grouped.set(group.id, []);
  for (const section of sections) {
    const group = groupByKind[section.kind] ?? "summary";
    grouped.get(group)?.push(section);
  }
  return reportGroups.map((group) => ({
    ...group,
    sections: grouped.get(group.id) ?? [],
  }));
}

export function primaryComparisonRows(sections: ReportSectionView[]) {
  const preferred = sections.find(
    (section) =>
      section.kind === "price_position" && section.records.length > 0,
  );
  const fallback = sections.find(
    (section) =>
      section.kind === "segment_analysis" && section.records.length > 0,
  );
  const rows = preferred?.records ?? fallback?.records ?? [];
  const overall = rows.filter(
    (row) => String(row.segment ?? "").toLowerCase() === "all comparable items",
  );
  return overall.length > 0 ? overall : rows;
}

export function formatMetric(value: unknown, unit: unknown): string {
  if (typeof value !== "number") return displayValue(value);
  const normalizedUnit = typeof unit === "string" ? unit : "";
  if (normalizedUnit === "rate") {
    return new Intl.NumberFormat("en-US", {
      style: "percent",
      maximumFractionDigits: 1,
    }).format(value);
  }
  if (normalizedUnit.startsWith("USD")) {
    const amount = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
    const suffixParts = normalizedUnit.slice(3).split("_").filter(Boolean);
    if (suffixParts[0] === "per") suffixParts.shift();
    const suffix = suffixParts.join(" ");
    return suffix ? `${amount} / ${suffix}` : amount;
  }
  const formatted = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
  }).format(value);
  return normalizedUnit ? `${formatted} ${normalizedUnit}` : formatted;
}

export function metricBarWidth(value: unknown, values: unknown[]): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  const numeric = values.filter(
    (candidate): candidate is number =>
      typeof candidate === "number" && Number.isFinite(candidate),
  );
  const maximum = Math.max(
    ...numeric.map((candidate) => Math.abs(candidate)),
    0,
  );
  return maximum === 0 ? 0 : Math.max(4, (Math.abs(value) / maximum) * 100);
}

const comparisonNamePattern =
  /^(.*?) (Strict same-ZIP and exact-package comparison|Best available price per pound|Configured nearby-store exact-package sensitivity) (.*?) (unique_geographies|benchmark_lower_rate|competitor_lower_rate|benchmark_lower|competitor_lower|median_gap|matches|parity_rate|parity)$/i;

export function compactMetricName(
  metric: Readonly<Record<string, unknown>>,
  benchmarkRetailer: string,
): string {
  const name = String(metric.name ?? "Metric");
  const match = comparisonNamePattern.exec(name);
  if (!match) return name.replaceAll("_", " ");
  const [, competitor, , rawSegment, rawMeasure] = match;
  const measure = rawMeasure.toLowerCase();
  const measureLabel: Record<string, string> = {
    matches: "Matched observations",
    unique_geographies: "Matched geographies",
    benchmark_lower: `${benchmarkRetailer} lower offers`,
    competitor_lower: `${competitor} lower offers`,
    parity: "Price parity",
    benchmark_lower_rate: `${benchmarkRetailer} lower rate`,
    competitor_lower_rate: `${competitor} lower rate`,
    parity_rate: "Parity rate",
    median_gap: "Typical price difference",
  };
  const segment = rawSegment.replace(/ \/ standard$/i, "");
  return segment === "All comparable items"
    ? `${competitor} · ${measureLabel[measure]}`
    : `${competitor} · ${segment} · ${measureLabel[measure]}`;
}
