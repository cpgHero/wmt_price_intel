/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceStudyDiscovery {
  schema_version: "1.0.0";
  id: string;
  name: string;
  status:
    | "query_review"
    | "search_estimated"
    | "collecting"
    | "profiling"
    | "profile_ready"
    | "pdp_estimated"
    | "enriching"
    | "draft_ready"
    | "certifying"
    | "certified"
    | "published"
    | "failed"
    | "canceled";
  intake: {
    benchmark_retailer_id: string;
    /**
     * @minItems 1
     */
    competitor_retailer_ids: [string, ...string[]];
    category_context: string;
    known_inclusions?: string[];
    known_exclusions?: string[];
    geography_request: RetailCompetitiveIntelligenceCollectionGeographyRequest;
    max_search_pages: number;
    amazon_same_day_url_template?: string | null;
  };
  query_plan: {
    keyword: string;
    /**
     * @minItems 1
     */
    target_terms: [string, ...string[]];
    exclusion_terms: string[];
    /**
     * @maxItems 8
     */
    alternate_queries:
      | []
      | [string]
      | [string, string]
      | [string, string, string]
      | [string, string, string, string]
      | [string, string, string, string, string]
      | [string, string, string, string, string, string]
      | [string, string, string, string, string, string, string]
      | [string, string, string, string, string, string, string, string];
    source: "deterministic" | "ai_assisted" | "human_edited";
    rationale?: string | null;
    revision: number;
  };
  query_plan_checksum: string;
  approval_state: {
    search: Approval;
    pdp: Approval;
    ai: Approval;
  };
  links: {
    geography_resolution_id?: string | null;
    search_estimate_id?: string | null;
    collection_run_id?: string | null;
    pdp_run_id?: string | null;
    product_pack_draft_id?: string | null;
  };
  profile: {
    raw_observations: number;
    unique_products: number;
    provisionally_admitted_products: number;
    excluded_products: number;
    unknown_brands: number;
    price_variant_contexts: number;
    pdp_contexts: number;
    review_required_products: number;
  };
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}
export interface RetailCompetitiveIntelligenceCollectionGeographyRequest {
  primary_retailer_id: string;
  /**
   * @minItems 1
   */
  competitor_retailer_ids: [string, ...string[]];
  country: string;
  primary_selection: {
    mode: "all_locations" | "states" | "per_state" | "state_cities" | "custom_zips" | "custom_locations";
    states?: string[];
    cities?: {
      state: string;
      city: string;
    }[];
    locations_per_state?: number | null;
    zipcodes?: string[];
    location_ids?: string[];
  };
  competitor_correspondence: {
    mode: "same_zip" | "primary_states" | "radius";
    radius_miles?: 1 | 3 | 5 | null;
    maximum_locations_per_retailer_per_primary?: number | null;
  };
  exclusions?: {
    retailer_id: string;
    retailer_location_id?: string | null;
    scope_key: string;
  }[];
}
export interface Approval {
  status: "not_requested" | "estimated" | "approved" | "consumed";
  maximum_cost: number | null;
  unit?: "credits" | "usd" | null;
  approved_by?: string | null;
  approved_at?: string | null;
  approved_checksum?: string | null;
}
