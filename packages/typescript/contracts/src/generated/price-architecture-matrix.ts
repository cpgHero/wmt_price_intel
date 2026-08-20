/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligencePriceArchitectureMatrix {
  schema_version: "1.1.0";
  analysis_id: string;
  generated_at: string;
  product_pack: IdNameVersion;
  source: {
    authority: "Search";
    price_grain: "retailer product x median positive shelf price across observed locations";
    assignment_rule: "price only; no product-match relationship is used";
    anchor_rule: string;
  };
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
export interface BrandOption {
  name: string;
  /**
   * @minItems 1
   */
  retailer_ids: [string, ...string[]];
  product_count: number;
}
export interface Retailer {
  id: string;
  name: string;
  status: "available" | "unavailable";
  location_dimension: "store" | "service_area";
  sku_count: number;
  eligible_locations: number;
  observed_locations: number;
  verified_first_party_skus: number;
  seller_unverified_skus: number;
  seller_not_governed_skus: number;
  population_checksum: string | null;
  reason: string | null;
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
