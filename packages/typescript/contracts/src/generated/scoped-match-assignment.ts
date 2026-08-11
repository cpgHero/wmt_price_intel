/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceScopedMatchAssignment {
  schema_version: "1.0.0";
  assignment_id: string;
  analysis_id: string;
  match_revision_id?: string | null;
  brand_revision_id?: string | null;
  relationship_id?: string | null;
  competitor_retailer_id: string;
  profile_id: string;
  comparison_family_key: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  benchmark_location_scope_key: string;
  competitor_location_scope_key?: string | null;
  status: "active" | "scope_conflict" | "unavailable" | "unmatched" | "alternative";
  relationship_role: "primary" | "alternative";
  resolution_reason?: string | null;
  benchmark_offer_id?: string | null;
  competitor_offer_id?: string | null;
  benchmark_value?: number | null;
  competitor_value?: number | null;
  comparison_metric?: string | null;
  winner?: "benchmark_lower" | "competitor_lower" | "parity" | null;
  source_authority: "search";
}
