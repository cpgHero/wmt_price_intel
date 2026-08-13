/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceBrandClassificationDecision {
  expected_revision: number;
  retailer_id: string;
  normalized_brand: string;
  role: "private_label" | "regional" | "national" | "unclassified";
  decision: "confirmed" | "rejected" | "reset";
  canonical_brand_id?: string | null;
  reason?: string | null;
}
