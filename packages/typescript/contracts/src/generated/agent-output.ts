/* Generated from the normative JSON Schema. Do not edit manually. */

export type RetailCompetitiveIntelligenceGovernedAgentOutput = {
  [k: string]: unknown;
} & {
  schema_version: "1.0.0";
  task_id: string;
  analysis_id: string;
  role: "classification_fallback" | "comparison_qa" | "insight" | "narrative";
  prompt_template: {
    id: string;
    version: string;
    checksum_sha256: string;
  };
  model: {
    provider: string;
    model_id: string;
  };
  input_checksum_sha256: string;
  output_checksum_sha256: string;
  /**
   * @minItems 1
   */
  evidence_refs: [string, ...string[]];
  generated_at: string;
  authoritative_metrics_computed: false;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    latency_ms?: number;
    estimated_cost_usd?: number;
  };
  result: {
    [k: string]: unknown;
  };
  validation: {
    status: "pending" | "passed" | "failed" | "needs_review";
    unsupported_numeric_claims: number;
    metric_reference_coverage: number;
    issues?: string[];
  };
};
