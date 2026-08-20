import { describe, expect, it } from "vitest";

import { productsForObservedBrand } from "./assortment-presentation";

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
      },
      {
        product_id: "2",
        canonical_product_id: "walmart_us:2",
        name: "Other eggs",
        brand: "Other",
        observed_brand: "Other",
        observed_locations: 10,
        observed_zipcodes: 9,
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
});
