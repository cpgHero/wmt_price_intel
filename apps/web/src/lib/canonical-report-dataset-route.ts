import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";

import type { AnalysisRecord, AnalysisReportView, ApiResult } from "./api";
import { canonicalReportDatasetFromReportView } from "./canonical-report-dataset";
import { canonicalReportIntegrityIssues } from "./canonical-report-qa";

type CanonicalDataset = RetailCompetitiveIntelligenceCanonicalReportDataset;

export type CanonicalReportDatasetResponse =
  | {
      body: CanonicalDataset;
      headers: Record<string, string>;
      status?: undefined;
    }
  | {
      body: { error: string };
      headers: Record<string, string>;
      status: number;
    };

export type CanonicalReportDatasetFetcher = <T>(
  path: string,
  timeoutMs?: number,
) => Promise<ApiResult<T>>;
type CanonicalIntegrityChecker = (
  dataset: CanonicalDataset,
) => ReturnType<typeof canonicalReportIntegrityIssues>;

export const CANONICAL_REPORT_DATASET_HEADERS = {
  "Cache-Control": "private, no-store",
};

function errorResponse(
  error: string | null,
  status: number,
): CanonicalReportDatasetResponse {
  return {
    body: { error: error ?? "Canonical report dataset is unavailable." },
    status,
    headers: CANONICAL_REPORT_DATASET_HEADERS,
  };
}

export async function loadCanonicalReportDatasetResponse(
  analysisId: string,
  getApi: CanonicalReportDatasetFetcher,
  integrityChecker: CanonicalIntegrityChecker = canonicalReportIntegrityIssues,
): Promise<CanonicalReportDatasetResponse> {
  const encodedAnalysisId = encodeURIComponent(analysisId);
  const analysis = await getApi<AnalysisRecord>(
    `/api/v1/analyses/${encodedAnalysisId}`,
    30_000,
  );
  if (!analysis.data) {
    return errorResponse(analysis.error, analysis.status);
  }
  if (analysis.data.schema_version !== "2.0.0") {
    return errorResponse(
      "Canonical report dataset preview requires an AnalysisResult v2 report.",
      409,
    );
  }

  const report = await getApi<AnalysisReportView>(
    `/api/v1/analyses/${encodedAnalysisId}/report`,
    120_000,
  );
  if (!report.data) {
    return errorResponse(report.error, report.status);
  }

  const dataset = canonicalReportDatasetFromReportView(
    analysis.data,
    report.data,
  );
  const integrityIssues = integrityChecker(dataset);
  if (integrityIssues.length > 0) {
    return errorResponse(
      `Canonical report dataset failed integrity checks: ${integrityIssues
        .slice(0, 5)
        .map((issue) => issue.code)
        .join(", ")}`,
      422,
    );
  }

  return {
    body: dataset,
    headers: CANONICAL_REPORT_DATASET_HEADERS,
  };
}
