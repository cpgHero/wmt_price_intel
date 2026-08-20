import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { summarizeAnalysis, type QualityTier } from "@/lib/primary-app";
import { displayDate } from "@/lib/presentation";

export const dynamic = "force-dynamic";

interface QualitySearchParams {
  analysis?: string;
  q?: string;
  status?: string;
}

const tierOrder: Record<QualityTier, number> = {
  blocked: 0,
  review_required: 1,
  caveat: 2,
  ready: 3,
};

function formatRate(rate: number | null): string {
  if (rate === null) return "Rate unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: rate < 0.01 ? 2 : 1,
  }).format(rate);
}

export default async function DataQualityPage({
  searchParams,
}: {
  searchParams: Promise<QualitySearchParams>;
}) {
  const [{ analysis = "", q = "", status = "all" }, response] =
    await Promise.all([
      searchParams,
      getApi<AnalysisRecord[]>("/api/v1/analyses?limit=200"),
    ]);
  const summaries = (response.data ?? []).map(summarizeAnalysis);
  const normalizedQuery = q.trim().toLowerCase();
  const filtered = summaries
    .filter((summary) => {
      const searchText = [
        summary.category,
        summary.benchmarkRetailer,
        ...summary.competitors,
        summary.analysis.analysis_id,
      ]
        .join(" ")
        .toLowerCase();
      return (
        (!analysis || summary.analysis.analysis_id === analysis) &&
        (!normalizedQuery || searchText.includes(normalizedQuery)) &&
        (status === "all" || summary.quality.tier === status)
      );
    })
    .sort(
      (left, right) =>
        tierOrder[left.quality.tier] - tierOrder[right.quality.tier] ||
        Date.parse(right.analysis.created_at) -
          Date.parse(left.analysis.created_at),
    );
  const attentionCount = summaries.filter((summary) =>
    ["blocked", "review_required"].includes(summary.quality.tier),
  ).length;
  const caveatCount = summaries.filter(
    (summary) => summary.quality.tier === "caveat",
  ).length;
  const readyCount = summaries.filter(
    (summary) => summary.quality.tier === "ready",
  ).length;

  return (
    <main className="data-quality-page">
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Decision readiness</p>
          <h1>Data Quality</h1>
        </div>
        <p>
          Understand what is ready to use, what needs review, and how each
          source issue affects a competitive conclusion. Source evidence stays
          attached to its immutable analysis.
        </p>
      </header>

      {summaries.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No validations yet"}
          title="No quality records to review"
          message={
            response.error ??
            "Quality evidence appears here after an AnalysisResult is published."
          }
        />
      ) : (
        <>
          <section className="quality-summary" aria-label="Quality summary">
            <span
              className={attentionCount > 0 ? "needs-attention" : "healthy"}
            >
              <b>{attentionCount}</b> reports need attention
            </span>
            <span className={caveatCount > 0 ? "with-caveat" : "healthy"}>
              <b>{caveatCount}</b> ready with caveats
            </span>
            <span className="healthy">
              <b>{readyCount}</b> ready without recorded issues
            </span>
          </section>

          <form className="filter-bar quality-filter-bar" method="get">
            <label>
              <span>Search quality records</span>
              <input
                type="search"
                name="q"
                defaultValue={q}
                placeholder="Category, retailer, or report ID"
              />
            </label>
            <label>
              <span>Readiness</span>
              <select name="status" defaultValue={status}>
                <option value="all">All readiness levels</option>
                <option value="blocked">Blocked</option>
                <option value="review_required">Review required</option>
                <option value="caveat">Ready with caveats</option>
                <option value="ready">Ready</option>
              </select>
            </label>
            {analysis ? (
              <input type="hidden" name="analysis" value={analysis} />
            ) : null}
            <button className="button secondary" type="submit">
              Apply filters
            </button>
            {q || status !== "all" || analysis ? (
              <Link className="text-link" href="/data-quality">
                Clear
              </Link>
            ) : null}
          </form>

          <p className="result-count">
            Showing {filtered.length.toLocaleString()} of{" "}
            {summaries.length.toLocaleString()} quality records
          </p>

          {filtered.length === 0 ? (
            <div className="empty-inline">
              No quality records match these filters.
            </div>
          ) : (
            <section
              className="quality-queue"
              aria-label="Quality review queue"
            >
              {filtered.map((summary) => (
                <article
                  className={`quality-queue-card ${summary.quality.tier}`}
                  key={summary.analysis.id}
                >
                  <header>
                    <span className={`readiness-pill ${summary.quality.tier}`}>
                      {summary.quality.label}
                    </span>
                    <small>{displayDate(summary.analysis.created_at)}</small>
                  </header>
                  <div className="quality-queue-title">
                    <div>
                      <h2>{summary.category}</h2>
                      <p>
                        {summary.benchmarkRetailer} vs.{" "}
                        {summary.competitors.length > 0
                          ? summary.competitors.join(", ")
                          : "configured competitors"}
                      </p>
                    </div>
                    <span className="readiness-pill">
                      Report {summary.analysis.analysis_id}
                    </span>
                  </div>
                  <p className="quality-impact-summary">
                    {summary.quality.description}
                  </p>

                  {summary.quality.issues.length > 0 ? (
                    <div className="quality-issue-list">
                      {summary.quality.issues.map((issue) => (
                        <div
                          className={`quality-issue-row ${issue.severity}`}
                          key={issue.key}
                        >
                          <div>
                            <strong>{issue.label}</strong>
                            <p>{issue.impact}</p>
                          </div>
                          <span>
                            <b>{issue.count.toLocaleString()}</b>
                            <small>{formatRate(issue.rate)}</small>
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="quality-clear-state">
                      No source issue is recorded for this analysis.
                    </div>
                  )}

                  <footer className="quality-source-context">
                    <span>Observed {displayDate(summary.observedAt)}</span>
                    <span>
                      {summary.sourceRows
                        ? `${summary.sourceRows.toLocaleString()} source rows evaluated`
                        : summary.sourceScope}
                    </span>
                  </footer>
                  <details className="audit-disclosure">
                    <summary>Audit details</summary>
                    <code>{summary.analysis.analysis_id}</code>
                    <span>
                      Product Pack v{summary.analysis.product_pack_version}
                    </span>
                    <span>
                      Checksum {summary.analysis.checksum.slice(0, 16)}…
                    </span>
                  </details>
                </article>
              ))}
            </section>
          )}
        </>
      )}
    </main>
  );
}
