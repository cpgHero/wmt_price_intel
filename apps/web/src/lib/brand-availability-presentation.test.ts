import { describe, expect, it } from "vitest";

import type { BrandWorkbenchBrand } from "./api";
import { brandDistributionPresentation } from "./brand-availability-presentation";

function brand(
  distribution_evidence: BrandWorkbenchBrand["distribution_evidence"],
): BrandWorkbenchBrand {
  return {
    retailer_id: "walmart_us",
    normalized_brand: "example",
    display_brand: "Example",
    role: "national",
    status: "suggested",
    origin: "deterministic",
    canonical_brand_id: null,
    canonical_brand_name: null,
    candidate_status: "none",
    candidate_matches: [],
    observed_products: 2,
    observed_locations: 4_510,
    observed_zipcodes: 3_900,
    location_share: 1,
    distribution_tier:
      distribution_evidence === "verified_local_search_availability"
        ? "broad"
        : "unknown",
    distribution_evidence,
    product_examples: [],
  };
}

describe("brandDistributionPresentation", () => {
  it("presents explicit local availability as verified distribution", () => {
    const result = brandDistributionPresentation(
      brand("verified_local_search_availability"),
    );

    expect(result.verified).toBe(true);
    expect(result.productLabel).toBe("verified-available products");
    expect(result.locationLabel).toBe("verified locations");
    expect(result.evidenceLabel).toBe("verified ZIPs");
    expect(result.footprintLabel).toContain("verified local availability");
    expect(result.footprintShare).toBe(1);
  });

  it("labels legacy Search brand reach as unverified", () => {
    const result = brandDistributionPresentation(brand("search_brand_field"));

    expect(result.verified).toBe(false);
    expect(result.productLabel).toBe("Search-observed products");
    expect(result.locationLabel).toBe("Search-observed locations");
    expect(result.evidenceLabel).toBe("Search-observed ZIPs");
    expect(result.footprintLabel).toBe(
      "Availability unverified; legacy Search reach does not prove local carriage",
    );
    expect(result.footprintShare).toBe(0);
  });

  it("fails closed for a contradictory verified-local mode", () => {
    const contradictory = brand("verified_local_search_availability");
    contradictory.observed_locations = 0;
    contradictory.distribution_tier = "unknown";

    const result = brandDistributionPresentation(contradictory);

    expect(result.verified).toBe(false);
    expect(result.productValue).toBe("—");
    expect(result.locationValue).toBe("—");
    expect(result.footprintLabel).toContain("incomplete or contradictory");
    expect(result.footprintShare).toBe(0);
  });

  it("keeps authoritative zero counters unverified without reviving legacy reach", () => {
    const corrected = brand("search_brand_field");
    corrected.observed_products = 0;
    corrected.observed_locations = 0;
    corrected.observed_zipcodes = 0;
    corrected.location_share = 0;

    const result = brandDistributionPresentation(corrected);

    expect(result.verified).toBe(false);
    expect(result.productValue).toBe("0");
    expect(result.productLabel).toBe("Search-observed products");
    expect(result.locationValue).toBe("0");
    expect(result.footprintShare).toBe(0);
  });

  it("does not promote PDP joins or PDP identity to carriage", () => {
    const joined = brandDistributionPresentation(
      brand("pdp_identity_joined_to_matched_search"),
    );
    const pdpOnly = brandDistributionPresentation(brand("pdp_identity_only"));

    expect(joined.verified).toBe(false);
    expect(joined.productLabel).toBe("PDP identity products");
    expect(joined.footprintLabel).toContain("availability unverified");
    expect(joined.footprintShare).toBe(0);
    expect(pdpOnly.verified).toBe(false);
    expect(pdpOnly.footprintLabel).toContain(
      "no verified local availability evidence",
    );
  });
});
