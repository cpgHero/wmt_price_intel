import { notFound } from "next/navigation";

import { EmptyState } from "@/app/components/empty-state";
import {
  getApi,
  type AnalysisRecord,
  type AnalysisReportView,
} from "@/lib/api";
import {
  canonicalReportPreviewEnabled,
  type CanonicalReportPreviewSearchParams,
} from "@/lib/canonical-report-preview";

import { AnalysisWorkspace } from "./workspace";

export const dynamic = "force-dynamic";

export default async function AnalysisPage({
  params,
  searchParams,
}: {
  params: Promise<{ analysisId: string }>;
  searchParams: Promise<CanonicalReportPreviewSearchParams>;
}) {
  const [{ analysisId }, query] = await Promise.all([params, searchParams]);
  const response = await getApi<AnalysisRecord>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
    30_000,
  );
  if (response.status === 404) notFound();
  if (!response.data) {
    return (
      <main>
        <EmptyState
          eyebrow={
            response.status === 409
              ? "Report quarantined"
              : "Analysis unavailable"
          }
          title={
            response.status === 409
              ? "This report is not available for sharing"
              : "The result could not be loaded"
          }
          message={response.error ?? "Try again when the API is available."}
        />
      </main>
    );
  }
  const reportResponse =
    response.data.schema_version === "2.0.0"
      ? await getApi<AnalysisReportView>(
          `/api/v1/analyses/${encodeURIComponent(analysisId)}/report`,
          120_000,
        )
      : null;
  return (
    <main className="analysis-page">
      <AnalysisWorkspace
        analysis={response.data}
        reportView={reportResponse?.data ?? null}
        canonicalPreview={canonicalReportPreviewEnabled(query)}
      />
    </main>
  );
}
