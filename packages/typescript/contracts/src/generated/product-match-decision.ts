/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductMatchDecision {
  expected_revision: number;
  competitor_retailer_id: string;
  profile_id: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  decision: "confirmed" | "rejected" | "reset";
  scope?: RetailCompetitiveIntelligenceProductMatchScope;
  replace_conflicts?: boolean;
  reason?: string | null;
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
