import { describe, expect, it } from "vitest";

import type { PriceMonitoringView } from "./api";
import { compactPriceMonitoringCatalog } from "./price-monitoring-catalog";

function fixture(productId: string | null): PriceMonitoringView {
  return {
    filters: { product_id: productId },
    distribution_gaps: {
      location_display: { returned: 1, total: 2, sampled: false },
      geographies: [{ key: "TX" }],
      locations: [{ scope_key: "store:1" }],
    },
    products: [
      {
        pdp: {
          enriched: true,
          authority: {
            identity: "pdp",
            price: "search",
            availability: "search",
          },
          description_full: "Large catalog-only payload",
          images: ["one", "two"],
        },
        price_histogram: [{ lower: 1, upper: 2, count: 1, share: 1 }],
        sample_locations: [{ scope_key: "store:1" }],
      },
    ],
  } as unknown as PriceMonitoringView;
}

describe("compactPriceMonitoringCatalog", () => {
  it("removes product-workspace-only evidence from catalog responses", () => {
    const compacted = compactPriceMonitoringCatalog(fixture(null));

    expect(compacted.products[0]?.pdp).toEqual({
      enriched: true,
      authority: {
        identity: "pdp",
        price: "search",
        availability: "search",
      },
    });
    expect(compacted.products[0]?.price_histogram).toEqual([]);
    expect(compacted.products[0]?.sample_locations).toEqual([]);
    expect(compacted.distribution_gaps.geographies).toEqual([]);
    expect(compacted.distribution_gaps.locations).toEqual([]);
    expect(compacted.distribution_gaps.location_display).toMatchObject({
      returned: 0,
      total: 2,
      sampled: true,
    });
  });

  it("preserves the complete product workspace response", () => {
    const full = fixture("product-1");
    expect(compactPriceMonitoringCatalog(full)).toBe(full);
  });
});
