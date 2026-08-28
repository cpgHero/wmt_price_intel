import type { JsonObject } from "./api";
import type { CompetitivePortfolioScorecards } from "./api";

export type CohortOutcome =
  "benchmark_lower" | "competitor_lower" | "parity" | "unavailable";

export type CohortSort = "evidence" | "competitor_pressure" | "gap";

export interface ComparableCohort {
  id: string;
  competitorId: string;
  competitor: string;
  profileId: string;
  segmentId: string;
  segment: string;
  attributes: Record<string, unknown>;
  comparisonMetric: string;
  comparisonUnit: string;
  medianGrain: string;
  overall: boolean;
  pairCount: number;
  matches: number;
  matchedGeographies: number;
  benchmarkObservedLocations: number;
  benchmarkScoredLocations: number;
  benchmarkUnscoredLocations: number;
  locationCoverageRate: number | null;
  competitorContributingLocations: number;
  competitorContributingStores: number;
  competitorContributingServiceAreas: number;
  benchmarkLowerRate: number;
  competitorLowerRate: number;
  parityRate: number;
  benchmarkMedian: number | null;
  competitorMedian: number | null;
  medianGap: number | null;
  outcome: CohortOutcome;
  productRelationships: NonNullable<
    CompetitivePortfolioScorecards["cohorts"][number]["product_relationships"]
  >;
}

export interface CohortPricePresentation {
  primaryValue: number | null;
  primaryUnitLabel: string;
  secondaryValue: number | null;
  secondaryUnitLabel: string | null;
  canonicalValue: number | null;
  canonicalUnitLabel: string;
}

function numericValue(
  row: JsonObject,
  rawKey: string,
  displayKey: string,
  legacyDisplayKey?: string,
) {
  const raw = row[rawKey];
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  const display =
    row[displayKey] ?? (legacyDisplayKey ? row[legacyDisplayKey] : undefined);
  if (typeof display === "number" && Number.isFinite(display)) return display;
  if (typeof display !== "string") return null;
  const percent = display.includes("%");
  const parsed = Number(display.replaceAll(",", "").replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(parsed)) return null;
  return percent ? parsed / 100 : parsed;
}

function outcomeValue(value: unknown): CohortOutcome {
  const token = String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll(" ", "_");
  if (
    token === "benchmark_lower" ||
    token === "competitor_lower" ||
    token === "parity"
  )
    return token;
  return "unavailable";
}

function positiveNumericValue(
  row: JsonObject,
  rawKey: string,
  displayKey: string,
  legacyDisplayKey?: string,
) {
  const value = numericValue(row, rawKey, displayKey, legacyDisplayKey);
  return value !== null && value > 0 ? value : null;
}

export function comparableCohort(row: JsonObject): ComparableCohort | null {
  const segment = String(row.segment ?? "").trim();
  if (!segment) return null;
  const competitor = String(row.competitor ?? "Competitor");
  const competitorId = String(row._competitor_id ?? competitor);
  const profileId = String(row._profile_id ?? "");
  const segmentId = String(row._segment_id ?? segment);
  const attributes = row._segment_attributes;
  return {
    id: `${competitorId}:${profileId}:${segmentId}`,
    competitorId,
    competitor,
    profileId,
    segmentId,
    segment,
    attributes:
      attributes && typeof attributes === "object" && !Array.isArray(attributes)
        ? (attributes as Record<string, unknown>)
        : {},
    comparisonMetric: String(row.comparison_metric ?? ""),
    comparisonUnit: String(row.comparison_unit ?? ""),
    medianGrain: String(row.median_grain ?? ""),
    overall:
      segmentId.toLocaleLowerCase("en-US") === "all" ||
      segment.toLocaleLowerCase("en-US") === "all comparable items",
    pairCount: numericValue(row, "_relationships", "relationships") ?? 0,
    matches: numericValue(row, "_matches", "matches") ?? 0,
    matchedGeographies:
      numericValue(row, "_matched_geographies", "matched geographies") ?? 0,
    benchmarkObservedLocations:
      numericValue(
        row,
        "_benchmark_observed_locations",
        "benchmark observed locations",
      ) ?? 0,
    benchmarkScoredLocations:
      numericValue(
        row,
        "_benchmark_scored_locations",
        "benchmark scored locations",
      ) ?? 0,
    benchmarkUnscoredLocations:
      numericValue(
        row,
        "_benchmark_unscored_locations",
        "benchmark unscored locations",
      ) ?? 0,
    locationCoverageRate: numericValue(
      row,
      "_location_coverage_rate",
      "location coverage rate",
    ),
    competitorContributingLocations:
      numericValue(
        row,
        "_competitor_contributing_locations",
        "competitor contributing locations",
      ) ?? 0,
    competitorContributingStores:
      numericValue(
        row,
        "_competitor_contributing_stores",
        "competitor contributing stores",
      ) ?? 0,
    competitorContributingServiceAreas:
      numericValue(
        row,
        "_competitor_contributing_service_areas",
        "competitor contributing service areas",
      ) ?? 0,
    benchmarkLowerRate:
      numericValue(row, "_benchmark_lower_rate", "benchmark lower") ?? 0,
    competitorLowerRate:
      numericValue(row, "_competitor_lower_rate", "competitor lower") ?? 0,
    parityRate: numericValue(row, "_parity_rate", "parity") ?? 0,
    benchmarkMedian: positiveNumericValue(
      row,
      "_benchmark_median",
      "benchmark marginal median",
      "benchmark median",
    ),
    competitorMedian: positiveNumericValue(
      row,
      "_competitor_median",
      "competitor marginal median",
      "competitor median",
    ),
    medianGap: numericValue(
      row,
      "_median_gap",
      "paired median gap",
      "competitor - benchmark gap",
    ),
    outcome: outcomeValue(row._dominant_outcome ?? row["dominant outcome"]),
    productRelationships: [],
  };
}

