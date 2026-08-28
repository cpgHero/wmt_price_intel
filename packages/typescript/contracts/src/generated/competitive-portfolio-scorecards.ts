/* Generated from the normative JSON Schema. Do not edit manually. */

export type Scorecard = Summary & {
  competitor_id: string;
  competitor: string;
  benchmark_products: number;
  competitor_products: number;
  relationships: number;
  evidence_funnel?: EvidenceFunnel;
  products: ProductSummary[];
  product_relationships?: RelationshipSummary[];
  [k: string]: unknown;
};
export type ProductSummary = Summary & {
  product_id: string;
  product_name: string;
  image_url: string | null;
  relationships: number;
  [k: string]: unknown;
};
export type RelationshipSummary = Summary & {
  relationship_id: string;
  competitor_id: string;
  competitor_name: string;
  benchmark_product_id: string;
  benchmark_product_name: string;
  benchmark_image_url: string | null;
  competitor_product_id: string;
  competitor_product_name: string;
  competitor_brand: string | null;
  competitor_brand_type: "private_label" | "regional" | "national" | "unclassified";
  competitor_image_url: string | null;
  profile_id: string;
  profile_label: string;
  comparison_metric: string;
  comparison_unit: string;
  scope_mode: string;
  scoped_benchmark_locations: number;
  [k: string]: unknown;
};
export type Cohort = Summary & {
  id: string;
  competitor_id: string;
  competitor: string;
  profile_id: string;
  segment_id: string;
  segment: string;
  attributes: {
    [k: string]: unknown;
  };
  comparison_metric?: string;
  comparison_unit?: string;
  median_grain?: "scored benchmark product-location observations";
  relationships: number;
  benchmark_products: number;
  competitor_products: number;
  benchmark_median: number | null;
  competitor_median: number | null;
  paired_median_gap: number | null;
  dominant_outcome: "benchmark_lower" | "competitor_lower" | "parity" | "unavailable";
  products: ProductSummary[];
  product_relationships?: RelationshipSummary[];
  [k: string]: unknown;
};
export type AssortmentScorecard = Summary & {
  competitor_id: string;
  competitor: string;
  profile_id: string;
  relationships: number;
  matched_benchmark_products: number;
  matched_competitor_products: number;
  benchmark_only_products: number;
  competitor_whitespace_products: number;
  benchmark_match_coverage: number | null;
  competitor_match_coverage: number | null;
  profiles: {
    [k: string]: unknown;
  }[];
  top_benchmark_only: {
    [k: string]: unknown;
  }[];
  top_competitor_whitespace: {
    [k: string]: unknown;
  }[];
  products: ProductSummary[];
  [k: string]: unknown;
};

export interface RetailCompetitiveIntelligenceCompetitivePortfolioScorecards {
  schema_version: "1.1.0" | "1.2.0" | "1.3.0" | "1.4.0" | "1.5.0" | "1.6.0";
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
  cohorts: Cohort[];
  assortment_scorecards: AssortmentScorecard[];
}
export interface IdName {
  id: string;
  name: string;
}
export interface Summary {
  benchmark_product_locations: number;
  scored_product_locations: number;
  coverage_rate: number | null;
  benchmark_observed_locations?: number;
  benchmark_scored_locations?: number;
  benchmark_unscored_locations?: number;
  location_coverage_rate?: number | null;
  competitor_contributing_locations?: number;
  competitor_contributing_stores?: number;
  competitor_contributing_service_areas?: number;
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
export interface EvidenceFunnel {
  catalog_products: number;
  in_scope_catalog_products: number;
  observed_catalog_products: number;
  certified_identity_products: number;
  selected_price_basis_products: number;
  locally_scored_products: number;
  scored_product_locations: number;
  status_counts: {
    benchmark_not_observed: number;
    no_certified_relationship: number;
    no_selected_price_basis: number;
    no_local_competitor_evidence: number;
    scored: number;
    governed_out_of_scope: number;
  };
}
