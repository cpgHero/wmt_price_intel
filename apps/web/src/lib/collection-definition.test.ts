import { describe, expect, it } from "vitest";

import {
  buildCollectionDefinition,
  normalizeZipcodes,
  validateCollectionValues,
} from "./collection-definition";

const values = {
  definitionId: "strawberries-test",
  name: "Strawberry test",
  productPackId: "fresh_strawberries",
  productPackVersion: "1.0.0",
  keyword: "strawberries",
  zipcodes: ["01234", "44906"],
  retailerIds: ["walmart_us", "aldi_us", "amazon_us_same_day"] as const,
  maxPages: 1,
  maxCredits: 10,
  availabilityGateEnabled: true,
};

describe("collection definition builder", () => {
  it("preserves leading-zero ZIPs and creates a generic Product Pack definition", () => {
    expect(normalizeZipcodes("01234, 44906\n01234")).toEqual([
      "01234",
      "44906",
    ]);
    const config = buildCollectionDefinition({
      ...values,
      retailerIds: [...values.retailerIds],
    });
    expect(config.product_pack).toEqual({
      id: "fresh_strawberries",
      version: "1.0.0",
    });
    expect(config.geography).toMatchObject({
      strategy: "custom_zips",
      zipcodes: ["01234", "44906"],
    });
    expect(config.availability_gate).toMatchObject({
      retailer_ids: ["aldi_us"],
    });
  });

  it("validates ZIP and retailer scope before estimate", () => {
    expect(
      validateCollectionValues({
        ...values,
        zipcodes: ["1234"],
        retailerIds: [...values.retailerIds],
      }),
    ).toContain("five digits");
  });

  it("changes product category only through Product Pack values", () => {
    const config = buildCollectionDefinition({
      ...values,
      productPackId: "fresh_shell_eggs",
      productPackVersion: "1.1.0",
      keyword: "fresh eggs",
      retailerIds: [...values.retailerIds],
    });
    expect(config.product_pack).toEqual({
      id: "fresh_shell_eggs",
      version: "1.1.0",
    });
    expect(config.query).toMatchObject({ keyword: "fresh eggs" });
  });
});
