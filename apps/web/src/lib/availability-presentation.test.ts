import { describe, expect, it } from "vitest";

import {
  distributionCoverageRate,
  distributionEvidenceLabel,
  hasArchitectureRetailerDistribution,
  hasDistributionPriceEvidence,
  hasObservedDistribution,
  serviceAreaPresenceDefinition,
  storeDistributionDefinition,
} from "./availability-presentation";

describe("distribution presentation compatibility", () => {
  it("accepts only the explicit two-dimensional distribution contract", () => {
    expect(
      hasObservedDistribution({
        distribution_store_count: 83,
        service_area_presence_count: 0,
      }),
    ).toBe(true);
    expect(
      hasObservedDistribution({
        distribution_store_count: 0,
        service_area_presence_count: 7,
      }),
    ).toBe(true);
    expect(
      hasObservedDistribution({
        verified_available_locations: 4_510,
        search_observed_locations: 4_510,
        observed_locations: 4_510,
      }),
    ).toBe(false);
    expect(
      hasObservedDistribution({
        distribution_store_count: 83,
      }),
    ).toBe(false);
  });

  it("labels stores and service areas separately", () => {
    expect(
      distributionEvidenceLabel({
        distribution_store_count: 83,
        service_area_presence_count: 2,
      }),
    ).toBe("83 stores in observed distribution · 2 service-area presences");
    expect(distributionEvidenceLabel({ observed_locations: 83 })).toBe(
      "Observed distribution not supplied",
    );
  });

  it("requires explicit distribution and positive price evidence", () => {
    const evidence = {
      distribution_store_count: 83,
      service_area_presence_count: 0,
    };
    expect(hasDistributionPriceEvidence(evidence, 83)).toBe(true);
    expect(hasDistributionPriceEvidence(evidence, 0)).toBe(false);
    expect(hasDistributionPriceEvidence({ observed_locations: 83 }, 83)).toBe(
      false,
    );
  });

  it("fails architecture evidence closed without both explicit counts", () => {
    expect(
      hasArchitectureRetailerDistribution({
        status: "available",
        sku_count: 10,
        distribution_store_count: 83,
        service_area_presence_count: 0,
      }),
    ).toBe(true);
    expect(
      hasArchitectureRetailerDistribution({
        status: "available",
        sku_count: 10,
        verified_available_locations: 4_510,
      }),
    ).toBe(false);
  });

  it("uses only explicit store distribution in coverage", () => {
    expect(
      distributionCoverageRate(
        {
          distribution_store_count: 83,
          service_area_presence_count: 0,
        },
        "store",
        4_510,
      ),
    ).toBeCloseTo(83 / 4_510);
    expect(
      distributionCoverageRate(
        { verified_available_locations: 4_510 },
        "store",
        4_510,
      ),
    ).toBeNull();
  });

  it("states the non-inventory contract without extrapolation", () => {
    expect(storeDistributionDefinition).toContain("price greater than $0");
    expect(storeDistributionDefinition).toContain("never extrapolated");
    expect(serviceAreaPresenceDefinition).toContain(
      "never presented as a store",
    );
  });
});
