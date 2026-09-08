import { describe, expect, it } from "vitest";

import type { BrandWorkbenchBrand } from "./api";
import { brandDistributionPresentation } from "./brand-availability-presentation";

function brand(
  overrides: Partial<BrandWorkbenchBrand> = {},
): BrandWorkbenchBrand {
  return {
    retailer_id: "walmart_us",
    normalized_brand: "great value",
    display_brand: "Great Value",
    role: "private_label",
    status: "confirmed",
    origin: "product_pack",
    canonical_brand_id: null,
    canonical_brand_name: null,
    candidate_status: "none",
    candidate_matches: [],
    observed_products: 12,
    observed_locations: 4_510,
    observed_zipcodes: 4_000,
    distribution_store_count: 0,
    service_area_presence_count: 0,
    location_share: 1,
    distribution_tier: "broad",
    distribution_evidence: "search_brand_field",
    product_examples: [],
    ...overrides,
  } as BrandWorkbenchBrand;
}

describe("brand distribution presentation", () => {
  it("presents explicit stores and service areas separately", () => {
    const result = brandDistributionPresentation(
      brand({
        distribution_store_count: 83,
        service_area_presence_count: 2,
      }),
    );

    expect(result.contractSupplied).toBe(true);
    expect(result.hasDistribution).toBe(true);
    expect(result.productLabel).toBe("products with observed distribution");
    expect(result.locationValue).toBe("83");
    expect(result.locationLabel).toBe("stores in observed distribution");
    expect(result.evidenceValue).toBe("2");
    expect(result.evidenceLabel).toBe("service-area presences");
    expect(result.footprintLabel).toContain("price greater than $0");
    expect(result.footprintLabel).toContain("never extrapolated");
  });

  it("does not fall back to legacy reach, footprint share, or evidence mode", () => {
    const result = brandDistributionPresentation(
      brand({
        observed_locations: 4_510,
        observed_zipcodes: 4_000,
        location_share: 1,
        distribution_store_count: undefined,
        service_area_presence_count: undefined,
      }),
    );

    expect(result.contractSupplied).toBe(false);
    expect(result.hasDistribution).toBe(false);
    expect(result.locationValue).toBe("—");
    expect(result.evidenceValue).toBe("—");
    expect(result.footprintLabel).toContain("not supplied");
  });

  it("keeps identity and discovery product labels separate from distribution", () => {
    const discovered = brandDistributionPresentation(
      brand({
        distribution_store_count: 0,
        service_area_presence_count: 0,
      }),
    );
    const identity = brandDistributionPresentation(
      brand({
        distribution_evidence: "pdp_identity_only",
        distribution_store_count: 0,
        service_area_presence_count: 0,
      }),
    );

    expect(discovered.productLabel).toBe("Search-observed products");
    expect(discovered.hasDistribution).toBe(false);
    expect(identity.productLabel).toBe("identity products");
    expect(identity.hasDistribution).toBe(false);
  });
});
