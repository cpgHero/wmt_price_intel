import type {
  RetailCompetitiveIntelligenceAnalysisResult,
  RetailCompetitiveIntelligenceAnalysisResultV2,
  RetailCompetitiveIntelligenceBrandWorkbench,
  RetailCompetitiveIntelligenceCollectionGeographyRequest,
  RetailCompetitiveIntelligenceCollectionGeographyResolution,
  RetailCompetitiveIntelligenceCollectionScopeEstimate,
  RetailCompetitiveIntelligenceCompetitiveProductLeadership,
  RetailCompetitiveIntelligenceProductMatchReview,
  RetailCompetitiveIntelligenceProductMatchScope,
  RetailCompetitiveIntelligencePriceMonitoringMap,
  RetailCompetitiveIntelligencePriceMonitoringView,
  RetailCompetitiveIntelligenceReportView,
} from "@rci/contracts";

import { loadServerConfig } from "./config";

export type JsonObject = Record<string, unknown>;
export type PriceMonitoringView =
  RetailCompetitiveIntelligencePriceMonitoringView;
export type PriceMonitoringMap =
  RetailCompetitiveIntelligencePriceMonitoringMap;
export type CompetitiveProductLeadership =
  RetailCompetitiveIntelligenceCompetitiveProductLeadership;

export interface AnalysisRecord {
  id: string;
  analysis_run_id: string;
  analysis_id: string;
  collection_run_id: string;
  status: string;
  product_pack_id: string;
  product_pack_version: string;
  schema_version: string;
  checksum: string;
  result:
    | RetailCompetitiveIntelligenceAnalysisResult
    | RetailCompetitiveIntelligenceAnalysisResultV2;
  created_at: string;
}

export interface ReportSectionView {
  id: string;
  title: string;
  kind: string;
  visualization: string;
  required: boolean;
  empty: boolean;
  empty_state?: string;
  metrics: JsonObject[];
  records: JsonObject[];
  evidence_sets: JsonObject[];
  narrative: JsonObject | null;
}

export interface AnalysisReportView extends Omit<
  RetailCompetitiveIntelligenceReportView,
  | "retailer_scorecards"
  | "product_pack"
  | "product_highlights"
  | "product_decisions"
  | "match_candidates"
  | "suppressed_product_decisions"
  | "map_points"
  | "quality_observations"
  | "assortment_analysis"
  | "sections"
> {
  analysis_id: string;
  generated_at: string;
  benchmark_retailer: string;
  competitors: string[];
  retailer_scope: {
    benchmark: RetailerOption;
    competitors: RetailerOption[];
  };
  retailer_scorecards: RetailerScorecard[];
  product_pack: {
    id: string;
    name: string;
    version: string;
    recommended_charts?: string[];
    cohort_dimensions?: string[];
    minimum_cohort_geographies?: number;
  };
  blueprint: { id: string; version: string };
  product_highlights?: ProductHighlight[];
  product_decisions?: ProductDecision[];
  match_candidates?: ProductMatchCandidate[];
  suppressed_product_decisions?: ProductDecision[];
  map_points?: MapPoint[];
  quality_observations?: QualityObservation[];
  assortment_analysis?: AssortmentAnalysis;
  sections: ReportSectionView[];
}

export interface ProductMatchCandidate {
  id: string;
  relationship_id?: string | null;
  relationship_status?:
    | "suggested"
    | "confirmed"
    | "rejected"
    | "ambiguous"
    | "unmatched"
    | "unavailable";
  qa_status?: "ready" | "review_required" | "suppressed";
  profile_id?: string | null;
  benchmark_product_id: string;
  benchmark_product_name: string;
  benchmark_image_url?: string | null;
  competitor: string;
  competitor_product_id: string;
  geographies?: number;
  matches?: number;
}

export interface AssortmentProduct {
  product_id: string;
  canonical_product_id: string;
  name: string;
  brand?: string | null;
  image_url?: string | null;
  url?: string | null;
  observed_locations: number;
  observed_zipcodes: number;
}

