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
  retailer_packs: {
    retailer_id: string;
    version: string;
    checksum_sha256: string;
    brand_foundation: {
      id: string;
      version: string;
      checksum_sha256: string;
    };
  }[];
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
      relationship_scope_policy?: {
        [k: string]: unknown;
      };
    },
    ...{
      profile_id: string;
      label: string;
      geography: "exact_zip" | "same_store_market" | "radius" | "national";
      comparison_metric: string;
      dimensions: string[];
      relationship_scope_policy?: {
        [k: string]: unknown;
      };
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
  kind: "live_collection" | "live_collection_composite" | "historical_import";
  collection_run_id?: string | null;
  base_collection_run_id?: string | null;
  component_collection_run_ids?: string[];
  input_manifest_checksum?: string | null;
  collection_evidence_readiness?: {
    [k: string]: {
      [k: string]: unknown;
    };
  } | null;
  unavailable_retailers?: string[];
  collection_scope_projections?: {
    id: string;
    retailer_id: string;
    projection_kind: "canonical_alias_collapse" | "limited_provider_footprint" | "audited_alias_reconciliation";
    projection_checksum: string;
    raw_task_count: number;
    retained_task_count: number;
    excluded_task_count: number;
    raw_location_count: number;
    retained_location_count: number;
    excluded_location_count: number;
    denominator_gap_location_count?: number;
    raw_task_retention_ratio: string;
    governed_coverage_ratio: string;
    minimum_scoreable_coverage: string;
    scorecard_disposition: "scoreable" | "unavailable";
    coverage_numerator_location_count?: number;
    coverage_denominator_location_count?: number;
    coverage_semantics?: string;
    source_audit_id: string | null;
    source_evidence_checksum: string;
    inventory_checksum: string;
    policy_version: string;
  }[];
  match_revision_id?: string | null;
  matching_v2_gold_set_release_id?: string | null;
  matching_v2_gold_set_checksum?: string | null;
  matching_v2_certification_coverage?: {
    authority: "matching_v2_certified_gold_set";
    source_candidate_count?: number;
    selected_candidate_count?: number;
    selection_complete?: boolean;
    selection_coverage_rate?: number;
    queue_case_count: number;
    certified_label_count: number;
    certified_comparable_count: number;
    certified_not_comparable_count: number;
    unresolved_excluded_count: number;
    reviewed_insufficient_evidence_count?: number;
    pending_unreviewed_count?: number;
    automatic_fallback_enabled: false;
    retailers?: {
      competitor_retailer_id: string;
      candidate_count: number;
      certified_count: number;
      certified_comparable_count: number;
      certified_not_comparable_count: number;
      reviewed_insufficient_evidence_count?: number;
      pending_unreviewed_count?: number;
      unresolved_count: number;
    }[];
  } | null;
  matching_v2_reporting_coverage?: {
    authority: "matching_v2_scoreable_retailer_projection";
    source_authority: string;
    source_coverage_checksum: string;
    scoreable_retailer_ids: string[];
    unavailable_retailer_ids: string[];
    source_candidate_count: number;
    selected_candidate_count: number;
    selection_complete: boolean;
    queue_case_count: number;
    certified_label_count: number;
    certified_comparable_count: number;
    certified_not_comparable_count: number;
    unresolved_excluded_count: number;
    reviewed_insufficient_evidence_count: number;
    pending_unreviewed_count: number;
    automatic_fallback_enabled: false;
    retailers: MatchingV2RetailerCoverage[];
    excluded_unavailable_retailers: MatchingV2RetailerCoverage[];
    withheld_certified_comparable_count: number;
    withheld_certified_not_comparable_count: number;
    projection_checksum: string;
  } | null;
  brand_revision_id?: string | null;
  source_analysis_id?: string | null;
  replay_generation?: number;
  replay_reason?: string | null;
  observed_start?: string | null;
  observed_end?: string | null;
  sampling: boolean;
  total_rows: number;
  /**
   * @minItems 1
   */
  source_artifact_ids: [string, ...string[]];
}
export interface MatchingV2RetailerCoverage {
  competitor_retailer_id: string;
  candidate_count: number;
  certified_count: number;
  certified_comparable_count: number;
  certified_not_comparable_count: number;
  reviewed_insufficient_evidence_count?: number;
  pending_unreviewed_count?: number;
  unresolved_count: number;
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
