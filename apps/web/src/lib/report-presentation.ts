import type { ReportSectionView } from "./api";
import { displayValue } from "./presentation";

export const reportGroups = [
  { id: "summary", label: "Summary" },
  { id: "geography", label: "Geography" },
  { id: "price", label: "Price" },
  { id: "segments", label: "Segments" },
  { id: "products", label: "Products" },
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
  assortment: "products",
  recommendations: "opportunities",
  data_quality: "quality",
  methodology: "methodology",
};

export function groupReportSections(sections: ReportSectionView[]) {
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
