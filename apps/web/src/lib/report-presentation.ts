import type {
  AnalysisReportView,
  ProductDecision,
  ProductMatchCandidate,
  ReportSectionView,
  RetailerScorecard,
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
    basis.population_basis === "market_floor"
      ? "market-floor assortment view"
      : "resolved product relationships",
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

export interface ScorecardProductSummary {
  id: string;
  relationship_id: string | null;
  relationship_status: ProductMatchCandidate["relationship_status"];
  profile_id: string | null;
  comparison_metric: string | null;
  match_rationale: string | null;
  match_attributes: Record<string, unknown>;
  benchmark_product_id: string;
  benchmark_product_name: string;
  benchmark_image_url: string | null;
  benchmark_product_url: string | null;
  competitor: string;
  competitor_product_id: string;
  competitor_product_name: string;
  competitor_image_url: string | null;
  competitor_product_url: string | null;
  matches: number;
  geographies: number;
  benchmark_lower: number;
  competitor_lower: number;
  parity: number;
  benchmark_lower_share: number;
  competitor_lower_share: number;
  median_benchmark_price: number | null;
  median_competitor_price: number | null;
  median_gap: number | null;
  stance: ProductDecisionStance;
}

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

function retailerIdentityToken(value: unknown) {
  return String(value ?? "")
    .toLocaleLowerCase("en-US")
    .replace(/\(us\)/g, "")
    .replace(/[^a-z0-9]/g, "");
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function productPairKey(row: {
  competitor: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  profile_id?: string | null;
}) {
  return [
    retailerIdentityToken(row.competitor),
    row.benchmark_product_id,
    row.competitor_product_id,
    row.profile_id ?? "",
  ].join("::");
}

type ProductSummaryScope = Pick<
  RetailerScorecard,
  "competitor_id" | "competitor" | "profile_id"
>;

function scopedProductSummaries(
  scope: ProductSummaryScope,
  candidates: ProductMatchCandidate[],
  decisions: ProductDecision[],
  governedFallback = false,
): ScorecardProductSummary[] {
  const competitorTokens = new Set([
    retailerIdentityToken(scope.competitor_id),
    retailerIdentityToken(scope.competitor),
  ]);
  const admitted = (row: {
    competitor: string;
    relationship_status?: ProductMatchCandidate["relationship_status"];
    qa_status?: ProductMatchCandidate["qa_status"];
    profile_id?: string | null;
    matches?: number;
  }) =>
    competitorTokens.has(retailerIdentityToken(row.competitor)) &&
    (row.relationship_status === "suggested" ||
      row.relationship_status === "confirmed") &&
    (row.qa_status ?? "ready") === "ready" &&
    (row.matches ?? 0) > 0;

  const decisionIndex = new Map(
    decisions.filter(admitted).map((row) => [productPairKey(row), row]),
  );
  const sourceRows: Array<ProductMatchCandidate | ProductDecision> =
    governedFallback
      ? decisions.filter(admitted)
      : candidates.filter(
          (row) => admitted(row) && row.profile_id === scope.profile_id,
        );
  const summaries = sourceRows.map((row) => {
    const decision = decisionIndex.get(productPairKey(row));
    const source = decision ?? row;
    const matches = finiteNumber(source.matches) ?? 0;
    const benchmarkLower = finiteNumber(source.benchmark_lower) ?? 0;
    const competitorLower = finiteNumber(source.competitor_lower) ?? 0;
    const parity = finiteNumber(source.parity) ?? 0;
    const completeOutcomes =
      matches > 0 && benchmarkLower + competitorLower + parity === matches;
    const benchmarkShare =
      finiteNumber(source.benchmark_lower_share) ??
      (completeOutcomes ? benchmarkLower / matches : 0);
    const competitorShare =
      finiteNumber(source.competitor_lower_share) ??
      (completeOutcomes ? competitorLower / matches : 0);
    const parityShare = completeOutcomes ? parity / matches : 0;
    return {
      id: source.id,
      relationship_id: source.relationship_id ?? null,
      relationship_status: source.relationship_status,
      profile_id: source.profile_id ?? null,
      comparison_metric: source.comparison_metric ?? null,
      match_rationale:
        "match_rationale" in row ? (row.match_rationale ?? null) : null,
      match_attributes:
        "match_attributes" in row ? (row.match_attributes ?? {}) : {},
      benchmark_product_id: source.benchmark_product_id,
      benchmark_product_name: source.benchmark_product_name,
      benchmark_image_url: source.benchmark_image_url ?? null,
      benchmark_product_url: source.benchmark_product_url ?? null,
      competitor: source.competitor,
      competitor_product_id: source.competitor_product_id,
      competitor_product_name:
        source.competitor_product_name ?? source.competitor_product_id,
      competitor_image_url: source.competitor_image_url ?? null,
      competitor_product_url: source.competitor_product_url ?? null,
      matches,
      geographies: finiteNumber(source.geographies) ?? 0,
      benchmark_lower: benchmarkLower,
      competitor_lower: competitorLower,
      parity,
      benchmark_lower_share: benchmarkShare,
      competitor_lower_share: competitorShare,
      median_benchmark_price: finiteNumber(source.median_benchmark_price),
      median_competitor_price: finiteNumber(source.median_competitor_price),
      median_gap: finiteNumber(source.median_gap),
      stance: productDecisionStance({
        matches,
        benchmark_lower_share: benchmarkShare,
        competitor_lower_share: competitorShare,
        parity: completeOutcomes ? parity : parityShare * matches,
      }),
    } satisfies ScorecardProductSummary;
  });
  const deduplicated = new Map<string, ScorecardProductSummary>();
  for (const row of summaries) {
    const key =
      row.relationship_id ??
      [
        retailerIdentityToken(row.competitor),
        row.benchmark_product_id,
        row.competitor_product_id,
        row.profile_id ?? "",
      ].join("::");
    if (!deduplicated.has(key)) deduplicated.set(key, row);
  }
  return [...deduplicated.values()].sort(
    (left, right) =>
      right.matches - left.matches ||
      left.benchmark_product_name.localeCompare(right.benchmark_product_name),
  );
}

/**
 * Project relationship-level evidence for a scorecard without recalculating it.
 * Preferred scorecards use admitted candidates for the exact scorecard profile;
 * the legacy governed-products fallback uses the same decision rows from which
 * that fallback scorecard was reconciled on the server.
 */
export function scorecardProductSummaries(
  scorecard: RetailerScorecard,
  candidates: ProductMatchCandidate[],
  decisions: ProductDecision[],
): ScorecardProductSummary[] {
  return scopedProductSummaries(
    scorecard,
    candidates,
    decisions,
    scorecard.profile_id === "governed_products",
  );
}

function comparableAttributeValue(value: unknown): string {
  if (typeof value === "string") return value.trim().toLocaleLowerCase("en-US");
  if (value === null || value === undefined) return "";
  return JSON.stringify(value);
}

/**
 * Select the admitted one-to-one relationships that contributed to a persisted
 * Product Pack cohort. Cohort metrics remain authoritative from AnalysisResult;
 * this function only resolves the product identities shown in the drilldown.
 */
export function cohortProductSummaries(
  cohort: {
    attributes: Record<string, unknown>;
    competitor: string;
    competitorId: string;
    overall: boolean;
    profileId: string;
  },
  candidates: ProductMatchCandidate[],
  decisions: ProductDecision[],
): ScorecardProductSummary[] {
  const products = scopedProductSummaries(
    {
      competitor_id: cohort.competitorId,
      competitor: cohort.competitor,
      profile_id: cohort.profileId,
    },
    candidates,
    decisions,
  );
  if (cohort.overall) return products;
  const cohortAttributes = Object.entries(cohort.attributes);
  if (!cohortAttributes.length) return [];
  return products.filter((product) =>
    cohortAttributes.every(
      ([name, value]) =>
        comparableAttributeValue(product.match_attributes[name]) ===
        comparableAttributeValue(value),
    ),
  );
}

export const reportGroups = [
  { id: "overview", label: "Overview" },
  { id: "price-segments", label: "Price & Segments" },
  { id: "products", label: "Products" },
  { id: "geography", label: "Geography" },
  { id: "assortment", label: "Assortment" },
  { id: "quality-methodology", label: "Quality & Methodology" },
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
    const visibleIds = new Set<string>(reportGroups.map((group) => group.id));
    return contractGroups
      .filter((group) => visibleIds.has(group.id))
      .map((group) => ({
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
