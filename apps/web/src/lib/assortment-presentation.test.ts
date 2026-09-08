import { describe, expect, it } from "vitest";

import {
  isVerifiedAssortmentProduct,
  productsForObservedBrand,
  verifiedAssortmentBrands,
  verifiedAssortmentProducts,
} from "./assortment-presentation";

describe("productsForObservedBrand", () => {
  it("uses the governed observed brand instead of a conflicting PDP label", () => {
    const products = [
      {
        product_id: "1",
        canonical_product_id: "walmart_us:1",
        name: "Large eggs",
        brand: "Happy Egg Co",
        observed_brand: "Happy Egg",
        observed_locations: 20,
        observed_zipcodes: 18,
        verified_available_locations: 20,
        verified_available_zipcodes: 18,
        search_observed_locations: 20,
        search_observed_zipcodes: 18,
        availability_status: "verified_in_stock" as const,
      },
      {
        product_id: "2",
        canonical_product_id: "walmart_us:2",
        name: "Other eggs",
        brand: "Other",
        observed_brand: "Other",
        observed_locations: 10,
        observed_zipcodes: 9,
        verified_available_locations: 10,
        verified_available_zipcodes: 9,
        search_observed_locations: 10,
        search_observed_zipcodes: 9,
        availability_status: "verified_in_stock" as const,
      },
    ];

    expect(
      productsForObservedBrand(products, {
        brand: " happy egg ",
        distinct_products: 1,
        observed_locations: 20,
        observed_zipcodes: 18,
        location_share: 0.2,
      }).map((product) => product.product_id),
    ).toEqual(["1"]);
  });

  it("does not replace an explicitly unbranded Search product with its PDP brand", () => {
    const products = [
      {
        product_id: "1",
        canonical_product_id: "walmart_us:1",
        name: "Search unbranded eggs",
        brand: "Hillandale farms",
        observed_brand: null,
        observed_locations: 18,
        observed_zipcodes: 18,
        verified_available_locations: 18,
        verified_available_zipcodes: 18,
        search_observed_locations: 18,
        search_observed_zipcodes: 18,
        availability_status: "verified_in_stock" as const,
      },
      {
        product_id: "2",
        canonical_product_id: "walmart_us:2",
        name: "Search branded eggs",
        brand: "Hillandale farms",
        observed_brand: "Hillandale farms",
        observed_locations: 2,
        observed_zipcodes: 2,
        verified_available_locations: 2,
        verified_available_zipcodes: 2,
        search_observed_locations: 2,
        search_observed_zipcodes: 2,
        availability_status: "verified_in_stock" as const,
      },
    ];

    expect(
      productsForObservedBrand(products, {
        brand: "Hillandale farms",
        distinct_products: 1,
        observed_locations: 2,
        observed_zipcodes: 2,
        location_share: 0.01,
      }).map((product) => product.product_id),
    ).toEqual(["2"]);
  });

  it("excludes Search-only and legacy products from verified assortment sets", () => {
    const products = [
      {
        product_id: "verified",
        canonical_product_id: "walmart_us:verified",
        name: "Verified product",
        observed_brand: "Example",
        observed_locations: 4,
        observed_zipcodes: 4,
        verified_available_locations: 4,
        verified_available_zipcodes: 4,
        search_observed_locations: 4,
        search_observed_zipcodes: 4,
        availability_status: "verified_in_stock" as const,
      },
      {
        product_id: "sponsored",
        canonical_product_id: "walmart_us:sponsored",
        name: "Sponsored Search result",
        observed_brand: "Example",
        observed_locations: 0,
        observed_zipcodes: 0,
        search_observed_locations: 4_510,
        verified_available_locations: 0,
        verified_available_zipcodes: 0,
        availability_status: "unverified_sponsored" as const,
      },
      {
        product_id: "legacy",
        canonical_product_id: "walmart_us:legacy",
        name: "Legacy Search result",
        observed_brand: "Example",
        observed_locations: 4_510,
        observed_zipcodes: 3_900,
      },
      {
        product_id: "contradictory",
        canonical_product_id: "walmart_us:contradictory",
        name: "Contradictory result",
        observed_brand: "Example",
        observed_locations: 5,
        observed_zipcodes: 5,
        verified_available_locations: 0,
        verified_available_zipcodes: 0,
        search_observed_locations: 4,
        search_observed_zipcodes: 4,
        availability_status: "verified_in_stock" as const,
      },
    ];

    expect(isVerifiedAssortmentProduct(products[0])).toBe(true);
    expect(
      verifiedAssortmentProducts(products).map((row) => row.product_id),
    ).toEqual(["verified"]);
    expect(
      productsForObservedBrand(products, {
        brand: "Example",
        distinct_products: 1,
        observed_locations: 4,
        observed_zipcodes: 4,
        location_share: 1,
      }).map((row) => row.product_id),
    ).toEqual(["verified"]);
  });

  it("fails closed for legacy Search-only brand summaries", () => {
    expect(
      verifiedAssortmentBrands([
        {
          brand: "Verified",
          distinct_products: 2,
          observed_locations: 8,
          observed_zipcodes: 8,
          verified_available_products: 2,
          verified_available_locations: 8,
          verified_available_zipcodes: 8,
          location_share: 0.8,
        },
        {
          brand: "Legacy Search",
          distinct_products: 9,
          observed_locations: 4_510,
          observed_zipcodes: 3_900,
          location_share: 1,
        },
      ]).map((row) => row.brand),
    ).toEqual(["Verified"]);
  });
});
