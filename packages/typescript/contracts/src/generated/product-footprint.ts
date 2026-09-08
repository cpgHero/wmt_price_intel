/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductFootprint {
  schema_version: "1.1.0";
  analysis_id: string;
  retailer_id: string;
  product_id: string;
  source_authority: "store_level_search";
  distribution_contract: DistributionContract;
  store_count: number;
  locations: Location[];
  checksum: string;
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
export interface Location {
  scope_key: string;
  store_number?: string;
  zipcode: string | null;
  state?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  observations: number;
  lowest_positive_price?: number | null;
}
