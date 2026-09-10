import { describe, expect, it } from "vitest";

import type { AnalysisRecord, AnalysisReportView, ApiResult } from "./api";
import {
  CANONICAL_REPORT_DATASET_HEADERS,
  type CanonicalReportDatasetFetcher,
  loadCanonicalReportDatasetResponse,
} from "./canonical-report-dataset-route";

function analysisRecord(schemaVersion = "2.0.0"): AnalysisRecord {
  return {
    id: "analysis-row-1",
    analysis_run_id: "run-1",
    analysis_id: "fresh_bananas-active",
    collection_run_id: "collection-1",
    status: "ready",
    reporting_status: "ready",
    product_pack_id: "fresh_bananas",
    product_pack_version: "1.0.0",
    schema_version: schemaVersion,
    checksum: "a".repeat(64),
    result: {} as AnalysisRecord["result"],
    created_at: "2026-09-09T18:00:00Z",
  };
}

function emptyReportView(): AnalysisReportView {
  return {
    schema_version: "1.1.0",
    analysis_id: "fresh_bananas-active",
    generated_at: "2026-09-09T18:00:00Z",
    benchmark_retailer: "Walmart (US)",
    competitors: ["ALDI (US)"],
    retailer_scope: {
      benchmark: { id: "walmart_us", name: "Walmart (US)" },
      competitors: [{ id: "aldi_us", name: "ALDI (US)" }],
    },
    retailer_scorecards: [],
    product_pack: {
      id: "fresh_bananas",
      name: "Fresh Bananas & Plantains",
      version: "1.0.0",
      recommended_charts: [],
    },
    blueprint: { id: "decision-led", version: "1.0.0" },
    comparison_bases: [],
    match_governance: {
      mode: "governed",
      match_revision_id: "match-revision-1",
      matching_v2_gold_set_release_id: "gold-set-1",
      applied_policy_revision_id: null,
      staged_revision_id: null,
      suggested: 0,
      confirmed: 0,
      rejected: 0,
      ambiguous: 0,
    },
    report_readiness: {
      status: "ready",
      blocking_reasons: [],
      warnings: [],
      suppressed_decisions: 0,
    },
    groups: [],
    sections: [],
    result_checksum: "a".repeat(64),
    publication: null,
    certification_coverage: {
      authority: "matching_v2",
      queue_case_count: 0,
      certified_label_count: 0,
      certified_comparable_count: 0,
      certified_not_comparable_count: 0,
      unresolved_excluded_count: 0,
      pending_unreviewed_count: 0,
      automatic_fallback_enabled: false,
    },
    match_candidates: [],
    product_decisions: [],
    assortment_analysis: {
      source: "Search",
      grain: "retailer product x location",
      distribution_contract: {
        version: "1.0.0",
        basis: "positive_price_store_search_result",
        grain: "retailer_product_id_x_store_id",
        deduplication: "distinct_store_id_per_product",
        price_rule: "price_gt_zero",
        inventory_claim: false,
        stock_status_used: false,
        sponsorship_used: false,
      },
      benchmark_retailer: "walmart_us",
      retailers: [],
      comparisons: [],
    },
  } as unknown as AnalysisReportView;
}

function singleResponseFetcher(
  response: ApiResult<unknown>,
): CanonicalReportDatasetFetcher {
  return async <T>() => response as ApiResult<T>;
}

