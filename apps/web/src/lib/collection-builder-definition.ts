import type {
  CollectionBuilderOptions,
  CollectionGeographyResolution,
  JsonObject,
} from "./api";

export interface BuilderDefinitionValues {
  definitionId: string;
  name: string;
  productPackId: string;
  productPackVersion: string;
  keyword: string;
  primaryRetailerId: string;
  competitorRetailerIds: string[];
  maxPagesByRetailer: Record<string, number>;
  maxCredits: number;
  availabilityGateEnabled: boolean;
  scheduleType: "manual" | "cron";
  cronExpression: string;
  timezone: string;
  delivery: {
    webReport: boolean;
    excel: boolean;
    leadershipEmail: boolean;
    auditPackage: boolean;
  };
  productDetailPolicy:
    | "disabled"
    | "new_or_changed"
    | "refresh_after_7_days"
    | "refresh_after_30_days"
    | "manual";
}

export function buildApprovedCollectionDefinition(
  values: BuilderDefinitionValues,
  options: CollectionBuilderOptions,
  resolution: CollectionGeographyResolution,
): JsonObject {
  const selectedIds = [
    values.primaryRetailerId,
    ...values.competitorRetailerIds,
  ];
  const retailers = selectedIds.map((retailerId) => {
    const retailer = options.retailers.find((item) => item.id === retailerId);
    if (!retailer) throw new Error(`Retailer ${retailerId} is unavailable.`);
    return {
      retailer_id: retailer.id,
      adapter_id: retailer.adapter_id,
      enabled: true,
      sort:
        retailer.id === "walmart_us"
          ? "Best Match"
          : retailer.id === "amazon_us_same_day"
            ? "Featured"
            : null,
      max_pages_override: retailer.supports_pagination
        ? (values.maxPagesByRetailer[retailer.id] ?? 1)
        : 1,
      request_overrides: {},
    };
  });
  const gatedRetailers = values.competitorRetailerIds.filter((retailerId) =>
    options.retailers.some(
      (retailer) =>
        retailer.id === retailerId &&
        retailer.location_dimension === "store_zip",
    ),
  );
  return {
    id: values.definitionId,
    name: values.name.trim(),
    version: "1.0.0",
    enabled: true,
    benchmark_retailer: values.primaryRetailerId,
    product_pack: {
      id: values.productPackId,
      version: values.productPackVersion,
    },
    query: {
      keyword: values.keyword.trim(),
      amazon_same_day_url_template:
        "https://www.amazon.com/s?k={{keyword}}&i=samedaystore",
      notes: "Created in the dynamic geography collection builder.",
    },
    retailers,
    geography: {
      strategy: "approved_resolution",
      benchmark_retailer: values.primaryRetailerId,
      country: String(resolution.request.country),
      states: [],
      zipcodes: [],
      location_ids: [],
      proximity_validation_miles:
        resolution.request.competitor_correspondence.mode === "radius"
          ? (resolution.request.competitor_correspondence.radius_miles ?? null)
          : null,
      resolution_id: resolution.id,
      resolution_checksum: resolution.checksum,
      refresh_policy: "frozen",
    },
    pagination: {
      max_pages: Math.max(...Object.values(values.maxPagesByRetailer), 1),
      stop_on_empty: true,
      stop_on_short_page: false,
    },
    availability_gate:
      values.availabilityGateEnabled && gatedRetailers.length > 0
        ? {
            enabled: true,
            retailer_ids: gatedRetailers,
            sample_size_per_retailer: 5,
            max_billable_404_rate: 0.5,
          }
        : null,
    schedule: {
      type: values.scheduleType,
      cron:
        values.scheduleType === "cron" ? values.cronExpression.trim() : null,
      timezone: values.timezone,
    },
    analysis: {
      comparison_profiles: [],
      enable_ai_fallback: true,
      enable_proximity_validation:
        resolution.request.competitor_correspondence.mode === "radius",
    },
    delivery: {
      web_report: values.delivery.webReport,
      excel: values.delivery.excel,
      leadership_email: values.delivery.leadershipEmail,
      audit_package: values.delivery.auditPackage,
      email_recipients: [],
    },
    budget: {
      max_credits_per_run: values.maxCredits,
      block_if_estimate_exceeds_budget: true,
    },
    product_detail_enrichment: {
      policy: values.productDetailPolicy,
      approval: "separate_after_search",
      analysis_admitted_products_only: true,
      price_variation_samples: true,
    },
  };
}

export function validateBuilderDefinition(
  values: BuilderDefinitionValues,
): string | null {
  if (values.name.trim().length < 3) return "Enter a collection name.";
  if (!values.keyword.trim()) return "Enter a search keyword.";
  if (!values.primaryRetailerId) return "Select a primary retailer.";
  if (values.competitorRetailerIds.length === 0) {
    return "Select at least one competitor retailer.";
  }
  if (
    values.competitorRetailerIds.some(
      (retailerId) => retailerId === values.primaryRetailerId,
    )
  ) {
    return "The primary retailer cannot also be a competitor.";
  }
  if (
    Object.values(values.maxPagesByRetailer).some(
      (pages) => !Number.isInteger(pages) || pages < 1 || pages > 10,
    )
  ) {
    return "Pages per location must be between 1 and 10.";
  }
  if (values.maxCredits < 0) return "The credit cap cannot be negative.";
  if (values.scheduleType === "cron" && !values.cronExpression.trim()) {
    return "Enter a cron expression for the scheduled collection.";
  }
  return null;
}