export interface AssortmentComparison {
  competitor: string;
  product_relationships: number;
  ambiguous_candidate_groups?: number;
  matched_benchmark_products: number;
  matched_competitor_products: number;
  benchmark_match_coverage: number;
  competitor_match_coverage: number;
  benchmark_only_products: number;
  competitor_whitespace_products: number;
  profiles: Array<{
    profile_id: string;
    profile_label: string;
    relationships: number;
  }>;
  geography: {
    shared_zipcodes: number;
    benchmark_only_zipcodes: number;
    competitor_only_zipcodes: number;
    benchmark_broader_zipcodes: number;
    competitor_broader_zipcodes: number;
    parity_zipcodes: number;
    median_product_count_gap: number;
    top_benchmark_breadth_gaps?: AssortmentBreadthGap[];
    top_competitor_breadth_gaps?: AssortmentBreadthGap[];
  };
  top_benchmark_only: AssortmentProduct[];
  top_competitor_whitespace: AssortmentProduct[];
  key_points: string[];
}

export interface AssortmentAnalysis {
  source: string;
  grain: string;
  benchmark_retailer: string;
  retailers: Array<{
    retailer: string;
    distinct_products: number;
    observed_locations: number;
    observed_zipcodes: number;
    median_products_per_location: number;
    distinct_brands?: number;
    unbranded_products?: number;
    top_brands?: AssortmentBrand[];
    geographically_concentrated_brands?: AssortmentBrand[];
  }>;
  comparisons: AssortmentComparison[];
}

export interface AssortmentBrand {
  brand: string;
  distinct_products: number;
  observed_locations: number;
  observed_zipcodes: number;
  location_share: number;
}

export interface AssortmentBreadthGap {
  zipcode: string;
  benchmark_products: number;
  competitor_products: number;
  product_count_gap: number;
}

export interface RetailerOption {
  id: string;
  name: string;
}

export interface RetailerScorecard {
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
  dominant_outcome:
    "benchmark_lower" | "competitor_lower" | "parity" | "unavailable";
  price_position: string;
  status: "ready" | "limited_evidence";
}

export interface QualityObservation {
  issue: string;
  retailer: string;
  product: string;
  product_id?: string | null;
  price?: string | number | null;
  zipcode?: string | null;
  store?: string | null;
  reason: string;
  source_url?: string | null;
  image_url?: string | null;
}

export interface ProductDecision {
  id: string;
  relationship_id?: string | null;
  relationship_status?:
    "suggested" | "confirmed" | "rejected" | "ambiguous" | "unavailable";
  profile_id?: string | null;
  comparison_metric?: string | null;
  qa_status?: "ready" | "review_required" | "suppressed";
  suppression_reasons?: string[];
  priority: "attention" | "protect" | "parity";
  benchmark_product_id: string;
  benchmark_product_name: string;
  benchmark_image_url?: string | null;
  benchmark_product_url?: string | null;
  competitor: string;
  competitor_product_id: string;
  competitor_product_name: string;
  competitor_image_url?: string | null;
  competitor_product_url?: string | null;
  matches: number;
  geographies: number;
  benchmark_lower: number;
  competitor_lower: number;
  parity: number;
  benchmark_lower_share: number;
  competitor_lower_share: number;
  median_benchmark_price: number;
  median_competitor_price: number;
  median_gap: number;
  plain_insight: string;
  comparison_grain?: string | null;
  evidence_available?: boolean;
  evidence_summary?: {
    matched_zip_markets?: number;
    benchmark_store_observations?: number;
    competitor_store_observations?: number;
    benchmark_stores_lower?: number;
    benchmark_stores_undercut?: number;
    price_parity?: number;
  };
  top_locations: Array<{
    zipcode: string;
    store?: string | null;
    outcome: "benchmark_lower" | "competitor_lower" | "parity";
    benchmark_price: number;
    competitor_price: number;
    gap: number;
  }>;
}

export interface ProductEvidenceRow {
  id: string;
  zipcode: string;
  outcome: "benchmark_lower" | "competitor_lower" | "parity";
  benchmark_retailer: string;
  benchmark_product_id: string;
  benchmark_product_name: string;
  benchmark_store?: string | null;
  benchmark_price: number;
  benchmark_comparison_value?: number;
  competitor: string;
  competitor_product_id: string;
  competitor_product_name: string;
  competitor_store?: string | null;
  competitor_price: number;
  competitor_comparison_value?: number;
  competitor_minus_benchmark: number;
  comparison_gap?: number;
  comparison_metric?: string;
  comparison_unit?: string;
  raw_price_unit?: "USD/package";
}

