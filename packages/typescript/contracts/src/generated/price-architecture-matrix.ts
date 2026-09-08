/* Generated from the normative JSON Schema. Do not edit manually. */

export type Retailer = {
  [k: string]: unknown;
} & {
  [k: string]: unknown;
} & {
  id: string;
  name: string;
  status: "available" | "unavailable";
  location_dimension: "store" | "service_area";
  sku_count: number;
  eligible_locations: number;
  /**
   * Store distribution plus separate service-area Search presence.
   */
  observed_locations: number;
  distribution_store_count: number;
  service_area_presence_count: number;
  /**
   * Distinct positive-price Search locations in the active filter scope.
   */
  search_observed_locations: number;
  /**
   * Distinct positive-price Search SKUs in the active filter scope.
   */
  search_observed_skus: number;
  verified_first_party_skus: number;
  seller_unverified_skus: number;
  seller_not_governed_skus: number;
  population_checksum: string | null;
  reason: string | null;
} & {
  id: string;
  name: string;
  status: "available" | "unavailable";
  location_dimension: "store" | "service_area";
  sku_count: number;
  eligible_locations: number;
  /**
   * Store distribution plus separate service-area Search presence.
   */
  observed_locations: number;
  distribution_store_count: number;
  service_area_presence_count: number;
  /**
   * Distinct positive-price Search locations in the active filter scope.
   */
  search_observed_locations: number;
  /**
   * Distinct positive-price Search SKUs in the active filter scope.
   */
  search_observed_skus: number;
  verified_first_party_skus: number;
  seller_unverified_skus: number;
  seller_not_governed_skus: number;
  population_checksum: string | null;
  reason: string | null;
};

export interface RetailCompetitiveIntelligencePriceArchitectureMatrix {
  schema_version: "1.3.0";
  analysis_id: string;
  generated_at: string;
  product_pack: IdNameVersion;
  source: {
    authority: "Search";
    price_grain: "retailer product x median positive Search-listed package price across observed Search locations";
    distribution_rule: "distinct store IDs where the product appears in store-level Search with price greater than zero; not an in-stock indicator";
    assignment_rule: "price only; no product-match relationship is used";
    anchor_rule: string;
  };
  distribution_contract: DistributionContract;
  filters: {
    anchor_retailer_id: string;
    mode: "benchmark_anchored" | "fixed_range";
    fixed_increment: 0.5 | 1;
    brand_type: "all" | "private_label" | "regional" | "national" | "unclassified";
    brand: string | null;
    state: string | null;
    city: string | null;
    zipcode: string | null;
  };
  summary: {
    anchor_price_points: number;
    rung_count: number;
    anchor_skus: number;
    competitor_skus: number;
    most_crowded_rung_id: string;
    whitespace_rung_count: number;
  };
  brand_options: BrandOption[];
  /**
   * @minItems 1
   */
  retailers: [Retailer, ...Retailer[]];
  /**
   * @minItems 1
   */
  rungs: [Rung, ...Rung[]];
}
export interface IdNameVersion {
  id: string;
  name: string;
  version: string;
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
export interface BrandOption {
  name: string;
  /**
   * @minItems 1
   */
  retailer_ids: [string, ...string[]];
  product_count: number;
}
export interface Rung {
  id: string;
  rank: number;
  label: string;
  anchor_price: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  anchor_products: Product[];
  competitor_sku_count: number;
  /**
   * @minItems 1
   */
  cells: [Cell, ...Cell[]];
}
export interface Product {
  product_id: string;
  name: string;
  brand: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  seller: string | null;
  seller_status: "verified_first_party" | "seller_unverified" | "not_governed";
  image_url: string | null;
  url: string | null;
  median_price: number;
  minimum_price: number;
  maximum_price: number;
  observed_locations: number;
  distribution_store_count: number;
  service_area_presence_count: number;
  search_observed_locations: number;
}
export interface Cell {
  retailer_id: string;
  sku_count: number;
  assortment_share: number | null;
  store_coverage: number | null;
  average_price: number | null;
  price_density: number | null;
  products: Product[];
}
