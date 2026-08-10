/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductMatchDecision {
  expected_revision: number;
  competitor_retailer_id: string;
  profile_id: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  decision: "confirmed" | "rejected" | "reset";
  replace_conflicts?: boolean;
  reason?: string | null;
}
