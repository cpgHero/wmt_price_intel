/* Generated from the normative JSON Schema. Do not edit manually. */

export type Brand = {
  [k: string]: unknown;
} & {
  retailer_id: string;
  normalized_brand: string;
  display_brand: string;
  role: "private_label" | "regional" | "national" | "unclassified";
  status: "suggested" | "confirmed" | "rejected" | "unclassified";
  origin: "product_pack" | "deterministic" | "user";
  reason?: string | null;
  canonical_brand_id: string | null;
  canonical_brand_name: string | null;
  candidate_status: "resolved" | "governed" | "candidate" | "ambiguous" | "none";
  /**
   * @maxItems 3
   */
  candidate_matches: [] | [Candidate] | [Candidate, Candidate] | [Candidate, Candidate, Candidate];
  /**
   * Products with positive-price Search presence when distribution_evidence is positive_price_store_search_result; otherwise a discovery or identity count with no distribution claim.
   */
  observed_products: number;
  /**
   * Deprecated display alias for distribution_store_count. It is never an inventory or in-stock count.
   */
  observed_locations: number;
  /**
   * ZIPs with governed positive-price Search presence; not a store count.
   */
  observed_zipcodes: number;
  /**
   * Distinct store IDs where a brand product appeared in a store-level Search result with price greater than zero.
   */
  distribution_store_count: number;
  /**
   * Distinct service-area Search presences, kept separate from store distribution.
   */
  service_area_presence_count: number;
  /**
   * Share of the retailer's governed positive-price Search stores carrying the brand; not an inventory claim.
   */
  location_share: number;
  distribution_tier: "unknown" | "single_location" | "concentrated" | "multi_market" | "broad";
  distribution_evidence: "positive_price_store_search_result" | "search_brand_field" | "pdp_identity_only";
  product_examples: {
    product_id: string;
    name: string;
    image_url?: string | null;
  }[];
};

export interface RetailCompetitiveIntelligenceBrandWorkbench {
  schema_version: "1.1.0";
  analysis_id: string;
  product_pack_id: string;
  product_pack_version: string;
  revision_id?: string | null;
  revision: number;
  current_publication_revision_id?: string | null;
  future_application?: null | {
    revision_id: string;
    revision: number;
  };
  retailers: {
    id: string;
    name: string;
  }[];
  brands: Brand[];
  summary: {
    suggested: number;
    confirmed: number;
    rejected: number;
    unclassified: number;
    candidate_matches: number;
    ambiguous_matches: number;
  };
}
export interface Candidate {
  canonical_brand_id: string;
  canonical_brand_name: string;
  role: "private_label" | "regional" | "national" | "unclassified";
  strict_private_label: boolean;
  retailer_scope: string;
  confidence_score: number;
  rationale: "quarantined_alias_conflict" | "same_core_name" | "name_prefix" | "token_overlap" | "spelling_similarity";
  brand_bucket: string;
  brand_class: string;
  primary_category: string | null;
  core_region: string | null;
}
