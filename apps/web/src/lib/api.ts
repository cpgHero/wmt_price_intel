import type {
  RetailCompetitiveIntelligenceAnalysisResult,
  RetailCompetitiveIntelligenceAnalysisResultV2,
} from "@rci/contracts";

import { loadServerConfig } from "./config";

export type JsonObject = Record<string, unknown>;

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

export interface AnalysisReportView {
  analysis_id: string;
  generated_at: string;
  benchmark_retailer: string;
  competitors: string[];
  product_pack: {
    id: string;
    name: string;
    version: string;
    recommended_charts?: string[];
  };
  blueprint: { id: string; version: string };
  result_checksum: string;
  publication: {
    id: string;
    version: number;
    status: string;
    source_result_checksum: string;
    publication_checksum: string;
    created_at: string;
  } | null;
  product_highlights?: ProductHighlight[];
  product_decisions?: ProductDecision[];
  map_points?: MapPoint[];
  sections: ReportSectionView[];
}

export interface ProductDecision {
  id: string;
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
  competitor: string;
  competitor_product_id: string;
  competitor_product_name: string;
  competitor_store?: string | null;
  competitor_price: number;
  competitor_minus_benchmark: number;
}

export interface ProductEvidenceResponse {
  analysis_id: string;
  publication_id: string;
  publication_version: number;
  decision: ProductDecision | null;
  decision_id: string;
  comparison_grain: string;
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

export interface ProductPackSummary {
  id: string;
  name: string;
  version: string;
  default_keyword: string;
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

export async function getApi<T>(path: string): Promise<ApiResult<T>> {
  const { apiInternalUrl } = loadServerConfig();
  try {
    const response = await fetch(new URL(path, apiInternalUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
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
