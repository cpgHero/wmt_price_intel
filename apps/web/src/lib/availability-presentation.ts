export type AvailabilityStatus =
  | "verified_in_stock"
  | "explicitly_out_of_stock"
  | "unverified_sponsored"
  | "unverified";

interface AvailabilityEvidence {
  availability_status?: unknown;
  verified_local_availability?: unknown;
  in_stock?: unknown;
  is_sponsored?: unknown;
}

function nonNegativeFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

const availabilityStatuses = new Set<AvailabilityStatus>([
  "verified_in_stock",
  "explicitly_out_of_stock",
  "unverified_sponsored",
  "unverified",
]);

/**
 * Presentation must consume the governed availability classification rather
 * than infer local carriage from a positive Search price. Missing legacy
 * fields and contradictory values therefore fail closed to unverified.
 */
export function availabilityStatus(
  evidence: AvailabilityEvidence | null | undefined,
): AvailabilityStatus {
  const status = evidence?.availability_status;
  if (
    typeof status !== "string" ||
    !availabilityStatuses.has(status as AvailabilityStatus)
  ) {
    return "unverified";
  }
  const canonicalStatus: AvailabilityStatus =
    evidence?.in_stock === false
      ? "explicitly_out_of_stock"
      : evidence?.is_sponsored === true
        ? "unverified_sponsored"
        : evidence?.in_stock === true && evidence?.is_sponsored === false
          ? "verified_in_stock"
          : "unverified";
  const verified = canonicalStatus === "verified_in_stock";
  if (
    status !== canonicalStatus ||
    evidence?.verified_local_availability !== verified
  ) {
    return "unverified";
  }
  return canonicalStatus;
}

export function isVerifiedLocalAvailability(
  evidence: AvailabilityEvidence | null | undefined,
): boolean {
  return availabilityStatus(evidence) === "verified_in_stock";
}

export function availabilityEvidenceLabel(
  evidence: AvailabilityEvidence | null | undefined,
): string {
  const status = availabilityStatus(evidence);
  if (status === "verified_in_stock") return "Verified locally in stock";
  if (status === "explicitly_out_of_stock") return "Explicitly out of stock";
  if (status === "unverified_sponsored") {
    return "Unverified · sponsored Search result";
  }
  return "Unverified Search result";
}

export function priceEvidenceLabel(
  evidence: AvailabilityEvidence | null | undefined,
): string {
  return isVerifiedLocalAvailability(evidence)
    ? "Verified local Search price"
    : "Search-listed price";
}

/**
 * Product breadth uses the full eligible local-query population as its
 * denominator. The known-stock denominator intentionally is not used here:
 * sponsored or unknown-stock Search rows must not make sparse proof look like
 * 100% carriage.
 */
export function verifiedLocationCoverageRate(
  verifiedAvailableLocations: unknown,
  eligibleLocations: unknown,
): number | null {
  const verified = nonNegativeFiniteNumber(verifiedAvailableLocations);
  const eligible = nonNegativeFiniteNumber(eligibleLocations);
  if (verified === null || eligible === null || eligible === 0) return null;
  if (verified > eligible) return null;
  return verified / eligible;
}

export function hasVerifiedLocalPriceEvidence(
  verifiedAvailableLocations: unknown,
  verifiedPriceObservations: unknown,
): boolean {
  const locations = nonNegativeFiniteNumber(verifiedAvailableLocations);
  const observations = nonNegativeFiniteNumber(verifiedPriceObservations);
  return (
    locations !== null &&
    locations > 0 &&
    observations !== null &&
    observations > 0
  );
}

export function hasVerifiedArchitectureRetailerEvidence(retailer: {
  status?: unknown;
  sku_count?: unknown;
  verified_available_locations?: unknown;
}): boolean {
  const skus = nonNegativeFiniteNumber(retailer.sku_count);
  const locations = nonNegativeFiniteNumber(
    retailer.verified_available_locations,
  );
  return (
    retailer.status === "available" &&
    skus !== null &&
    skus > 0 &&
    locations !== null &&
    locations > 0
  );
}
