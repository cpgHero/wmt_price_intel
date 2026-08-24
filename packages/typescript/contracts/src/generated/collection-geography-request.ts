/* Generated from the normative JSON Schema. Do not edit manually. */

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
