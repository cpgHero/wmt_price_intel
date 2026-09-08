import type { BrandWorkbenchBrand } from "./api";

export interface BrandDistributionPresentation {
  verified: boolean;
  productValue: string;
  productLabel: string;
  locationValue: string;
  locationLabel: string;
  evidenceValue: string;
  evidenceLabel: string;
  footprintLabel: string;
  footprintShare: number;
}

function count(value: number) {
  return value.toLocaleString("en-US");
}

function isNonNegativeInteger(value: number) {
  return Number.isInteger(value) && value >= 0;
}

/**
 * Only the explicit verified-local evidence mode may be presented as brand
 * distribution. Legacy Search reach and PDP joins remain useful identity or
 * discovery evidence, but fail closed for local carriage.
 */
export function brandDistributionPresentation(
  brand: BrandWorkbenchBrand,
): BrandDistributionPresentation {
  const verifiedEvidenceIsCoherent =
    brand.distribution_evidence === "verified_local_search_availability" &&
    Number.isInteger(brand.observed_products) &&
    brand.observed_products > 0 &&
    Number.isInteger(brand.observed_locations) &&
    brand.observed_locations > 0 &&
    isNonNegativeInteger(brand.observed_zipcodes) &&
    Number.isFinite(brand.location_share) &&
    brand.location_share >= 0 &&
    brand.location_share <= 1 &&
    brand.distribution_tier !== "unknown";
  if (verifiedEvidenceIsCoherent) {
    return {
      verified: true,
      productValue: count(brand.observed_products),
      productLabel:
        brand.observed_products === 1
          ? "verified-available product"
          : "verified-available products",
      locationValue: count(brand.observed_locations),
      locationLabel:
        brand.observed_locations === 1
          ? "verified location"
          : "verified locations",
      evidenceValue: count(brand.observed_zipcodes),
      evidenceLabel:
        brand.observed_zipcodes === 1 ? "verified ZIP" : "verified ZIPs",
      footprintLabel: `${(brand.location_share * 100).toFixed(1)}% of retailer locations have verified local availability`,
      footprintShare: brand.location_share,
    };
  }

  if (brand.distribution_evidence === "verified_local_search_availability") {
    return {
      verified: false,
      productValue: "—",
      productLabel: "verified-available products",
      locationValue: "—",
      locationLabel: "verified locations",
      evidenceValue: "Incomplete",
      evidenceLabel: "availability evidence",
      footprintLabel:
        "Availability unverified; the reported verified-local evidence is incomplete or contradictory",
      footprintShare: 0,
    };
  }

  if (brand.distribution_evidence === "search_brand_field") {
    return {
      verified: false,
      productValue: count(brand.observed_products),
      productLabel:
        brand.observed_products === 1
          ? "Search-observed product"
          : "Search-observed products",
      locationValue: count(brand.observed_locations),
      locationLabel:
        brand.observed_locations === 1
          ? "Search-observed location"
          : "Search-observed locations",
      evidenceValue: count(brand.observed_zipcodes),
      evidenceLabel:
        brand.observed_zipcodes === 1
          ? "Search-observed ZIP"
          : "Search-observed ZIPs",
      footprintLabel:
        "Availability unverified; legacy Search reach does not prove local carriage",
      footprintShare: 0,
    };
  }

  if (brand.distribution_evidence === "pdp_identity_joined_to_matched_search") {
    return {
      verified: false,
      productValue: count(brand.observed_products),
      productLabel:
        brand.observed_products === 1
          ? "PDP identity product"
          : "PDP identity products",
      locationValue: count(brand.observed_zipcodes),
      locationLabel:
        brand.observed_zipcodes === 1 ? "matched ZIP" : "matched ZIPs",
      evidenceValue: "PDP + Search",
      evidenceLabel: "identity evidence",
      footprintLabel: `Search identity match in at least ${count(brand.observed_zipcodes)} ZIP${brand.observed_zipcodes === 1 ? "" : "s"}; availability unverified`,
      footprintShare: 0,
    };
  }

  return {
    verified: false,
    productValue: count(brand.observed_products),
    productLabel:
      brand.observed_products === 1
        ? "PDP identity product"
        : "PDP identity products",
    locationValue: "—",
    locationLabel: "verified locations",
    evidenceValue: "PDP only",
    evidenceLabel: "identity evidence",
    footprintLabel:
      "PDP identity is available; no verified local availability evidence is present",
    footprintShare: 0,
  };
}
