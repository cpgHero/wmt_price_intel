/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceCollectionDefinition {
  id: string;
  name: string;
  version: string;
  enabled?: boolean;
  benchmark_retailer: string;
  product_pack: {
    id: string;
    version: string;
  };
  query: {
    keyword: string;
    amazon_same_day_url_template?: string | null;
    notes?: string | null;
  };
  /**
   * @minItems 1
   */
  retailers: [
    {
      retailer_id: string;
      adapter_id: string;
      enabled: boolean;
      sort?: string | null;
      max_pages_override?: number | null;
      request_overrides?: {
        [k: string]: unknown;
      };
    },
    ...{
      retailer_id: string;
      adapter_id: string;
      enabled: boolean;
      sort?: string | null;
      max_pages_override?: number | null;
      request_overrides?: {
        [k: string]: unknown;
      };
    }[]
  ];
  geography: {
    strategy:
      | "all_retailer_locations"
      | "benchmark_retailer_zips"
      | "union_retailer_zips"
      | "custom_zips"
      | "custom_locations"
      | "states";
    benchmark_retailer?: string | null;
    country?: string;
    states?: string[];
    zipcodes?: string[];
    location_ids?: string[];
    proximity_validation_miles?: number | null;
  };
  pagination: {
    max_pages: number;
    stop_on_empty: boolean;
    stop_on_short_page?: boolean;
  };
  schedule?: {
    [k: string]: unknown;
  } & ({
    type: "manual" | "cron";
    cron?: string | null;
    timezone: string;
  } | null);
  analysis?: {
    comparison_profiles?: string[];
    enable_ai_fallback?: boolean;
    enable_proximity_validation?: boolean;
  };
  delivery: {
    web_report: boolean;
    excel: boolean;
    leadership_email: boolean;
    audit_package?: boolean;
    email_recipients?: string[];
  };
  budget?: {
    max_credits_per_run?: number | null;
    block_if_estimate_exceeds_budget?: boolean;
    max_credits_per_day?: number | null;
    max_credits_per_month?: number | null;
  } | null;
}
