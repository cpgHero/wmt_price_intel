/* Generated from the normative JSON Schema. Do not edit manually. */

export type RetailCompetitiveIntelligencePriceObservation = {
  [k: string]: unknown;
} & {
  schema_version: "1.3.0";
  observation_id: string;
  analysis_id: string;
  product_pack_id: string;
  product_pack_version: string;
  retailer_id: string;
  retailer_name: string;
  retailer_product_id: string;
  product_name: string;
  brand: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  brand_origin: "user" | "retailer_pack" | "search" | "pdp" | "unresolved";
  brand_status: string;
  image_url: string | null;
  product_url: string | null;
  identity_authority: "search" | "pdp";
  location: {
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
  };
  price: number;
  regular_price: number | null;
  discounted_price: number | null;
  currency: string;
  search_observed: true;
  is_sponsored: boolean | null;
  distribution_store_id: string | null;
  distribution_contract: DistributionContract;
  price_metrics: {
    [k: string]: number | null;
  };
  observed_at: string | null;
  source_authority: "search_location_observation";
  location_authority: "retailer_location_master";
  eligible: true;
  /**
   * @maxItems 0
   */
  exclusion_reasons: [];
};

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
