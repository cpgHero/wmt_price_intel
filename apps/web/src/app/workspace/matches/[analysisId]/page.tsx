import Link from "next/link";
import { notFound } from "next/navigation";

import { MatchReviewWorkbench } from "@/app/analyses/[analysisId]/match-review-workbench";
import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { summarizeAnalysis } from "@/lib/primary-app";

export const dynamic = "force-dynamic";

interface MatchSearchParams {
  competitor?: string;
  lens?: string;
  pair?: string;
}

export default async function MatchWorkbenchDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ analysisId: string }>;
  searchParams: Promise<MatchSearchParams>;
}) {
  const [{ analysisId }, query] = await Promise.all([params, searchParams]);
  const response = await getApi<AnalysisRecord>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
  );
  if (response.status === 404) notFound();
  if (!response.data) {
    return (
      <main>
        <EmptyState
          eyebrow="Match Workbench unavailable"
          title="The governed analysis could not be loaded"
          message={response.error ?? "Try again when the API is available."}
        />
      </main>
    );
  }
  const summary = summarizeAnalysis(response.data);
  return (
    <main className="governance-detail-page">
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Workspace · Match Workbench</p>
          <h1>{summary.category}</h1>
        </div>
        <div className="page-header-actions governance-detail-actions">
          <p>
            Govern product relationships for {summary.benchmarkRetailer} and its
            configured competitors. Changes remain staged until you request
            re-evaluation.
          </p>
          <Link
            className="button secondary"
            href={`/analyses/${encodeURIComponent(analysisId)}?tab=match-review`}
          >
            View match evidence in report
          </Link>
        </div>
      </header>
      <MatchReviewWorkbench
        analysisId={analysisId}
        scopedCompetitorId={query.competitor ?? null}
        scopedProfileId={query.lens ?? null}
        focusedRelationshipId={query.pair ?? null}
        routeBasePath={`/workspace/matches/${encodeURIComponent(analysisId)}`}
      />
    </main>
  );
}
