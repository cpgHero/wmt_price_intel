/* Generated from the normative JSON Schema. Do not edit manually. */

export type GeographySummary = Summary & {
  id: string;
  level: "state" | "city";
  label: string;
  [k: string]: unknown;
};

export interface RetailCompetitiveIntelligenceCompetitiveProductLeadership {
  schema_version: "1.0.0";
  analysis_id: string;
  generated_at: string;
  benchmark_retailer: IdName;
  benchmark_product: ProductOption;
  competitors: IdName[];
  filters: {
    competitor_id: string;
    profile_id: string;
    radius_miles: 1 | 3 | 5;
    state: string | null;
    city: string | null;
  };
  filter_options: {
    products: ProductOption[];
    competitors: IdName[];
    profiles: IdName[];
    radii_miles: never[];
    states: FilterOption[];
    cities: (FilterOption & {
      state: string;
      [k: string]: unknown;
    })[];
  };
  policy: {
    price_authority: "Search";
    identity_authority: string;
    location_authority: "Retailer location master";
    observation_definition: string;
    comparison_definition: string;
    comparison_metric: string;
    comparison_unit: string;
    parity_tolerance: number;
    at_risk_threshold: number;
    status_definition: {
      leader: string;
      tied: string;
      at_risk: string;
      losing: string;
      unscored: string;
    };
  };
  summary: Summary;
  state_summaries: GeographySummary[];
  city_summaries: GeographySummary[];
  competitor_summaries: (Summary & {
    competitor_id: string;
    competitor: string;
    [k: string]: unknown;
  })[];
  relationships: Relationship[];
  outcomes: Outcome[];
}
export interface IdName {
  id: string;
  name: string;
}
export interface ProductOption {
  id: string;
  name: string;
  image_url: string | null;
}
export interface FilterOption {
  value: string;
  label: string;
  count: number;
  [k: string]: unknown;
}
export interface Summary {
  benchmark_observed_stores: number;
  scored_stores: number;
  coverage_rate: number | null;
  leader_stores: number;
  tied_stores: number;
  at_risk_stores: number;
  losing_stores: number;
  unscored_stores: number;
  leader_rate: number | null;
  average_gap: number | null;
  average_losing_gap: number | null;
  maximum_losing_gap: number | null;
  [k: string]: unknown;
}
export interface Relationship {
  relationship_id: string;
  competitor_id: string;
  competitor_name: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  profile_id: string;
  profile_label: string;
  comparison_metric: string;
  comparison_unit: string;
  scope_mode: string;
  scoped_benchmark_locations: number;
}
export interface Outcome {
  id: string;
  status: "leader" | "tied" | "at_risk" | "losing" | "unscored";
  benchmark: Location;
  competitor: null | Location;
  relationship_id: string | null;
  distance_miles: number | null;
  competitor_minus_benchmark: number | null;
  comparison_value_reduction_to_lead: number | null;
}
export interface Location {
  retailer_id: string;
  retailer_name: string;
  product_id: string;
  product_name: string;
  image_url: string | null;
  scope_key: string;
  location_kind: "store" | "service_area";
  store_number: string | null;
  store_name: string | null;
  zipcode: string | null;
  city: string | null;
  state: string | null;
  country: string;
  latitude: number | null;
  longitude: number | null;
  package_price: number;
  comparison_value: number;
  observed_at: string | null;
}
