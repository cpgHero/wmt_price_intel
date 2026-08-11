/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductMatchReview {
  analysis_id: string;
  product_pack_id: string;
  product_pack_version: string;
  revision_id?: string | null;
  revision: number;
  current_publication_revision_id?: string | null;
  staged_revision_id?: string | null;
  future_application: null | {
    revision_id: string;
    revision: number;
  };
  benchmark_retailer: Retailer;
  competitors: Retailer[];
  profiles: Profile[];
  products: Product[];
  connections: Connection[];
  summary: {
    suggested: number;
    confirmed: number;
    rejected: number;
    unmatched: number;
    ambiguous?: number;
  };
}
export interface Retailer {
  id: string;
  name: string;
}
export interface Profile {
  id: string;
  label: string;
  geography: string;
  comparison_metric: string;
  default_scope_mode?: "global" | "observed_benchmark_product_footprint" | "explicit_benchmark_locations";
  allow_scoped_reuse?: boolean;
}
export interface Product {
  retailer_id: string;
  product_id: string;
  canonical_product_id: string;
  name: string;
  brand?: string | null;
  image_url?: string | null;
  url?: string | null;
  price?: number | null;
  other_lens_participation?: {
    profile_id: string;
    status: "suggested" | "confirmed" | "rejected" | "ambiguous";
  }[];
  [k: string]: unknown;
}
export interface Connection {
  id?: string | null;
  relationship_id?: string | null;
  candidate_group_id?: string | null;
  competitor_retailer_id: string;
  source_profile_id: string;
  /**
   * @minItems 1
   */
  eligible_profile_ids: [string, ...string[]];
  benchmark_product_id: string;
  competitor_product_id: string;
  status: "suggested" | "confirmed" | "rejected" | "ambiguous";
  origin: "automatic" | "user";
  reason?: string | null;
  matches?: number | null;
  geographies?: number | null;
  median_gap?: number | null;
  qa_status?: "ready" | "review_required" | "suppressed";
  suppression_reasons?: string[];
  match_basis: "exact_package" | "normalized_unit" | "multiple" | "user_defined";
  profile_evidence: ProfileEvidence[];
  scope?: null | RetailCompetitiveIntelligenceProductMatchScope;
  scope_summary?: {
    eligible_locations?: number;
    active_locations?: number;
    conflict_locations?: number;
    unmatched_locations?: number;
  };
}
export interface ProfileEvidence {
  profile_id: string;
  profile_label: string;
  comparison_metric: string;
  match_basis: "exact_package" | "normalized_unit";
  matches?: number | null;
  geographies?: number | null;
  median_gap?: number | null;
  match_attributes: {
    [k: string]: unknown;
  };
  rationale: string;
}
export interface RetailCompetitiveIntelligenceProductMatchScope {
  mode: "global" | "observed_benchmark_product_footprint" | "explicit_benchmark_locations";
  relationship_role: "primary" | "alternative";
  comparison_family_key: string;
  definition: {
    source_analysis_id?: string | null;
    benchmark_location_scope_keys?: string[];
    excluded_benchmark_location_scope_keys?: string[];
    future_location_policy?: "review" | "follow_unique_product_footprint" | "explicit_only";
  };
  checksum: string;
  artifact_id?: string | null;
}
