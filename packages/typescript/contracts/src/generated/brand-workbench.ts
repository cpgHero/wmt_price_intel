/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceBrandWorkbench {
  schema_version: "1.0.0";
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
export interface Brand {
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
  observed_products: number;
  observed_locations: number;
  observed_zipcodes: number;
  location_share: number;
  distribution_tier: "unknown" | "single_location" | "concentrated" | "multi_market" | "broad";
  distribution_evidence: "search_brand_field" | "pdp_identity_joined_to_matched_search" | "pdp_identity_only";
  product_examples: {
    product_id: string;
    name: string;
    image_url?: string | null;
  }[];
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
