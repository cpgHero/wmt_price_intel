/* Generated from the normative JSON Schema. Do not edit manually. */

export type EvidenceRate = EvidenceRate1 & {
  status: "observed" | "unavailable";
  known_observations: number;
  in_stock_observations?: number;
  promotion_observations?: number;
  sponsorship_observations?: number;
  rate: number | null;
  definition: string;
};
export type EvidenceRate1 = {
  [k: string]: unknown;
};

export interface RetailCompetitiveIntelligencePriceMonitoringView {
  schema_version: "1.3.0";
  analysis_id: string;
  generated_at: string;
  product_pack: IdNameVersion;
  retailer: {
    id: string;
    name: string;
    location_dimension: "store" | "service_area";
  };
  source: {
    authority: "Search";
    location_authority: "Retailer location master";
    grain: "retailer product x retailer location x latest observation in run";
    observed_start: string | null;
    observed_end: string | null;
    source_rows: number;
    classified_rows: number;
    observation_schema_version: "1.1.0";
    observation_population_checksum: string;
    artifact_checksums: string[];
  };
  filters: {
    retailer_id: string;
    brand_type: "all" | "private_label" | "regional" | "national" | "unclassified";
    state: string | null;
    city: string | null;
    zipcode: string | null;
    product_id: string | null;
  };
  filter_options: {
    retailers: IdName[];
    brand_types: ValueLabelCount[];
    states: ValueLabelCount[];
    cities: ValueLabelCount[];
    zipcodes: ValueLabelCount[];
    products: ProductOption[];
  };
  summary: {
    observed_locations: number;
    expected_locations: number;
    coverage_rate: number | null;
    observed_products: number;
    eligible_observations: number;
    usable_price_rate: number;
    price_consistency_rate: number | null;
  };
  presence: {
    status: "observed_only";
    observed_locations: number;
    eligible_locations: number;
    observed_presence_rate: number | null;
    not_observed_locations: number;
    confirmed_gap_locations: number;
    definition: string;
  };
  distribution_gaps: {
    status: "search_non_observation";
    definition: string;
    location_display: {
      returned: number;
      total: number;
      sampled: boolean;
      missing_location_details: number;
    };
    geographies: GapGeography[];
    locations: GapLocation[];
  };
  price_distribution: PriceStats;
  price_histogram: PriceBin[];
  brand_portfolio: {
    brand_type: "private_label" | "regional" | "national" | "unclassified";
    products: number;
    locations: number;
    observations: number;
    median_price: number | null;
  }[];
  geographies: Geography[];
  locations: LocationSummary[];
  location_display: {
    returned: number;
    total: number;
    sampled: boolean;
  };
  products: ProductSummary[];
  exceptions: StoreException[];
  quality: {
    status: "ready" | "warning" | "blocked";
    checks: {
      id: string;
      label: string;
      count: number;
      rate: number;
      severity: "info" | "warning" | "blocker";
      definition: string;
    }[];
  };
  movement: {
    status: "available" | "unavailable";
    reason: string;
    continuous_pairs?: number;
    changed_pairs?: number;
    changed_rate?: number | null;
  };
}
export interface IdNameVersion {
  id: string;
  name: string;
  version: string;
}
export interface IdName {
  id: string;
  name: string;
}
export interface ValueLabelCount {
  value: string;
  label: string;
  count: number;
}
export interface ProductOption {
  value: string;
  label: string;
  count: number;
  brand: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  image_url: string | null;
}
export interface GapGeography {
  level: "state" | "city" | "zipcode";
  key: string;
  label: string;
  state: string | null;
  city: string | null;
  zipcode: string | null;
  eligible_locations: number;
  observed_locations: number;
  not_observed_locations: number;
  observed_rate: number | null;
}
export interface GapLocation {
  scope_key: string;
  kind: "store" | "service_area";
  store_number: string | null;
  store_name: string | null;
  zipcode: string | null;
  city: string | null;
  state: string | null;
  country: string;
  latitude: number | null;
  longitude: number | null;
}
export interface PriceStats {
  minimum: number | null;
  q1: number | null;
  observation_median: number | null;
  product_equal_weighted_median: number | null;
  q3: number | null;
  maximum: number | null;
  range: number | null;
  modal_price: number | null;
  modal_share: number | null;
  observation_count: number;
}
export interface PriceBin {
  lower: number;
  upper: number;
  count: number;
  share: number;
}
export interface Geography {
  level: "country" | "state" | "city" | "zipcode";
  key: string;
  label: string;
  state: string | null;
  city: string | null;
  zipcode?: string | null;
  locations: number;
  products: number;
  observations: number;
  latitude?: number | null;
  longitude?: number | null;
  price_stats: PriceStats;
}
export interface LocationSummary {
  scope_key: string;
  kind: "store" | "service_area";
  store_number: string | null;
  store_name: string | null;
  zipcode: string | null;
  city: string | null;
  state: string | null;
  country: string;
  latitude: number | null;
  longitude: number | null;
  products: number;
  observations: number;
  minimum_price: number | null;
  median_price: number | null;
  maximum_price: number | null;
  sponsorship_status: "sponsored" | "organic" | "mixed" | "unknown";
}
export interface ProductSummary {
  product_id: string;
  name: string;
  brand: string | null;
  seller: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  brand_origin: "user" | "product_pack" | "retailer_pack" | "search" | "pdp" | "unresolved";
  brand_status: "confirmed" | "suggested" | "unclassified" | "rejected";
  image_url: string | null;
  url: string | null;
  locations: number;
  states: number;
  cities: number;
  price_stats: PriceStats;
  unit_price: UnitPriceSummary;
  consistency_rate: number | null;
  availability: EvidenceRate;
  promotion: EvidenceRate;
  sponsorship: EvidenceRate;
  presence: ProductPresence;
  price_histogram: PriceBin[];
  sample_locations: ProductLocation[];
}
export interface UnitPriceSummary {
  status: "observed" | "unavailable";
  metric: string | null;
  label: string | null;
  unit: string | null;
  price_stats: PriceStats;
  known_observations: number;
  total_observations: number;
  coverage_rate: number | null;
  definition: string;
}
export interface ProductPresence {
  observed_locations: number;
  eligible_locations: number;
  not_observed_locations: number;
  observed_rate: number | null;
  not_observed_rate: number | null;
  definition: string;
}
export interface ProductLocation {
  scope_key: string;
  store_number: string | null;
  store_name: string | null;
  zipcode: string | null;
  city: string | null;
  state: string | null;
  price: number;
  is_sponsored: boolean | null;
  observed_at: string | null;
}
export interface StoreException {
  id: string;
  type: "price_outlier";
  severity: "high" | "review";
  scope_key: string;
  store_number: string | null;
  store_name: string | null;
  zipcode: string | null;
  city: string | null;
  state: string | null;
  price: number;
  reference_price: number;
  difference: number;
  observed_at: string | null;
  reason: string;
}
