import { describe, expect, it } from "vitest";

import {
  distributionCount,
  distributionCoverageRate,
  distributionLabel,
  distributionNoun,
} from "./distribution-presentation";

describe("distribution presentation", () => {
  it("uses only the explicit positive-price store-distribution count", () => {
    expect(
      distributionCount(
        {
          distribution_store_count: 83,
          service_area_presence_count: 7,
        },
        "store",
      ),
    ).toBe(83);
    expect(
      distributionCount(
        {
          search_observed_locations: 4_510,
          verified_available_locations: 4_510,
        } as never,
        "store",
      ),
    ).toBeNull();
  });

  it("keeps service-area presence separate from store distribution", () => {
    const evidence = {
      distribution_store_count: 0,
      service_area_presence_count: 126,
    };
    expect(distributionCount(evidence, "store")).toBe(0);
    expect(distributionCount(evidence, "service_area")).toBe(126);
    expect(distributionLabel("store")).toBe("Observed store distribution");
    expect(distributionLabel("service_area")).toBe(
      "Observed service-area presence",
    );
  });

  it("calculates coverage only against a coherent searched-location scope", () => {
    const evidence = {
      distribution_store_count: 83,
      service_area_presence_count: 0,
    };
    expect(distributionCoverageRate(evidence, "store", 100)).toBe(0.83);
    expect(distributionCoverageRate(evidence, "store", 0)).toBeNull();
    expect(distributionCoverageRate(evidence, "store", 82)).toBeNull();
  });

  it("uses dimension-specific nouns", () => {
    expect(distributionNoun("store", 1)).toBe("store");
    expect(distributionNoun("store", 2)).toBe("stores");
    expect(distributionNoun("service_area", 1)).toBe("service area");
    expect(distributionNoun("service_area", 2)).toBe("service areas");
  });
});
