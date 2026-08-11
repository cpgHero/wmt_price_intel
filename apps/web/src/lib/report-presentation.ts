import type {
  AnalysisReportView,
  ProductDecision,
  ReportSectionView,
} from "./api";
import { displayLabel, displayValue } from "./presentation";

export type ComparisonBasis = AnalysisReportView["comparison_bases"][number];

const priceUnitNames: Record<string, { short: string; long: string }> = {
  package: { short: "package", long: "per package" },
  lb: { short: "lb", long: "per pound" },
  pound: { short: "lb", long: "per pound" },
  gallon: { short: "gal", long: "per gallon" },
  dozen: { short: "dozen", long: "per dozen" },
  ounce: { short: "oz", long: "per ounce" },
  "fluid ounce": { short: "fl oz", long: "per fluid ounce" },
  count: { short: "count", long: "per count" },
  unit: { short: "unit", long: "per unit" },
};

function priceUnitToken(priceUnit: string | null | undefined) {
  return (priceUnit ?? "USD/package").replace(/^USD\//, "").trim();
}

export function priceUnitLabel(
  priceUnit: string | null | undefined,
  style: "short" | "long" = "long",
) {
  const token = priceUnitToken(priceUnit);
  return priceUnitNames[token]?.[style] ?? `per ${token}`;
}

export function formatPriceForBasis(
  value: number | null | undefined,
  priceUnit: string | null | undefined,
) {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  const amount = value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${amount} / ${priceUnitLabel(priceUnit, "short")}`;
}

export function formatMapValueLabel(
  valueLabel: string | null | undefined,
  priceUnit: string | null | undefined,
) {
  if (!valueLabel) return null;
  const sourceSuffix = `/${priceUnitToken(priceUnit)}`;
  if (!valueLabel.endsWith(sourceSuffix)) return valueLabel;
  return `${valueLabel.slice(0, -sourceSuffix.length)}/ ${priceUnitLabel(priceUnit, "short")}`;
}

export function comparisonBasisDescription(basis?: ComparisonBasis | null) {
  if (!basis) return "Configured comparison basis";
  return [
    basis.label,
    displayLabel(basis.comparison_metric),
    priceUnitLabel(basis.price_unit),
    displayLabel(basis.geography),
  ].join(" · ");
}

export function governedOutcomeCounts(
  decisions: ProductDecision[],
  benchmarkProductId = "all",
) {
  const visible = decisions.filter(
    (decision) =>
      benchmarkProductId === "all" ||
      decision.benchmark_product_id === benchmarkProductId,
  );
  return visible.reduce(
    (counts, decision) => {
      const benchmarkLower = counts.benchmark_lower + decision.benchmark_lower;
      const competitorLower =
        counts.competitor_lower + decision.competitor_lower;
      const parity = counts.parity + decision.parity;
      return {
        benchmark_lower: benchmarkLower,
        competitor_lower: competitorLower,
        parity,
        total: benchmarkLower + competitorLower + parity,
      };
    },
    { benchmark_lower: 0, competitor_lower: 0, parity: 0, total: 0 },
  );
}

export type ProductDecisionStance =
  "attention" | "protect" | "parity" | "mixed";

/**
 * Convert complete directional evidence into an honest merchant-facing stance.
 * A retailer win requires a majority of matched observations; otherwise the card
 * must say that the evidence is mixed instead of promoting a plurality to a win.
 */
export function productDecisionStance(
  decision: Pick<
    ProductDecision,
    "matches" | "benchmark_lower_share" | "competitor_lower_share" | "parity"
  >,
): ProductDecisionStance {
  if (decision.matches <= 0) return "mixed";
  const parityShare = decision.parity / decision.matches;
  if (decision.competitor_lower_share > 0.5) return "attention";
  if (decision.benchmark_lower_share > 0.5) return "protect";
  if (
    parityShare >= 0.5 &&
    parityShare >= decision.competitor_lower_share &&
    parityShare >= decision.benchmark_lower_share
  ) {
    return "parity";
  }
  return "mixed";
}

export const reportGroups = [
  { id: "overview", label: "Overview" },
  { id: "price-segments", label: "Price & Segments" },
  { id: "products", label: "Products" },
  { id: "geography", label: "Geography" },
  { id: "assortment", label: "Assortment" },
  { id: "match-review", label: "Match Review" },
  { id: "quality-methodology", label: "Quality & Methodology" },
  { id: "exports", label: "Exports" },
] as const;

export type ReportGroupId = (typeof reportGroups)[number]["id"];

const groupByKind: Record<string, ReportGroupId> = {
  executive_summary: "overview",
  kpi_strip: "overview",
  coverage: "geography",
  geographic_sensitivity: "geography",
  price_position: "price-segments",
  segment_analysis: "price-segments",
  product_table: "products",
  assortment: "assortment",
  recommendations: "quality-methodology",
  data_quality: "quality-methodology",
  methodology: "quality-methodology",
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
    median_gap: "Paired median price difference",
  };
  const segment = rawSegment.replace(/ \/ standard$/i, "");
  return segment === "All comparable items"
    ? `${competitor} · ${measureLabel[measure]}`
    : `${competitor} · ${segment} · ${measureLabel[measure]}`;
}
