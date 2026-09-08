import type { BrandWorkbenchBrand } from "./api";
import {
  distributionCount,
  serviceAreaPresenceDefinition,
  storeDistributionDefinition,
} from "./distribution-presentation";

export interface BrandDistributionPresentation {
  contractSupplied: boolean;
  hasDistribution: boolean;
  productValue: string;
  productLabel: string;
  locationValue: string;
  locationLabel: string;
  evidenceValue: string;
  evidenceLabel: string;
  footprintLabel: string;
}

function count(value: number) {
  return value.toLocaleString("en-US");
}

function productLabel(brand: BrandWorkbenchBrand) {
  if (brand.distribution_evidence === "search_brand_field") {
    return brand.observed_products === 1
      ? "Search-observed product"
      : "Search-observed products";
  }
  return brand.observed_products === 1
    ? "identity product"
    : "identity products";
}

/**
 * Brand footprint uses only the explicit distribution fields. Historic
 * availability modes, observed-location counts, ZIP counts, footprint shares,
 * and distribution tiers are retained as source metadata but never converted
 * into public distribution claims.
 */
export function brandDistributionPresentation(
  brand: BrandWorkbenchBrand,
): BrandDistributionPresentation {
  const stores = distributionCount(brand, "store");
  const serviceAreas = distributionCount(brand, "service_area");
  const contractSupplied = stores !== null && serviceAreas !== null;
  const hasDistribution =
    stores !== null &&
    serviceAreas !== null &&
    (stores > 0 || serviceAreas > 0);

  return {
    contractSupplied,
    hasDistribution,
    productValue: count(brand.observed_products),
    productLabel: hasDistribution
      ? brand.observed_products === 1
        ? "product with observed distribution"
        : "products with observed distribution"
      : productLabel(brand),
    locationValue: stores === null ? "—" : count(stores),
    locationLabel:
      stores === 1
        ? "store in observed distribution"
        : "stores in observed distribution",
    evidenceValue: serviceAreas === null ? "—" : count(serviceAreas),
    evidenceLabel:
      serviceAreas === 1 ? "service-area presence" : "service-area presences",
    footprintLabel: !contractSupplied
      ? "Observed distribution was not supplied under the positive-price Search contract."
      : hasDistribution
        ? `${storeDistributionDefinition} ${serviceAreaPresenceDefinition}`
        : "No positive-price store Search distribution or service-area presence was observed.",
  };
}
