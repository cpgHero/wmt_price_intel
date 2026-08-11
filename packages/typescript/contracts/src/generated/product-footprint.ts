/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductFootprint {
  schema_version: "1.0.0";
  analysis_id: string;
  retailer_id: string;
  product_id: string;
  source_authority: "search";
  locations: Location[];
  checksum: string;
}
export interface Location {
  scope_key: string;
  store_number?: string | null;
  zipcode: string;
  state?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  observations: number;
  lowest_positive_price?: number | null;
}
