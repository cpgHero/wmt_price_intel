/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceReportView {
  schema_version: "1.1.0";
  analysis_id: string;
  generated_at: string;
  benchmark_retailer: string;
  competitors: string[];
  retailer_scope: {
    benchmark: Retailer;
    competitors: Retailer[];
  };
  retailer_scorecards: Scorecard[];
  product_pack: {
    id: string;
    name: string;
    version: string;
    recommended_charts: string[];
    cohort_dimensions?: string[];
    minimum_cohort_geographies?: number;
  };
  blueprint: {
    id: string;
    version: string;
  };
  comparison_bases: ComparisonBasis[];
  match_governance: MatchGovernance;
  report_readiness: ReportReadiness;
  certification_coverage?: null | {
    authority?: string;
    source_candidate_count?: number;
    selected_candidate_count?: number;
    selection_complete?: boolean;
    selection_coverage_rate?: number;
    queue_case_count: number;
    certified_label_count: number;
    certified_comparable_count: number;
    certified_not_comparable_count: number;
    unresolved_excluded_count: number;
    automatic_fallback_enabled: boolean;
    retailers?: {
      competitor_retailer_id: string;
      candidate_count: number;
      certified_count: number;
      certified_comparable_count: number;
      certified_not_comparable_count: number;
      unresolved_count: number;
    }[];
    [k: string]: unknown;
  };
  groups: Group[];
  sections: Section[];
  result_checksum: string;
  publication: null | Publication;
  product_highlights?: {
    [k: string]: unknown;
  }[];
  product_evidence?: {
    [k: string]: {
      [k: string]: unknown;
    };
  };
  product_decisions?: ProductDecision[];
  suppressed_product_decisions?: ProductDecision[];
  match_candidates?: {
    [k: string]: unknown;
  }[];
  match_relationships?: {
    [k: string]: unknown;
  }[];
  ambiguous_match_groups?: {
    [k: string]: unknown;
  }[];
  map_points?: {
    [k: string]: unknown;
  }[];
  quality_observations?: {
    [k: string]: unknown;
  }[];
  assortment_analysis?: {
    [k: string]: unknown;
  };
  notes?: string[];
}
export interface Retailer {
  id: string;
  name: string;
}
export interface Scorecard {
  competitor_id: string;
  competitor: string;
  benchmark_retailer_id: string;
  benchmark_retailer: string;
  profile_id: string;
  comparison_lens: string;
  comparison_metric: string;
  price_unit: string;
  package_basis: "exact_package" | "normalized_unit" | "configured_interval";
  geography: string;
  basis_status: "preferred" | "fallback" | "unavailable";
  matches: number | null;
  matched_geographies: number | null;
  qualifying_geographies: number | null;
  benchmark_lower_rate: number | null;
  competitor_lower_rate: number | null;
  parity_rate: number | null;
  benchmark_median: number | null;
  competitor_median: number | null;
  median_gap: number | null;
  benchmark_median_statistic: "marginal_median";
  competitor_median_statistic: "marginal_median";
  median_gap_statistic: "paired_median_gap";
  minimum_observations: number;
  minimum_geographies: number;
  readiness_reason: string;
  evidence_state: "reported" | "no_matched_observations" | "no_governed_relationships" | "no_admissible_observations";
  dominant_outcome: "benchmark_lower" | "competitor_lower" | "parity" | "unavailable";
  price_position: string;
  status: "ready" | "limited_evidence";
}
export interface ComparisonBasis {
  profile_id: string;
  label: string;
  geography: string;
  comparison_metric: string;
  price_unit: string;
  package_basis: "exact_package" | "normalized_unit" | "configured_interval";
  availability_policy: string;
  population_basis: "relationship_resolved_products" | "market_floor";
  scorecard_role?: "preferred" | "fallback" | "excluded";
}
export interface MatchGovernance {
  mode: "ungoverned" | "governed";
  match_revision_id: string | null;
  applied_policy_revision_id: string | null;
  staged_revision_id: string | null;
  suggested: number;
  confirmed: number;
  rejected: number;
  ambiguous: number;
}
export interface ReportReadiness {
  status: "ready" | "review_required" | "limited";
  blocking_reasons: ReadinessReason[];
  warnings: ReadinessReason[];
  suppressed_decisions: number;
}
export interface ReadinessReason {
  code: string;
  message: string;
  competitor_id?: string | null;
  profile_id?: string | null;
  relationship_id?: string | null;
}
export interface Group {
  id: string;
  label: string;
  section_ids: string[];
}
export interface Section {
  id: string;
  title: string;
  kind: string;
  visualization: string;
  required: boolean;
  empty: boolean;
  empty_state?: string | null;
  metrics: {
    [k: string]: unknown;
  }[];
  records: {
    [k: string]: unknown;
  }[];
  evidence_sets: {
    [k: string]: unknown;
  }[];
  narrative: null | {
    [k: string]: unknown;
  };
}
export interface Publication {
  id: string;
  version: number;
  status: string;
  source_result_checksum: string;
  publication_checksum: string;
  created_at: string;
}
export interface ProductDecision {
  id: string;
  relationship_id?: string | null;
  relationship_status?: "suggested" | "confirmed" | "rejected" | "ambiguous" | "unavailable";
  profile_id?: string | null;
  comparison_metric?: string | null;
  qa_status?: "ready" | "review_required" | "suppressed";
  suppression_reasons?: string[];
  benchmark_product_id: string;
  competitor_product_id: string;
  competitor: string;
  matches?: number;
  geographies?: number;
  benchmark_lower?: number;
  competitor_lower?: number;
  parity?: number;
  median_gap?: number;
  plain_insight?: string;
  top_locations?: unknown[];
  [k: string]: unknown;
}
