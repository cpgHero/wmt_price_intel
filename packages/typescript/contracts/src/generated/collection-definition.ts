/* Generated from the normative JSON Schema. Do not edit manually. */

export type RetailCompetitiveIntelligenceCollectionDefinition = {
  [k: string]: unknown;
} & {
  purpose?: "analysis" | "study_discovery";
  id: string;
  name: string;
  version: string;
  enabled?: boolean;
  benchmark_retailer: string;
  product_pack?: {
    id: string;
    version: string;
  } | null;
  study_discovery?: {
    study_id: string;
    query_plan_checksum: string;
  } | null;
  query: {
    keyword: string;
    /**
     * @minItems 1
     * @maxItems 500
     */
    keywords?: [string, ...string[]];
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
    [k: string]: unknown;
  };
  pagination: {
    max_pages: number;
    stop_on_empty: boolean;
    stop_on_short_page?: boolean;
  };
  availability_gate?: {
    enabled: boolean;
    retailer_ids: string[];
    sample_size_per_retailer: number;
    max_billable_404_rate: number;
  } | null;
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
  } | null;
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
  product_detail_enrichment?: {
    policy: "disabled" | "new_or_changed" | "refresh_after_7_days" | "refresh_after_30_days" | "manual";
    approval: "separate_after_search";
    analysis_admitted_products_only?: true;
    price_variation_samples?: boolean;
  } | null;
};
