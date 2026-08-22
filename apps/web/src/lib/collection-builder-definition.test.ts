import { describe, expect, it } from "vitest";

import type {
  CollectionBuilderOptions,
  CollectionGeographyResolution,
} from "./api";
import {
  buildApprovedCollectionDefinition,
  type BuilderDefinitionValues,
} from "./collection-builder-definition";

const options: CollectionBuilderOptions = {
  retailers: [
    {
      id: "walmart_us",
      display_name: "Walmart (US)",
      adapter_id: "metricscart.walmart.search_zip.v2",
      location_dimension: "store_zip",
      credits_per_page: 1,
      supports_pagination: true,
      status: "enabled",
    },
    {
      id: "giant_eagle_us",
      display_name: "Giant Eagle",
      adapter_id: "metricscart.gianteagle.serp_zip",
      location_dimension: "store_zip",
      credits_per_page: 2,
      supports_pagination: false,
      status: "enabled",
    },
    {
      id: "amazon_us_same_day",
      display_name: "Amazon Same Day (US)",
      adapter_id: "metricscart.amazon.search_zip",
      location_dimension: "zipcode",
      credits_per_page: 2,
      supports_pagination: true,
      status: "enabled",
    },
  ],
  product_packs: [],
  default_product_pack_id: "fresh_shell_eggs",
  geography: {
    primary_selection_modes: ["all_locations"],
    competitor_correspondence_modes: ["primary_states"],
    radius_miles: [1, 3, 5],
  },
  product_detail_policies: ["disabled"],
};

const values: BuilderDefinitionValues = {
  definitionId: "fourteen-retailer-eggs",
  name: "Fourteen-retailer eggs",
  productPackId: "fresh_shell_eggs",
  productPackVersion: "1.0.0",
  keyword: "eggs",
  primaryRetailerId: "walmart_us",
  competitorRetailerIds: ["giant_eagle_us", "amazon_us_same_day"],
  maxPagesByRetailer: {
    walmart_us: 2,
    giant_eagle_us: 5,
    amazon_us_same_day: 2,
  },
  maxCredits: 100,
  availabilityGateEnabled: true,
  scheduleType: "manual",
  cronExpression: "",
  timezone: "America/Chicago",
  delivery: {
    webReport: true,
    excel: false,
    leadershipEmail: false,
    auditPackage: false,
  },
  productDetailPolicy: "disabled",
};

const resolution: CollectionGeographyResolution = {
  id: "00000000-0000-0000-0000-000000000001",
  request: {
    primary_retailer_id: "walmart_us",
    competitor_retailer_ids: ["giant_eagle_us", "amazon_us_same_day"],
    country: "US",
    primary_selection: { mode: "all_locations" },
    competitor_correspondence: { mode: "primary_states" },
  },
  checksum: "test-checksum",
  status: "ready",
  counts: { total: 0, primary: 0, competitors: {} },
  locations: [],
  edges: [],
  created_at: "2026-08-22T00:00:00Z",
};

describe("approved collection definition builder", () => {
  it("forces a single page for endpoints that do not support pagination", () => {
    const definition = buildApprovedCollectionDefinition(
      values,
      options,
      resolution,
    );
    const retailers = definition.retailers as Array<Record<string, unknown>>;

    expect(
      retailers.find((retailer) => retailer.retailer_id === "giant_eagle_us"),
    ).toMatchObject({ max_pages_override: 1 });
    expect(
      retailers.find((retailer) => retailer.retailer_id === "walmart_us"),
    ).toMatchObject({ max_pages_override: 2 });
  });

  it("gates the primary and every selected competitor, including ZIP-only retailers", () => {
    const definition = buildApprovedCollectionDefinition(
      values,
      options,
      resolution,
    );

    expect(definition.availability_gate).toMatchObject({
      retailer_ids: ["walmart_us", "giant_eagle_us", "amazon_us_same_day"],
    });
  });
});
