/* Generated from the normative JSON Schema. Do not edit manually. */

/**
 * @minItems 1
 */
export type NonemptyRefs = [string, ...string[]];

export interface RetailCompetitiveIntelligenceAnalysisResultV2 {
  schema_version: "2.0.0";
  analysis_id: string;
  analysis_run_id: string;
  generated_at: string;
  source: Source;
  benchmark_retailer: string;
  /**
   * @minItems 1
   */
  competitors: [string, ...string[]];
  product_pack: {
    id: string;
    version: string;
    checksum_sha256: string;
    report_blueprint: {
      id: string;
      version: string;
    };
  };
  /**
   * @minItems 1
   */
  metrics: [Metric, ...Metric[]];
  /**
   * @minItems 1
   */
  coverage: [
    {
      retailer_id: string;
      metric_refs: NonemptyRefs;
      evidence_refs: NonemptyRefs;
    },
    ...{
      retailer_id: string;
      metric_refs: NonemptyRefs;
      evidence_refs: NonemptyRefs;
    }[]
  ];
  /**
   * @minItems 1
   */
  comparison_modes: [
    {
      profile_id: string;
      label: string;
      geography: "exact_zip" | "same_store_market" | "radius" | "national";
      comparison_metric: string;
      dimensions: string[];
    },
    ...{
      profile_id: string;
      label: string;
      geography: "exact_zip" | "same_store_market" | "radius" | "national";
      comparison_metric: string;
      dimensions: string[];
    }[]
  ];
  segments: {
    segment_id: string;
    label: string;
    attributes: {
      [k: string]: unknown;
    };
    metric_refs: string[];
    evidence_refs: NonemptyRefs;
  }[];
  /**
   * @minItems 1
   */
  comparisons: [
    {
      comparison_id: string;
      competitor_id: string;
      profile_id: string;
      segment_id: string;
      metric_refs: NonemptyRefs;
      evidence_refs: NonemptyRefs;
    },
    ...{
      comparison_id: string;
      competitor_id: string;
      profile_id: string;
      segment_id: string;
      metric_refs: NonemptyRefs;
      evidence_refs: NonemptyRefs;
    }[]
  ];
  geographic_sensitivity: {
    id: string;
    profile_id: string;
    radius_miles: number;
    metric_refs: NonemptyRefs;
    evidence_refs: NonemptyRefs;
  }[];
  assortment: {
    metric_refs: string[];
    evidence_refs: NonemptyRefs;
  };
  data_quality: {
    status: "ready" | "warning" | "blocked";
    metric_refs: string[];
    issue_counts: {
      [k: string]: number;
    };
    evidence_refs: NonemptyRefs;
  };
  validation: {
    status: "ready_to_share" | "needs_review" | "blocked";
    golden_status: "not_applicable" | "passed" | "failed";
    unsupported_numeric_claims: number;
    metric_reference_coverage: number;
    /**
     * @minItems 1
     */
    checks: [
      {
        id: string;
        status: "passed" | "failed" | "warning";
        evidence_refs?: string[];
      },
      ...{
        id: string;
        status: "passed" | "failed" | "warning";
        evidence_refs?: string[];
      }[]
    ];
  };
  insights: Insight[];
  recommendations: Recommendation[];
  narratives: {
    generation_mode: "deterministic" | "ai_assisted";
    agent_task_ids?: string[];
    /**
     * @minItems 1
     */
    sections: [NarrativeSection, ...NarrativeSection[]];
  };
  /**
   * @minItems 1
   */
  evidence_sets: [
    {
      evidence_set_id: string;
      kind: string;
      row_count: number;
      checksum_sha256: string;
    },
    ...{
      evidence_set_id: string;
      kind: string;
      row_count: number;
      checksum_sha256: string;
    }[]
  ];
  artifacts: {
    artifact_type: "html" | "xlsx" | "leadership_email" | "audit_zip";
    artifact_id: string;
    checksum_sha256: string;
    template_version: string;
  }[];
  provenance: {
    analytics_code_version: string;
    deterministic_result_checksum_sha256: string;
    final_result_checksum_sha256: string;
    /**
     * @minItems 1
     */
    raw_source_artifact_ids: [string, ...string[]];
  };
}
export interface Source {
  input_set_id: string;
  kind: "live_collection" | "historical_import";
  collection_run_id?: string | null;
  observed_start?: string | null;
  observed_end?: string | null;
  sampling: boolean;
  total_rows: number;
  /**
   * @minItems 1
   */
  source_artifact_ids: [string, ...string[]];
}
export interface Metric {
  metric_id: string;
  name: string;
  value: number;
  unit: string;
  numerator?: number;
  denominator?: number;
  method: string;
  source: "deterministic";
  evidence_refs: NonemptyRefs;
}
export interface Insight {
  id: string;
  title: string;
  summary: string;
  severity: "positive" | "info" | "watch" | "high" | "critical";
  business_impact: string;
  metric_refs: NonemptyRefs;
  evidence_refs: NonemptyRefs;
  confidence: number;
  limitations?: string[];
  generated_by: "deterministic" | "ai_assisted";
}
export interface Recommendation {
  id: string;
  priority: number;
  action: string;
  owner: string;
  rationale: string;
  metric_refs: NonemptyRefs;
  evidence_refs: NonemptyRefs;
}
export interface NarrativeSection {
  id: string;
  heading: string;
  body: string;
  subtitle?: string;
  /**
   * @maxItems 5
   */
  bullets?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  implication?: string;
  /**
   * @minItems 1
   */
  topic_refs?: [
    (
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
      | "caveats"
    ),
    ...(
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
      | "caveats"
    )[]
  ];
  /**
   * @minItems 1
   */
  storyline_refs?: [string, ...string[]];
  product_refs?: string[];
  metric_refs: NonemptyRefs;
  evidence_refs: NonemptyRefs;
}
