/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceCompetitiveProductCoverage {
  schema_version: "1.0.0";
  analysis_id: string;
  benchmark_retailer: IdName;
  competitor: IdName;
  profile_id: string;
  radius_miles: 1 | 3 | 5;
  evidence_funnel: EvidenceFunnel;
  products: Product[];
}
export interface IdName {
  id: string;
  name: string;
}
export interface EvidenceFunnel {
  catalog_products: number;
  in_scope_catalog_products: number;
  observed_catalog_products: number;
  certified_identity_products: number;
  selected_price_basis_products: number;
  locally_scored_products: number;
  scored_product_locations: number;
  status_counts: {
    benchmark_not_observed: number;
    no_certified_relationship: number;
    no_selected_price_basis: number;
    no_local_competitor_evidence: number;
    scored: number;
    governed_out_of_scope: number;
  };
}
export interface Product {
  product_id: string;
  product_name: string;
  image_url: string | null;
  observed_locations: number;
  status:
    | "benchmark_not_observed"
    | "no_certified_relationship"
    | "no_selected_price_basis"
    | "no_local_competitor_evidence"
    | "scored"
    | "governed_out_of_scope";
  certified_relationships: number;
  selected_price_basis_relationships: number;
  selected_competitor_products: number;
  scored_product_locations: number;
}