export function cohortUnitLabel(comparisonUnit: string) {
  const normalized = comparisonUnit.trim().toLowerCase();
  if (normalized === "usd/package") return "per package";
  if (normalized.startsWith("usd/"))
    return `per ${normalized.slice("usd/".length)}`;
  return comparisonUnit || "on the configured price basis";
}

export function cohortPackageEquivalent(
  value: number | null,
  comparisonMetric: string,
  attributes: Record<string, unknown>,
) {
  if (value === null || !Number.isFinite(value)) return null;
  const volume = Number(attributes.volume_oz);
  if (
    comparisonMetric !== "price_per_gallon" ||
    !Number.isFinite(volume) ||
    volume <= 0
  )
    return null;
  return {
    value: value * (volume / 128),
    label: `per ${volume.toLocaleString("en-US", { maximumFractionDigits: 2 })} fl oz`,
  };
}

function positiveAttributeNumber(
  attributes: Record<string, unknown>,
  key: string,
) {
  const value = Number(attributes[key]);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function quantityLabel(value: number) {
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/**
 * Selects a human-readable price basis without changing the governed metric.
 * A fixed-volume cohort leads with its comparable package price. Mixed-volume
 * cohorts lead with fluid-ounce pricing. The canonical value remains available
 * for audit/export lineage.
 */
export function cohortPricePresentation(
  value: number | null,
  comparisonMetric: string,
  comparisonUnit: string,
  attributes: Record<string, unknown>,
): CohortPricePresentation {
  const canonicalUnitLabel = cohortUnitLabel(comparisonUnit);
  if (value === null || !Number.isFinite(value)) {
    return {
      primaryValue: null,
      primaryUnitLabel: canonicalUnitLabel,
      secondaryValue: null,
      secondaryUnitLabel: null,
      canonicalValue: null,
      canonicalUnitLabel,
    };
  }

  const normalizedMetric = comparisonMetric.trim().toLowerCase();
  const normalizedUnit = comparisonUnit.trim().toLowerCase();
  const isPerGallon =
    normalizedMetric === "price_per_gallon" || normalizedUnit === "usd/gallon";
  const isPerFluidOunce =
    normalizedMetric === "price_per_fluid_ounce" ||
    normalizedMetric === "price_per_fl_oz" ||
    normalizedUnit === "usd/fl_oz" ||
    normalizedUnit === "usd/fl oz";

  if (isPerGallon || isPerFluidOunce) {
    const perFluidOunce = isPerGallon ? value / 128 : value;
    const volumeOunces = positiveAttributeNumber(attributes, "volume_oz");
    if (volumeOunces !== null) {
      return {
        primaryValue: perFluidOunce * volumeOunces,
        primaryUnitLabel: `per ${quantityLabel(volumeOunces)} fl oz package`,
        secondaryValue: perFluidOunce,
        secondaryUnitLabel: "per fl oz",
        canonicalValue: value,
        canonicalUnitLabel,
      };
    }
    return {
      primaryValue: perFluidOunce,
      primaryUnitLabel: "per fl oz",
      secondaryValue: null,
      secondaryUnitLabel: null,
      canonicalValue: value,
      canonicalUnitLabel,
    };
  }

  return {
    primaryValue: value,
    primaryUnitLabel: canonicalUnitLabel,
    secondaryValue: null,
    secondaryUnitLabel: null,
    canonicalValue: value,
    canonicalUnitLabel,
  };
}

export function comparableCohorts(records: JsonObject[]): ComparableCohort[] {
  const cohorts = records.flatMap((row) => {
    const cohort = comparableCohort(row);
    return cohort && !cohort.overall ? [cohort] : [];
  });
  const unique = new Map<string, ComparableCohort>();
  for (const cohort of cohorts) {
    const current = unique.get(cohort.id);
    if (!current || cohort.matches > current.matches) {
      unique.set(cohort.id, cohort);
    }
  }
  return [...unique.values()];
}

export function sortComparableCohorts(
  cohorts: ComparableCohort[],
  sort: CohortSort,
) {
  return [...cohorts].sort((left, right) => {
    if (sort === "competitor_pressure") {
      return (
        right.competitorLowerRate - left.competitorLowerRate ||
        right.matchedGeographies - left.matchedGeographies ||
        left.segment.localeCompare(right.segment)
      );
    }
    if (sort === "gap") {
      return (
        Math.abs(right.medianGap ?? 0) - Math.abs(left.medianGap ?? 0) ||
        right.matchedGeographies - left.matchedGeographies ||
        left.segment.localeCompare(right.segment)
      );
    }
    return (
      right.matchedGeographies - left.matchedGeographies ||
      right.matches - left.matches ||
      left.segment.localeCompare(right.segment)
    );
  });
}