export interface ProductEvidenceResponse {
  analysis_id: string;
  publication_id: string;
  publication_version: number;
  decision: ProductDecision | null;
  decision_id: string;
  comparison_grain: string;
  comparison_metric?: string;
  comparison_unit?: string;
  raw_price_unit?: "USD/package";
  price_source: string;
  attribute_source: string;
  summary: NonNullable<ProductDecision["evidence_summary"]>;
  rows: ProductEvidenceRow[];
}

export interface ProductHighlight {
  canonical_product_id: string;
  retailer: string;
  name: string;
  brand?: string | null;
  url?: string | null;
  image_url?: string | null;
  price?: number | null;
  price_currency?: string | null;
  role?: string | null;
  detail?: string | null;
}

export type MatchReview = RetailCompetitiveIntelligenceProductMatchReview;
export type MatchReviewProduct = MatchReview["products"][number];
export type MatchReviewConnection = MatchReview["connections"][number];
export type ProductMatchScope = RetailCompetitiveIntelligenceProductMatchScope;
export type BrandWorkbench = RetailCompetitiveIntelligenceBrandWorkbench;
export type BrandWorkbenchBrand = BrandWorkbench["brands"][number];

export interface MapPoint {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  value?: number | null;
  value_label?: string | null;
  retailer?: string | null;
  benchmark_product_id?: string | null;
  benchmark_product_name?: string | null;
  benchmark_price?: number | null;
  competitor_price?: number | null;
  competitor?: string | null;
  outcome?: "benchmark_lower" | "competitor_lower" | "parity" | null;
  zipcode?: string | null;
  store?: string | null;
  matches?: number | null;
  relationship_id?: string | null;
  profile_id?: string | null;
  comparison_metric?: string | null;
}

export interface RunRecord {
  id: string;
  definition_version_id: string;
  status: string;
  trigger_type: "manual" | "scheduled" | "historical_import";
  schedule_id: string | null;
  scheduled_for: string | null;
  estimated_pages: number;
  estimated_credits: number;
  actual_success_pages: number;
  actual_credits: number;
  started_at: string | null;
  completed_at: string | null;
  cancel_requested_at: string | null;
  created_at: string;
  availability_gate_status: string;
  availability_gate_config: JsonObject;
  scope_estimate_id: string | null;
}

export interface CollectionDefinitionRecord {
  id: string;
  stable_key: string;
  name: string;
  active: boolean;
  version_id: string;
  version: number;
  checksum: string;
  config: JsonObject;
  created_at: string;
}

export interface CollectionTask {
  id: string;
  collection_run_id: string;
  retailer_id: string;
  retailer_location_id: string | null;
  adapter_id: string;
  location_scope_key: string;
  zipcode: string;
  store_number: string | null;
  page_number: number;
  max_pages: number;
  status: string;
  attempt_count: number;
  max_attempts: number;
  locked_by: string | null;
  lease_expires_at: string | null;
  http_status: number | null;
  result_count: number | null;
  failure_class: string | null;
  billable_credits: number;
  raw_artifact_id: string | null;
}

export interface RetailerEstimate {
  retailer_id: string;
  location_units: number;
  credits_per_page: number;
  max_pages: number;
  estimated_pages: number;
  estimated_credits: number;
}

export interface CostEstimate {
  definition_id: string;
  retailers: RetailerEstimate[];
  estimated_total_pages: number;
  estimated_total_credits: number;
}

export type CollectionGeographyRequest =
  RetailCompetitiveIntelligenceCollectionGeographyRequest;
export type CollectionGeographyResolution =
  RetailCompetitiveIntelligenceCollectionGeographyResolution;
export type CollectionScopeEstimate =
  RetailCompetitiveIntelligenceCollectionScopeEstimate;

export interface CollectionBuilderRetailer {
  id: string;
  display_name: string;
  adapter_id: string;
  location_dimension: "store_zip" | "zipcode";
  credits_per_page: number;
  status: "enabled";
}

export interface CollectionBuilderOptions {
  retailers: CollectionBuilderRetailer[];
  product_packs: ProductPackSummary[];
  default_product_pack_id: string;
  geography: {
    primary_selection_modes: string[];
    competitor_correspondence_modes: string[];
    radius_miles: Array<1 | 3 | 5>;
  };
  product_detail_policies: string[];
}

