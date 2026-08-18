import { describe, expect, it } from "vitest";

import type {
  AlertDefinitionRecord,
  AnalysisRecord,
  CollectionDefinitionRecord,
  RunRecord,
} from "./api";
import {
  describeAlertCondition,
  isInternalAcceptanceRecord,
  isOperationalFailure,
  summarizeAnalysis,
  summarizeQuality,
} from "./primary-app";

function analysis(overrides: Record<string, unknown> = {}): AnalysisRecord {
  return {
    id: "record-1",
    analysis_run_id: "analysis-run-1",
    analysis_id: "analysis-1",
    collection_run_id: "run-1",
    status: "succeeded",
    product_pack_id: "fresh_ground_beef",
    product_pack_version: "1.0.0",
    schema_version: "2.0.0",
    checksum: "a".repeat(64),
    result: {
      schema_version: "2.0.0",
      analysis_id: "analysis-1",
      analysis_run_id: "analysis-run-1",
      generated_at: "2026-08-10T12:00:00Z",
      source: {
        input_set_id: "input-1",
        kind: "historical_import",
        collection_run_id: null,
        observed_start: "2026-08-07T00:00:00Z",
        observed_end: "2026-08-07T12:00:00Z",
        sampling: false,
        total_rows: 1000,
        source_artifact_ids: [],
      },
      benchmark_retailer: "walmart_us",
      competitors: ["aldi_us", "amazon_us_same_day"],
      product_pack: {
        id: "fresh_ground_beef",
        version: "1.0.0",
        checksum_sha256: "b".repeat(64),
        report_blueprint: { id: "ground-beef", version: "1.0.0" },
      },
      metrics: [],
      evidence_sets: [],
      comparisons: [],
      assortment: { metric_refs: [], evidence_refs: [] },
      data_quality: {
        status: "warning",
        metric_refs: [],
        issue_counts: {
          review_offers: 25,
          normalization_rejections: 100,
          zero_or_missing_price_offers: 10,
        },
        evidence_refs: [],
      },
      validation: {
        status: "ready_to_share",
        golden_status: "passed",
        unsupported_numeric_claims: 0,
        metric_reference_coverage: 1,
        checks: [],
      },
      insights: [],
      narratives: [],
      artifacts: [],
      provenance: {
        analytics_code_version: "0.1.0",
        raw_source_artifact_ids: [],
        deterministic_result_checksum_sha256: "c".repeat(64),
        final_result_checksum_sha256: "a".repeat(64),
      },
      ...overrides,
    } as unknown as AnalysisRecord["result"],
    created_at: "2026-08-10T12:00:00Z",
  };
}

describe("primary application presentation", () => {
  it("prioritizes unresolved review work over general caveats", () => {
    const summary = summarizeQuality(analysis());
    expect(summary.tier).toBe("review_required");
    expect(summary.label).toBe("Review required");
    expect(summary.totalIssues).toBe(135);
    expect(summary.issues[0]).toMatchObject({
      key: "review_offers",
      count: 25,
      rate: 0.025,
    });
  });

  it("uses named retailers and full-scope source context", () => {
    const summary = summarizeAnalysis(analysis());
    expect(summary.category).toBe("Fresh Ground Beef");
    expect(summary.benchmarkRetailer).toBe("Walmart");
    expect(summary.competitors).toEqual(["ALDI", "Amazon Same Day"]);
    expect(summary.sourceRows).toBe(1000);
    expect(summary.sourceScope).toBe("Full collection scope");
  });

  it("recognizes blocked validation states", () => {
    const summary = summarizeQuality(
      analysis({
        data_quality: { status: "failed", issue_counts: { blocker: 2 } },
        validation: { status: "failed" },
      }),
    );
    expect(summary.tier).toBe("blocked");
    expect(summary.label).toBe("Blocked");
  });

  it("does not count certified matching totals as quality issues", () => {
    const summary = summarizeQuality(
      analysis({
        data_quality: {
          status: "warning",
          issue_counts: {
            matching_v2_certified_comparable: 183,
            matching_v2_certified_not_comparable: 1,
            matching_v2_unresolved_excluded: 1,
          },
        },
        validation: { status: "needs_review" },
      }),
    );
    expect(summary.totalIssues).toBe(1);
    expect(summary.issues.map((issue) => issue.key)).toEqual([
      "matching_v2_unresolved_excluded",
    ]);
  });

  it("keeps disabled test failures in history but out of the operational queue", () => {
    const run = {
      id: "run-1",
      definition_version_id: "definition-version-1",
      status: "failed",
    } as RunRecord;
    const definitions = [
      {
        version_id: "definition-version-1",
        active: false,
      } as CollectionDefinitionRecord,
    ];
    expect(isOperationalFailure(run, definitions)).toBe(false);
    expect(isOperationalFailure(run, [])).toBe(true);
  });

  it("turns an alert condition into business language", () => {
    const alert = {
      config: {
        selector: { field: "competitor_lower_rate" },
        condition: {
          operator: "change_gte",
          threshold: 5,
          change_mode: "percent",
        },
      },
    } as unknown as AlertDefinitionRecord;
    expect(describeAlertCondition(alert)).toBe(
      "Notify when competitor lower rate changes by at least 5%.",
    );
  });

  it("hides internal phase acceptance fixtures from business views", () => {
    expect(isInternalAcceptanceRecord("phase09-automation-acceptance")).toBe(
      true,
    );
    expect(isInternalAcceptanceRecord("Weekly Fresh Beef")).toBe(false);
  });
});
