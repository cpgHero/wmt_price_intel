/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductMatchReview {
  analysis_id: string;
  product_pack_id: string;
  product_pack_version: string;
  revision_id?: string | null;
  revision: number;
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
  [k: string]: unknown;
}
export interface Connection {
  id?: string | null;
  competitor_retailer_id: string;
  source_profile_id: string;
  /**
   * @minItems 1
   */
  eligible_profile_ids: [string, ...string[]];
  benchmark_product_id: string;
  competitor_product_id: string;
  status: "suggested" | "confirmed" | "rejected";
  origin: "automatic" | "user";
  reason?: string | null;
  matches?: number | null;
  geographies?: number | null;
  median_gap?: number | null;
  match_basis: "exact_package" | "normalized_unit" | "multiple" | "user_defined";
  profile_evidence: ProfileEvidence[];
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
