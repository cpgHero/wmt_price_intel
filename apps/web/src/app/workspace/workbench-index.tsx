import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { summarizeAnalysis } from "@/lib/primary-app";
import { displayDate } from "@/lib/presentation";

type WorkbenchKind = "matches" | "brands";

const copy = {
  matches: {
    eyebrow: "Product relationship governance",
    title: "Match Workbench",
    description:
      "Choose a category to review, confirm, reject, or manually create product relationships. Decisions remain analysis-scoped until you explicitly apply a revision to later collections.",
    action: "Open match review",
    path: "matches",
    availability: "Match review available",
  },
  brands: {
    eyebrow: "Brand governance",
    title: "Brand Workbench",
    description:
      "Choose a category to review private-label, regional, and national brand classifications. Search and PDP evidence remain attached to each governed decision.",
    action: "Open brand workbench",
    path: "brands",
    availability: "Brand review available",
  },
} as const;

export async function WorkbenchIndex({
  kind,
}: Readonly<{ kind: WorkbenchKind }>) {
  const response = await getApi<AnalysisRecord[]>("/api/v1/analyses?limit=200");
  const latestByProductPack = new Map<string, AnalysisRecord>();
  for (const analysis of response.data ?? []) {
    const current = latestByProductPack.get(analysis.product_pack_id);
    if (
      !current ||
      Date.parse(analysis.created_at) > Date.parse(current.created_at)
    ) {
      latestByProductPack.set(analysis.product_pack_id, analysis);
    }
  }
  const analyses = Array.from(latestByProductPack.values())
    .map(summarizeAnalysis)
    .sort((left, right) => left.category.localeCompare(right.category));
  const content = copy[kind];

  return (
    <main className="governance-workspace-index">
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Workspace · {content.eyebrow}</p>
          <h1>{content.title}</h1>
        </div>
        <p>{content.description}</p>
      </header>

      {analyses.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No governed analyses"}
          title={`No categories are available in ${content.title}`}
          message={
            response.error ??
            "Complete and publish an analysis before opening its governance workspace."
          }
        />
      ) : (
        <>
          <section
            className="workbench-index-guide"
            aria-label="Workspace guidance"
          >
            <div>
              <small>Cross-report entry point</small>
              <strong>
                {analyses.length.toLocaleString()} current categories
              </strong>
              <span>
                The most recent analysis for each Product Pack is shown below.
              </span>
            </div>
            <p>
              Workspace tools govern evidence and decisions. Competitive
              Intelligence remains the place to interpret price, assortment,
              geography, and executive reporting.
            </p>
          </section>

          <section className="workbench-index-grid" aria-label={content.title}>
            {analyses.map((summary) => (
              <article
                className="workbench-index-card"
                key={summary.analysis.analysis_id}
              >
                <header>
                  <span className={`readiness-pill ${summary.quality.tier}`}>
                    {summary.quality.label}
                  </span>
                  <small>{content.availability}</small>
                </header>
                <div>
                  <h2>{summary.category}</h2>
                  <p>
                    {summary.benchmarkRetailer} vs.{" "}
                    {summary.competitors.length
                      ? summary.competitors.join(", ")
                      : "configured competitors"}
                  </p>
                </div>
                <dl>
                  <div>
                    <dt>Latest analysis</dt>
                    <dd>{displayDate(summary.analysis.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Evidence scope</dt>
                    <dd>
                      {summary.sourceRows
                        ? `${summary.sourceRows.toLocaleString()} rows`
                        : summary.sourceScope}
                    </dd>
                  </div>
                  <div>
                    <dt>Product Pack</dt>
                    <dd>v{summary.analysis.product_pack_version}</dd>
                  </div>
                </dl>
                <Link
                  className="button primary"
                  href={`/workspace/${content.path}/${encodeURIComponent(summary.analysis.analysis_id)}`}
                >
                  {content.action}
                </Link>
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
