import { notFound } from "next/navigation";

import { EmptyState } from "@/app/components/empty-state";
import {
  getApi,
  type AnalysisRecord,
  type AnalysisReportView,
} from "@/lib/api";

import { AnalysisWorkspace } from "./workspace";

export const dynamic = "force-dynamic";

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  const response = await getApi<AnalysisRecord>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
    30_000,
  );
  if (response.status === 404) notFound();
  if (!response.data) {
    return (
      <main>
        <EmptyState
          eyebrow="Analysis unavailable"
          title="The result could not be loaded"
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
      />
    </main>
  );
}
