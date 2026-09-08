/* Generated from the normative JSON Schema. Do not edit manually. */

export type MapPoint = {
  [k: string]: unknown;
} & {
  scope_key: string;
  status: "observed" | "not_observed";
  search_observed: boolean;
  is_sponsored: boolean | null;
  distribution_store_id: string | null;
  kind: "store" | "service_area";
  store_number: string | null;
  store_name: string | null;
  zipcode: string | null;
  city: string | null;
  state: string | null;
  country: string;
  latitude: number;
  longitude: number;
  price: number | null;
  difference_from_reference: number | null;
};

export interface RetailCompetitiveIntelligencePriceMonitoringMap {
  schema_version: "1.3.0";
  analysis_id: string;
  retailer: IdName;
  product: IdName;
  distribution_contract: DistributionContract;
  filters: {
    state: string | null;
    city: string | null;
    zipcode: string | null;
    detail: "summary" | "full";
  };
  source: {
    authority: "Search";
    location_authority: "Retailer location master";
    definition: string;
  };
  reference_price: number | null;
  display: {
    /**
     * All positive-price Search locations; store and service-area components are reported separately.
     */
    observed_locations: number;
    search_observed_locations: number;
    distribution_store_count: number;
    service_area_presence_count: number;
    observed_points: number;
    observed_missing_coordinates: number;
    observed_sampled: boolean;
    below_reference_locations: number;
    at_reference_locations: number;
    above_reference_locations: number;
    not_observed_locations: number;
    not_observed_points: number;
    not_observed_missing_coordinates: number;
    not_observed_sampled: boolean;
  };
  points: MapPoint[];
}
export interface IdName {
  id: string;
  name: string;
}
export interface DistributionContract {
  version: "1.0.0";
  basis: "positive_price_store_search_result";
  grain: "retailer_product_id_x_store_id";
  deduplication: "distinct_store_id_per_product";
  price_rule: "price_gt_zero";
  inventory_claim: false;
  stock_status_used: false;
  sponsorship_used: false;
}
