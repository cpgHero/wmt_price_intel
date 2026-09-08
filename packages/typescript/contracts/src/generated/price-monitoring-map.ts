/* Generated from the normative JSON Schema. Do not edit manually. */

export type MapPoint = AvailabilityInvariant & {
  [k: string]: unknown;
} & {
  scope_key: string;
  status: "observed" | "not_observed";
  search_observed: boolean;
  in_stock: boolean | null;
  is_sponsored: boolean | null;
  availability_status: "verified_in_stock" | "explicitly_out_of_stock" | "unverified_sponsored" | "unverified";
  verified_local_availability: boolean;
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
export type AvailabilityInvariant =
  | {
      availability_status: "verified_in_stock";
      in_stock: true;
      is_sponsored: false;
      verified_local_availability: true;
      [k: string]: unknown;
    }
  | {
      availability_status: "explicitly_out_of_stock";
      in_stock: false;
      verified_local_availability: false;
      [k: string]: unknown;
    }
  | {
      availability_status: "unverified_sponsored";
      in_stock: true | null;
      is_sponsored: true;
      verified_local_availability: false;
      [k: string]: unknown;
    }
  | {
      availability_status: "unverified";
      in_stock: true | null;
      is_sponsored: false | null;
      verified_local_availability: false;
      [k: string]: unknown;
    };

export interface RetailCompetitiveIntelligencePriceMonitoringMap {
  schema_version: "1.2.0";
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
    /**
     * Legacy alias of search_observed_locations; never proof of carriage.
     */
    observed_locations: number;
    search_observed_locations: number;
    verified_available_locations: number;
    explicitly_out_of_stock_locations: number;
    /**
     * All Search-observed locations not verified in stock, including the explicitly_out_of_stock_locations subset.
     */
    unverified_locations: number;
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
