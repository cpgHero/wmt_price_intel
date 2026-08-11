/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceCollectionScopeEstimate {
  id: string;
  definition_id: string;
  resolution_id: string;
  configuration_checksum: string;
  geography_checksum: string;
  retailers: {
    retailer_id: string;
    location_units: number;
    credits_per_page: number;
    max_pages: number;
    estimated_pages: number;
    estimated_credits: number;
  }[];
  estimated_total_pages: number;
  estimated_total_credits: number;
  expires_at: string;
  created_at: string;
}
