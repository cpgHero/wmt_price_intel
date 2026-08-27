/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceCompetitiveDecisionQuality {
  schema_version: "1.1.0-competitive-decision-quality-audit";
  status: "passed" | "failed";
  analysis_id: string;
  document_count: number;
  profiles: string[];
  radii: (1 | 3 | 5)[];
  retailer_count: number;
  expected_context_count: number;
  context_count: number;
  context_state_counts: {
    scored: number;
    local_evidence_limited: number;
    no_selected_basis_relationship: number;
  };
  contexts: Context[];
  error_count: number;
  warning_count: number;
  findings: Finding[];
}
export interface Context {
  profile_id: string;
  radius_miles: 1 | 3 | 5;
  competitor_id: string;
  competitor: string;
  evidence_state: "scored" | "local_evidence_limited" | "no_selected_basis_relationship";
  comparison_metric: string | null;
  comparison_unit: string | null;
  catalog_products: number;
  in_scope_catalog_products: number;
  observed_catalog_products: number;
  certified_identity_products: number;
  selected_price_basis_products: number;
  locally_scored_products: number;
  relationships: number;
  benchmark_product_locations: number;
  scored_product_locations: number;
  coverage_rate: number | null;
}
export interface Finding {
  severity: "error" | "warning";
  code: string;
  message: string;
  context: {
    [k: string]: unknown;
  };
}
