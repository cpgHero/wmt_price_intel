import { describe, expect, it } from "vitest";

import {
  availabilityEvidenceLabel,
  availabilityStatus,
  hasVerifiedArchitectureRetailerEvidence,
  hasVerifiedLocalPriceEvidence,
  isVerifiedLocalAvailability,
  priceEvidenceLabel,
  verifiedLocationCoverageRate,
} from "./availability-presentation";

describe("availability presentation", () => {
  it("fails closed for legacy and contradictory evidence", () => {
    expect(availabilityStatus(undefined)).toBe("unverified");
    expect(
      availabilityStatus({ availability_status: "verified_in_stock" }),
    ).toBe("unverified");
    expect(
      availabilityStatus({
        availability_status: "verified_in_stock",
        verified_local_availability: false,
        in_stock: true,
        is_sponsored: false,
      }),
    ).toBe("unverified");
    expect(
      availabilityStatus({
        availability_status: "explicitly_out_of_stock",
        verified_local_availability: false,
        in_stock: true,
        is_sponsored: false,
      }),
    ).toBe("unverified");
    expect(
      availabilityStatus({
        availability_status: "unverified_sponsored",
        verified_local_availability: false,
        in_stock: true,
        is_sponsored: false,
      }),
    ).toBe("unverified");
    expect(
      availabilityStatus({
        availability_status: "unverified",
        verified_local_availability: true,
        in_stock: null,
        is_sponsored: null,
      }),
    ).toBe("unverified");
    expect(
      availabilityStatus({
        availability_status: "verified_in_stock",
        verified_local_availability: true,
        in_stock: true,
        is_sponsored: true,
      }),
    ).toBe("unverified");
    expect(
      availabilityStatus({
        availability_status: "verified_in_stock",
        verified_local_availability: true,
        in_stock: true,
      }),
    ).toBe("unverified");
    expect(isVerifiedLocalAvailability({})).toBe(false);
  });

  it("fails closed when an architecture retailer lacks explicit verified breadth", () => {
    expect(
      hasVerifiedArchitectureRetailerEvidence({
        status: "available",
        sku_count: 3,
        verified_available_locations: 20,
      }),
    ).toBe(true);
    expect(
      hasVerifiedArchitectureRetailerEvidence({
        status: "available",
        sku_count: 3,
        verified_available_locations: 0,
      }),
    ).toBe(false);
    expect(
      hasVerifiedArchitectureRetailerEvidence({
        status: "available",
        sku_count: 3,
      }),
    ).toBe(false);
    expect(
      hasVerifiedArchitectureRetailerEvidence({
        status: "unavailable",
        sku_count: 3,
        verified_available_locations: 20,
      }),
    ).toBe(false);
  });

  it("reserves local-availability and local-price labels for governed proof", () => {
    const verified = {
      availability_status: "verified_in_stock",
      verified_local_availability: true,
      in_stock: true,
      is_sponsored: false,
    };

    expect(isVerifiedLocalAvailability(verified)).toBe(true);
    expect(availabilityEvidenceLabel(verified)).toBe(
      "Verified locally in stock",
    );
    expect(priceEvidenceLabel(verified)).toBe("Verified local Search price");
  });

  it("never turns sponsored Search exposure into availability", () => {
    const sponsored = {
      availability_status: "unverified_sponsored",
      verified_local_availability: false,
      in_stock: true,
      is_sponsored: true,
    };

    expect(isVerifiedLocalAvailability(sponsored)).toBe(false);
    expect(availabilityEvidenceLabel(sponsored)).toBe(
      "Unverified · sponsored Search result",
    );
    expect(priceEvidenceLabel(sponsored)).toBe("Search-listed price");
  });

  it("distinguishes explicit out-of-stock evidence from Search ambiguity", () => {
    const unavailable = {
      availability_status: "explicitly_out_of_stock",
      verified_local_availability: false,
      in_stock: false,
      is_sponsored: false,
    };

    expect(availabilityEvidenceLabel(unavailable)).toBe(
      "Explicitly out of stock",
    );
    expect(priceEvidenceLabel(unavailable)).toBe("Search-listed price");
  });

  it("uses eligible locations as the product availability denominator", () => {
    expect(verifiedLocationCoverageRate(126, 4_683)).toBeCloseTo(126 / 4_683);
    expect(verifiedLocationCoverageRate(0, 4_510)).toBe(0);
  });

  it("never turns a sponsored-only known-signal denominator into 100% carriage", () => {
    // A known-signal rate could be 126 / (126 + 0) = 100%, while 4,384
    // sponsored rows remain unverified. Eligible-location coverage stays 2.7%.
    expect(verifiedLocationCoverageRate(126, 4_510)).toBeCloseTo(126 / 4_510);
    expect(verifiedLocationCoverageRate(126, 126)).toBe(1);
    expect(verifiedLocationCoverageRate(4_511, 4_510)).toBeNull();
  });

  it("conditions verified price labels on both locations and price rows", () => {
    expect(hasVerifiedLocalPriceEvidence(1, 1)).toBe(true);
    expect(hasVerifiedLocalPriceEvidence(0, 12)).toBe(false);
    expect(hasVerifiedLocalPriceEvidence(12, 0)).toBe(false);
    expect(hasVerifiedLocalPriceEvidence(undefined, 12)).toBe(false);
  });
});
