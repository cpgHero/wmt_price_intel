import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { summarizeAnalysis } from "@/lib/primary-app";
import { displayDate } from "@/lib/presentation";

export const dynamic = "force-dynamic";

interface ReportSearchParams {
  q?: string;
  retailer?: string;
  readiness?: string;
  sort?: string;
}

export default async function AnalysesPage({
  searchParams,
}: {
  searchParams: Promise<ReportSearchParams>;
}) {
  const [
    { q = "", retailer = "all", readiness = "all", sort = "newest" },
    response,
  ] = await Promise.all([
    searchParams,
    getApi<AnalysisRecord[]>("/api/v1/analyses?limit=200"),
  ]);
  const summaries = (response.data ?? []).map(summarizeAnalysis);
  const retailerOptions = Array.from(
    new Set(
      summaries.flatMap((summary) => [
        summary.benchmarkRetailer,
        ...summary.competitors,
      ]),
    ),
  ).sort();
  const normalizedQuery = q.trim().toLowerCase();
  const analyses = summaries
    .filter((summary) => {
      const searchText = [
        summary.category,
        summary.benchmarkRetailer,
        ...summary.competitors,
        summary.analysis.analysis_id,
      ]
        .join(" ")
        .toLowerCase();
      const matchesQuery =
        normalizedQuery === "" || searchText.includes(normalizedQuery);
      const matchesRetailer =
        retailer === "all" ||
        summary.benchmarkRetailer === retailer ||
        summary.competitors.includes(retailer);
      const matchesReadiness =
        readiness === "all" || summary.quality.tier === readiness;
      return matchesQuery && matchesRetailer && matchesReadiness;
    })
    .sort((left, right) => {
      if (sort === "oldest") {
        return (
          Date.parse(left.analysis.created_at) -
          Date.parse(right.analysis.created_at)
        );
      }
      if (sort === "category")
        return left.category.localeCompare(right.category);
      return (
        Date.parse(right.analysis.created_at) -
        Date.parse(left.analysis.created_at)
      );
    });
  return (
    <main>
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Competitive intelligence library</p>
          <h1>Reports</h1>
        </div>
        <p>
          Find completed intelligence by category, retailer, or readiness.
          Immutable IDs and Product Pack versions remain available in each
          report&apos;s audit details.
        </p>
      </header>
      {summaries.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No results yet"}
          title="No reports to display"
          message={
            response.error ??
            "Publish a validated AnalysisResult from a completed collection run to populate this workspace."
          }
        />
      ) : (
        <>
          <form className="filter-bar report-filter-bar" method="get">
            <label>
              <span>Search reports</span>
              <input
                type="search"
                name="q"
                defaultValue={q}
                placeholder="Category, retailer, or report ID"
              />
            </label>
            <label>
              <span>Retailer</span>
              <select name="retailer" defaultValue={retailer}>
                <option value="all">All retailers</option>
                {retailerOptions.map((option) => (
                  <option value={option} key={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Readiness</span>
              <select name="readiness" defaultValue={readiness}>
                <option value="all">All readiness levels</option>
                <option value="blocked">Blocked</option>
                <option value="review_required">Review required</option>
                <option value="caveat">Ready with caveats</option>
                <option value="ready">Ready</option>
              </select>
            </label>
            <label>
              <span>Sort</span>
              <select name="sort" defaultValue={sort}>
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="category">Category A–Z</option>
              </select>
            </label>
            <button className="button secondary" type="submit">
              Apply filters
            </button>
            {q ||
            retailer !== "all" ||
            readiness !== "all" ||
            sort !== "newest" ? (
              <Link className="text-link" href="/analyses">
                Clear
              </Link>
            ) : null}
          </form>
          <p className="result-count">
            Showing {analyses.length.toLocaleString()} of{" "}
            {summaries.length.toLocaleString()} reports
          </p>
          {analyses.length === 0 ? (
            <div className="empty-inline">No reports match these filters.</div>
          ) : (
            <section className="report-library" aria-label="Reports">
              {analyses.map((summary) => (
                <article
                  className="report-library-card"
                  key={summary.analysis.id}
                >
                  <header>
                    <span className={`readiness-pill ${summary.quality.tier}`}>
                      {summary.quality.label}
                    </span>
                    <small>
                      Generated {displayDate(summary.analysis.created_at)}
                    </small>
                  </header>
                  <div className="report-library-title">
                    <div>
                      <h2>
                        <Link
                          href={`/analyses/${encodeURIComponent(summary.analysis.analysis_id)}`}
                        >
                          {summary.category}
                        </Link>
                      </h2>
                      <p>
                        {summary.benchmarkRetailer} vs.{" "}
                        {summary.competitors.length > 0
                          ? summary.competitors.join(", ")
                          : "configured competitors"}
                      </p>
                    </div>
                    <Link
                      className="button secondary"
                      href={`/analyses/${encodeURIComponent(summary.analysis.analysis_id)}`}
                    >
                      Open report
                    </Link>
                  </div>
                  <dl className="report-library-meta">
                    <div>
                      <dt>Observed</dt>
                      <dd>{displayDate(summary.observedAt)}</dd>
                    </div>
                    <div>
                      <dt>Source scope</dt>
                      <dd>
                        {summary.sourceRows
                          ? `${summary.sourceRows.toLocaleString()} rows`
                          : summary.sourceScope}
                      </dd>
                    </div>
                    <div>
                      <dt>Quality context</dt>
                      <dd>
                        {summary.quality.totalIssues > 0
                          ? `${summary.quality.totalIssues.toLocaleString()} affected source records`
                          : "No recorded quality issues"}
                      </dd>
                    </div>
                  </dl>
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
