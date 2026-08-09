/* Generated from the normative JSON Schema. Do not edit manually. */

export type Topic =
  | "data_scope"
  | "footprint"
  | "exact_price"
  | "normalized_price"
  | "segment_drivers"
  | "segment_reversals"
  | "geography"
  | "fulfillment"
  | "brand_assortment"
  | "actions"
  | "caveats";
/**
 * @minItems 1
 */
export type Refs = [string, ...string[]];

export interface RetailCompetitiveIntelligenceAnalysisBrief {
  schema_version: "1.0.0";
  analysis_id: string;
  analysis_result_checksum_sha256: string;
  benchmark_retailer: string;
  /**
   * @minItems 1
   */
  competitors: [string, ...string[]];
  product_pack: {
    id: string;
    name: string;
    version: string;
  };
  leadership_objective: string;
  /**
   * @minItems 1
   */
  required_topics: [Topic, ...Topic[]];
  decision_lenses: Lens[];
  /**
   * @minItems 1
   */
  facts: [Fact, ...Fact[]];
  /**
   * @minItems 1
   */
  storylines: [Storyline, ...Storyline[]];
  /**
   * @minItems 1
   */
  requested_sections: [Section, ...Section[]];
  guardrails: {
    required_caveats: string[];
    forbidden_claims: string[];
    /**
     * @minItems 1
     */
    action_principles: [string, ...string[]];
    small_sample_threshold: number;
    numeric_claim_policy: "metric_placeholders_only";
  };
}
export interface Lens {
  id: string;
  label: string;
  question: string;
  metric_refs: Refs;
  evidence_refs: Refs;
}
export interface Fact {
  id: string;
  kind:
    | "source_scope"
    | "coverage"
    | "comparison_overall"
    | "comparison_segment"
    | "geographic_validation"
    | "data_quality";
  label: string;
  significance: "context" | "strength" | "watch" | "risk" | "caveat";
  metric_refs: Refs;
  evidence_refs: Refs;
  context: {
    [k: string]: string | boolean | null;
  };
}
export interface Storyline {
  id: string;
  kind:
    | "scope"
    | "competitive_pressure"
    | "benchmark_strength"
    | "mixed_position"
    | "segment_reversal"
    | "geographic_validation"
    | "quality_limitation"
    | "action";
  headline: string;
  interpretation: string;
  priority: number;
  /**
   * @minItems 1
   */
  topic_refs: [Topic, ...Topic[]];
  fact_refs: Refs;
  metric_refs: Refs;
  evidence_refs: Refs;
}
export interface Section {
  id: string;
  heading: string;
  objective: string;
  /**
   * @minItems 1
   */
  required_topics: [Topic, ...Topic[]];
  storyline_refs: Refs;
  allowed_metric_refs: Refs;
  allowed_evidence_refs: Refs;
}
