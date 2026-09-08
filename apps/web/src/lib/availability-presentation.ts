import {
  distributionCount,
  distributionCoverageRate,
  serviceAreaPresenceDefinition,
  storeDistributionDefinition,
} from "./distribution-presentation";

interface DistributionEvidence {
  distribution_store_count?: unknown;
  service_area_presence_count?: unknown;
  [key: string]: unknown;
}

function nonNegativeFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

/**
 * Require the complete two-dimensional distribution contract. Historic
 * availability and observed-location fields are deliberately not accepted.
 */
export function hasObservedDistribution(
  evidence: DistributionEvidence | null | undefined,
): boolean {
  const stores = distributionCount(evidence, "store");
  const serviceAreas = distributionCount(evidence, "service_area");
  return (
    stores !== null && serviceAreas !== null && (stores > 0 || serviceAreas > 0)
  );
}

export function distributionEvidenceLabel(
  evidence: DistributionEvidence | null | undefined,
): string {
  const stores = distributionCount(evidence, "store");
  const serviceAreas = distributionCount(evidence, "service_area");
  if (stores === null || serviceAreas === null) {
    return "Observed distribution not supplied";
  }
  return `${stores.toLocaleString("en-US")} ${stores === 1 ? "store" : "stores"} in observed distribution · ${serviceAreas.toLocaleString("en-US")} service-area ${serviceAreas === 1 ? "presence" : "presences"}`;
}

export function hasDistributionPriceEvidence(
  evidence: DistributionEvidence | null | undefined,
  priceObservations: unknown,
): boolean {
  const observations = nonNegativeFiniteNumber(priceObservations);
  return (
    hasObservedDistribution(evidence) &&
    observations !== null &&
    observations > 0
  );
}

export function hasArchitectureRetailerDistribution(retailer: {
  status?: unknown;
  sku_count?: unknown;
  distribution_store_count?: unknown;
  service_area_presence_count?: unknown;
  [key: string]: unknown;
}): boolean {
  const skus = nonNegativeFiniteNumber(retailer.sku_count);
  return (
    retailer.status === "available" &&
    skus !== null &&
    skus > 0 &&
    hasObservedDistribution(retailer)
  );
}

export {
  distributionCount,
  distributionCoverageRate,
  serviceAreaPresenceDefinition,
  storeDistributionDefinition,
};
