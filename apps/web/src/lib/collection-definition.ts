import type { JsonObject } from "./api";

export const RETAILER_OPTIONS = [
  {
    id: "walmart_us",
    label: "Walmart",
    adapterId: "metricscart_walmart_search_zipcode_v2",
    sort: "Best Match",
    credits: 1,
  },
  {
    id: "aldi_us",
    label: "ALDI",
    adapterId: "metricscart_new_aldi_serp_zipcode",
    sort: null,
    credits: 2,
  },
  {
    id: "amazon_us_same_day",
    label: "Amazon Same Day",
    adapterId: "metricscart_amazon_same_day_zipcode",
    sort: "Featured",
    credits: 2,
  },
] as const;

export type RetailerId = (typeof RETAILER_OPTIONS)[number]["id"];

export interface CollectionFormValues {
  definitionId: string;
  name: string;
  productPackId: string;
  productPackVersion: string;
  keyword: string;
  zipcodes: string[];
  retailerIds: RetailerId[];
  maxPages: number;
  maxCredits: number;
  availabilityGateEnabled: boolean;
}

export function normalizeZipcodes(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\s,;]+/)
        .map((zipcode) => zipcode.trim())
        .filter(Boolean),
    ),
  );
}

export function validateCollectionValues(
  values: CollectionFormValues,
): string | null {
  if (!values.keyword.trim()) return "Enter a search keyword.";
  if (values.zipcodes.length === 0)
    return "Enter at least one five-digit ZIP code.";
  if (values.zipcodes.some((zipcode) => !/^\d{5}$/.test(zipcode))) {
    return "Every ZIP code must contain exactly five digits.";
  }
  if (values.retailerIds.length === 0) return "Select at least one retailer.";
  if (values.maxPages < 1 || values.maxPages > 10) {
    return "Pages per retailer must be between 1 and 10.";
  }
  if (values.maxCredits < 0) return "The credit cap cannot be negative.";
  return null;
}

export function buildCollectionDefinition(
  values: CollectionFormValues,
): JsonObject {
  const retailers = RETAILER_OPTIONS.filter((retailer) =>
    values.retailerIds.includes(retailer.id),
  ).map((retailer) => ({
    retailer_id: retailer.id,
    adapter_id: retailer.adapterId,
    enabled: true,
    sort: retailer.sort,
    max_pages_override: values.maxPages,
    request_overrides: {},
  }));
  const gateEnabled =
    values.availabilityGateEnabled && values.retailerIds.includes("aldi_us");
  return {
    id: values.definitionId,
    name: values.name.trim(),
    version: "1.0.0",
    enabled: true,
    benchmark_retailer: values.retailerIds.includes("walmart_us")
      ? "walmart_us"
      : values.retailerIds[0],
    product_pack: {
      id: values.productPackId,
      version: values.productPackVersion,
    },
    query: {
      keyword: values.keyword.trim(),
      amazon_same_day_url_template:
        "https://www.amazon.com/s?k={{keyword}}&i=samedaystore",
      notes: "Created in the collection wizard.",
    },
    retailers,
    geography: {
      strategy: "custom_zips",
      benchmark_retailer: values.retailerIds.includes("walmart_us")
        ? "walmart_us"
        : values.retailerIds[0],
      country: "USA",
      states: [],
      zipcodes: values.zipcodes,
      location_ids: [],
      proximity_validation_miles: 10,
    },
    pagination: {
      max_pages: values.maxPages,
      stop_on_empty: true,
      stop_on_short_page: false,
    },
    availability_gate: gateEnabled
      ? {
          enabled: true,
          retailer_ids: ["aldi_us"],
          sample_size_per_retailer: 5,
          max_billable_404_rate: 0.5,
        }
      : null,
    schedule: {
      type: "manual",
      cron: null,
      timezone: "America/Chicago",
    },
    analysis: {
      comparison_profiles: [],
      enable_ai_fallback: false,
      enable_proximity_validation: true,
    },
    delivery: {
      web_report: true,
      excel: true,
      leadership_email: true,
      audit_package: true,
    },
    budget: {
      max_credits_per_run: values.maxCredits,
      block_if_estimate_exceeds_budget: true,
    },
  };
}
