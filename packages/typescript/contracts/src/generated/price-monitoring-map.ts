/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligencePriceMonitoringMap {
  schema_version: "1.0.0";
  analysis_id: string;
  retailer: IdName;
  product: IdName;
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
    observed_locations: number;
    observed_points: number;
    observed_missing_coordinates: number;
    observed_sampled: boolean;
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
export interface MapPoint {
  scope_key: string;
  status: "observed" | "not_observed";
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
}
