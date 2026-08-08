import { notFound } from "next/navigation";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";

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
  return (
    <main className="analysis-page">
      <AnalysisWorkspace analysis={response.data} />
    </main>
  );
}
