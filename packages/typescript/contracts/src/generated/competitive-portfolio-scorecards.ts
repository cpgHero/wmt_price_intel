/* Generated from the normative JSON Schema. Do not edit manually. */

export type Scorecard = Summary & {
  competitor_id: string;
  competitor: string;
  benchmark_products: number;
  competitor_products: number;
  relationships: number;
  products: ProductSummary[];
  [k: string]: unknown;
};
export type ProductSummary = Summary & {
  product_id: string;
  product_name: string;
  image_url: string | null;
  relationships: number;
  [k: string]: unknown;
};

export interface RetailCompetitiveIntelligenceCompetitivePortfolioScorecards {
  schema_version: "1.0.0";
  analysis_id: string;
  generated_at: string;
  benchmark_retailer: IdName;
  filters: {
    competitor_id: string;
    profile_id: string;
    radius_miles: 1 | 3 | 5;
    state: string | null;
    city: string | null;
  };
  policy: {
    physical_store_rule: "within selected radius";
    service_area_rule: "same delivery ZIP";
    grain: string;
  };
  scorecards: Scorecard[];
}
export interface IdName {
  id: string;
  name: string;
}
export interface Summary {
  benchmark_product_locations: number;
  scored_product_locations: number;
  coverage_rate: number | null;
  leader_product_locations: number;
  tied_product_locations: number;
  at_risk_product_locations: number;
  losing_product_locations: number;
  unscored_product_locations: number;
  leader_rate: number | null;
  benchmark_lower_rate: number | null;
  competitor_lower_rate: number | null;
  parity_rate: number | null;
  average_gap: number | null;
  [k: string]: unknown;
}
