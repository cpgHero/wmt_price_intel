import { describe, expect, it } from "vitest";

import type { AssortmentBrand, AssortmentProduct } from "./api";
import {
  assortmentBrandsWithDistribution,
  assortmentProductsWithDistribution,
  productsForObservedBrand,
} from "./assortment-presentation";

function product(
  id: string,
  stores: number,
  serviceAreas: number,
  observedBrand = "Great Value",
): AssortmentProduct {
  return {
    product_id: id,
    canonical_product_id: `walmart_us:${id}`,
    name: `Product ${id}`,
    observed_brand: observedBrand,
    observed_locations: 4_510,
    observed_zipcodes: 4_000,
    distribution_store_count: stores,
    service_area_presence_count: serviceAreas,
  };
}

function brand(
  name: string,
  stores: number,
  serviceAreas: number,
): AssortmentBrand {
  return {
    brand: name,
    distinct_products: 2,
    observed_locations: 4_510,
    observed_zipcodes: 4_000,
    distribution_store_count: stores,
    service_area_presence_count: serviceAreas,
    location_share: 1,
  };
}

describe("assortment distribution presentation", () => {
  it("keeps store and service-area distribution while excluding legacy-only rows", () => {
    const legacyOnly = {
      ...product("legacy", 0, 0),
      distribution_store_count: undefined,
      service_area_presence_count: undefined,
      verified_available_locations: 4_510,
      search_observed_locations: 4_510,
      availability_status: "verified_in_stock",
    } as unknown as AssortmentProduct;

    expect(
      assortmentProductsWithDistribution([
        product("stores", 83, 0),
        product("service", 0, 7),
        product("none", 0, 0),
        legacyOnly,
      ]).map((row) => row.product_id),
    ).toEqual(["stores", "service"]);
  });

  it("requires both explicit distribution dimensions", () => {
    const partial = {
      ...product("partial", 83, 0),
      service_area_presence_count: undefined,
    } as unknown as AssortmentProduct;
    expect(assortmentProductsWithDistribution([partial])).toEqual([]);
  });

  it("uses the same fail-closed contract for brands", () => {
    expect(
      assortmentBrandsWithDistribution([
        brand("Stores", 83, 0),
        brand("Service", 0, 7),
        brand("None", 0, 0),
      ]).map((row) => row.brand),
    ).toEqual(["Stores", "Service"]);
  });

  it("matches governed observed brand identity after distribution filtering", () => {
    expect(
      productsForObservedBrand(
        [
          product("great-value", 83, 0, " Great   Value "),
          product("other", 83, 0, "Organic Valley"),
          product("no-distribution", 0, 0, "Great Value"),
        ],
        brand("great value", 83, 0),
      ).map((row) => row.product_id),
    ).toEqual(["great-value"]);
  });
});