export interface CollectionLocationFacet {
  state: string;
  city: string | null;
  location_count: number;
}

export interface ProductPackSummary {
  id: string;
  name: string;
  version: string;
  default_keyword: string;
  active?: boolean;
}

export interface ProductPackCatalog {
  schema_version: string;
  default_pack_id: string;
  packs: ProductPackSummary[];
}

export interface ScheduleRecord {
  id: string;
  definition_id: string;
  definition_key: string;
  cron_expression: string;
  timezone: string;
  enabled: boolean;
  next_run_at: string;
  last_scheduled_for: string | null;
  last_collection_run_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertDefinitionRecord {
  id: string;
  stable_key: string;
  name: string;
  active: boolean;
  version_id: string;
  version: number;
  checksum: string;
  config: JsonObject;
  created_at: string;
}

export interface AlertEventRecord {
  id: string;
  alert_key: string;
  analysis_id: string;
  baseline_analysis_id: string | null;
  status: string;
  current_value: string | number | null;
  baseline_value: string | number | null;
  change_value: string | number | null;
  evidence: JsonObject;
  created_at: string;
}

export interface EmailDeliveryRecord {
  id: string;
  analysis_id: string;
  delivery_type: string;
  recipients: string[];
  subject: string;
  evidence: JsonObject;
  idempotency_key: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  provider_message_id: string | null;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface RunUsage {
  run_id: string;
  estimated_pages: number;
  estimated_credits: number;
  actual_success_pages: number;
  actual_credits: number;
  pending_tasks: number;
  running_tasks: number;
  succeeded_tasks: number;
  failed_tasks: number;
  cancelled_tasks: number;
}

export interface RetailerRunProgress {
  retailer_id: string;
  pending_tasks: number;
  running_tasks: number;
  succeeded_tasks: number;
  failed_tasks: number;
  cancelled_tasks: number;
  billable_credits: number;
  attempts: number;
  retries: number;
}

export interface ProviderRateState {
  provider: string;
  second_count: number;
  minute_count: number;
  paused_until: string | null;
  last_429_at: string | null;
  updated_at: string;
}

export interface RunMonitor {
  run: RunRecord;
  usage: RunUsage;
  retailers: RetailerRunProgress[];
  retry_attempts: number;
  failure_classes: Record<string, number>;
  elapsed_seconds: number;
  provider_state: ProviderRateState | null;
  configured_global_rps: number;
  configured_global_rpm: number;
}

export interface ApiResult<T> {
  data: T | null;
  status: number;
  error: string | null;
}

export async function getApi<T>(
  path: string,
  timeoutMs = 5_000,
): Promise<ApiResult<T>> {
  const { apiInternalUrl } = loadServerConfig();
  try {
    const response = await fetch(new URL(path, apiInternalUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      return {
        data: null,
        status: response.status,
        error: `API returned ${response.status}`,
      };
    }
    return {
      data: (await response.json()) as T,
      status: response.status,
      error: null,
    };
  } catch {
    return {
      data: null,
      status: 503,
      error: "The API is not currently reachable from the web service.",
    };
  }
}

export async function postApi<T>(path: string): Promise<ApiResult<T>> {
  return postApiJson<T>(path);
}

export async function postApiJson<T>(
  path: string,
  body?: JsonObject,
): Promise<ApiResult<T>> {
  const { apiInternalUrl } = loadServerConfig();
  try {
    const response = await fetch(new URL(path, apiInternalUrl), {
      method: "POST",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) {
      let detail = `API returned ${response.status}`;
      try {
        const responseBody = (await response.json()) as { detail?: unknown };
        if (typeof responseBody.detail === "string") {
          detail = responseBody.detail;
        } else if (responseBody.detail) {
          detail = JSON.stringify(responseBody.detail);
        }
      } catch {
        // Preserve the status-only message for non-JSON upstream errors.
      }
      return { data: null, status: response.status, error: detail };
    }
    return {
      data: (await response.json()) as T,
      status: response.status,
      error: null,
    };
  } catch {
    return {
      data: null,
      status: 503,
      error: "The API is not currently reachable from the web service.",
    };
  }
}