describe("loadCanonicalReportDatasetResponse", () => {
  it("returns the upstream analysis error without fetching the report", async () => {
    const calls: Array<{ path: string; timeoutMs?: number }> = [];
    const getApi: CanonicalReportDatasetFetcher = async (path, timeoutMs) => {
      calls.push({ path, timeoutMs });
      return {
        data: null,
        status: 503,
        error: "API unavailable",
      };
    };

    const response = await loadCanonicalReportDatasetResponse(
      "fresh bananas",
      getApi,
    );

    expect(response).toEqual({
      body: { error: "API unavailable" },
      status: 503,
      headers: CANONICAL_REPORT_DATASET_HEADERS,
    });
    expect(calls).toEqual([
      { path: "/api/v1/analyses/fresh%20bananas", timeoutMs: 30_000 },
    ]);
  });

  it("rejects non-v2 analyses before loading a report view", async () => {
    const calls: Array<{ path: string; timeoutMs?: number }> = [];
    const getApi: CanonicalReportDatasetFetcher = async <T>(
      path: string,
      timeoutMs?: number,
    ) => {
      calls.push({ path, timeoutMs });
      return {
        data: analysisRecord("1.0.0") as T,
        status: 200,
        error: null,
      };
    };

    const response = await loadCanonicalReportDatasetResponse(
      "fresh_bananas-active",
      getApi,
    );

    expect(response).toEqual({
      body: {
        error:
          "Canonical report dataset preview requires an AnalysisResult v2 report.",
      },
      status: 409,
      headers: CANONICAL_REPORT_DATASET_HEADERS,
    });
    expect(calls).toHaveLength(1);
  });

  it("returns the upstream report error with private no-store headers", async () => {
    const getApi: CanonicalReportDatasetFetcher = async <T>(path: string) => {
      if (path.endsWith("/report")) {
        return {
          data: null,
          status: 504,
          error: "Report timed out",
        };
      }
      return {
        data: analysisRecord() as T,
        status: 200,
        error: null,
      };
    };

    const response = await loadCanonicalReportDatasetResponse(
      "fresh_bananas-active",
      getApi,
    );

    expect(response).toEqual({
      body: { error: "Report timed out" },
      status: 504,
      headers: CANONICAL_REPORT_DATASET_HEADERS,
    });
  });

  it("projects a v2 analysis and report view into the canonical dataset", async () => {
    const calls: Array<{ path: string; timeoutMs?: number }> = [];
    const getApi: CanonicalReportDatasetFetcher = async <T>(
      path: string,
      timeoutMs?: number,
    ) => {
      calls.push({ path, timeoutMs });
      if (path.endsWith("/report")) {
        return {
          data: emptyReportView() as T,
          status: 200,
          error: null,
        };
      }
      return {
        data: analysisRecord() as T,
        status: 200,
        error: null,
      };
    };

    const response = await loadCanonicalReportDatasetResponse(
      "fresh_bananas-active",
      getApi,
    );

    expect(response.status).toBeUndefined();
    expect(response.headers).toBe(CANONICAL_REPORT_DATASET_HEADERS);
    expect(response.body).toMatchObject({
      schema_version: "1.0.0",
      analysis_id: "fresh_bananas-active",
      readiness: {
        status: "blocked",
        blocking_reasons: [
          {
            code: "no_reportable_product_relationships",
          },
        ],
      },
      summary: {
        relationship_count: 0,
        excluded_relationship_count: 0,
      },
    });
    expect(calls).toEqual([
      { path: "/api/v1/analyses/fresh_bananas-active", timeoutMs: 30_000 },
      {
        path: "/api/v1/analyses/fresh_bananas-active/report",
        timeoutMs: 120_000,
      },
    ]);
  });

  it("fails closed when the projected canonical dataset has integrity blockers", async () => {
    const getApi: CanonicalReportDatasetFetcher = async <T>(path: string) => {
      if (path.endsWith("/report")) {
        return {
          data: emptyReportView() as T,
          status: 200,
          error: null,
        };
      }
      return {
        data: analysisRecord() as T,
        status: 200,
        error: null,
      };
    };

    const response = await loadCanonicalReportDatasetResponse(
      "fresh_bananas-active",
      getApi,
      () => [
        {
          code: "summary_relationship_count_mismatch",
          message: "Summary relationship count does not match.",
        },
      ],
    );

    expect(response).toEqual({
      body: {
        error:
          "Canonical report dataset failed integrity checks: summary_relationship_count_mismatch",
      },
      status: 422,
      headers: CANONICAL_REPORT_DATASET_HEADERS,
    });
  });

  it("uses a generic unavailable message when an upstream error is empty", async () => {
    const response = await loadCanonicalReportDatasetResponse(
      "fresh_bananas-active",
      singleResponseFetcher({
        data: null,
        status: 500,
        error: null,
      }),
    );

    expect(response).toEqual({
      body: { error: "Canonical report dataset is unavailable." },
      status: 500,
      headers: CANONICAL_REPORT_DATASET_HEADERS,
    });
  });
});
