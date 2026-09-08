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
   * Verified-available products only when distribution_evidence is verified_local_search_availability; otherwise a discovery or identity count that must remain explicitly unverified. Zero is authoritative when corrected verified-local counters prove no available products.
   */
  observed_products: number;
  /**
   * Verified locations only when distribution_evidence is verified_local_search_availability; otherwise discovery or identity reach that must remain unverified.
   */
  observed_locations: number;
  /**
   * Verified ZIPs only when distribution_evidence is verified_local_search_availability; otherwise discovery or identity reach that must remain unverified.
   */
  observed_zipcodes: number;
  /**
   * A verified-availability footprint only when distribution_evidence is verified_local_search_availability.
   */
  location_share: number;
  distribution_tier: "unknown" | "single_location" | "concentrated" | "multi_market" | "broad";
  distribution_evidence:
    | "verified_local_search_availability"
    | "search_brand_field"
    | "pdp_identity_joined_to_matched_search"
    | "pdp_identity_only";
  product_examples: {
    product_id: string;
    name: string;
    image_url?: string | null;
  }[];
};

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
