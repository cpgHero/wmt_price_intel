export type DistributionLocationDimension = "store" | "service_area";

export const storeDistributionDefinition =
  "A product counts in a store's observed distribution when that exact retailer product ID appears in a store-level Search result with a listed price greater than $0. Counts are distinct stores and are never extrapolated to stores that were not observed.";

export const serviceAreaPresenceDefinition =
  "Service-area presence counts distinct positive-price Search contexts. It is reported separately and is never presented as a store count.";

function nonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" &&
    Number.isInteger(value) &&
    Number.isFinite(value) &&
    value >= 0
    ? value
    : null;
}

/**
 * Read only the explicit distribution contract. Legacy Search-reach,
 * availability, and generic location counts are intentionally not fallbacks.
 */
export function distributionCount(
  evidence: object | null | undefined,
  dimension: DistributionLocationDimension,
): number | null {
  const record = evidence as Record<string, unknown> | null | undefined;
  return nonNegativeInteger(
    dimension === "store"
      ? record?.distribution_store_count
      : record?.service_area_presence_count,
  );
}

export function distributionCoverageRate(
  evidence: object | null | undefined,
  dimension: DistributionLocationDimension,
  searchedLocations: unknown,
): number | null {
  const distributed = distributionCount(evidence, dimension);
  const searched = nonNegativeInteger(searchedLocations);
  if (
    distributed === null ||
    searched === null ||
    searched === 0 ||
    distributed > searched
  ) {
    return null;
  }
  return distributed / searched;
}

export function distributionNoun(
  dimension: DistributionLocationDimension,
  value: number,
): string {
  if (dimension === "store") return value === 1 ? "store" : "stores";
  return value === 1 ? "service area" : "service areas";
}

export function distributionLabel(
  dimension: DistributionLocationDimension,
): string {
  return dimension === "store"
    ? "Observed store distribution"
    : "Observed service-area presence";
}
