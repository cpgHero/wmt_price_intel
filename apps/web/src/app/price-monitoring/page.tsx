import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { summarizeAnalysis } from "@/lib/primary-app";
import { displayDate, displayLabel } from "@/lib/presentation";

export const dynamic = "force-dynamic";

export default async function PriceMonitoringPage() {
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

  return (
    <main className="price-monitoring-index">
      <header className="page-header compact price-index-header">
        <div>
          <p className="eyebrow">Price intelligence</p>
          <h1>Price Intelligence</h1>
        </div>
        <p>
          Track Search-listed package prices and observed product distribution
          by store. Service-area Search presence is reported separately. Select
          a study, then drill from country to state, city, product, and
          location.
        </p>
      </header>
      <section className="source-authority-banner">
        <span>Distribution definition</span>
        <strong>
          One distinct store where the product appears with price greater than
          $0 counts once
        </strong>
        <p>
          This is an observed distribution footprint, not an inventory or
          in-stock measure. It is never extrapolated to stores that were not
          observed. Service-area results are not counted as stores. PDP data
          adds product identity, imagery, and brand detail; Search supplies the
          listed price and store context.
        </p>
      </section>
      {analyses.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No observations yet"}
          title="No completed price-intelligence reports are available"
          message={
            response.error ??
            "Reprocess or complete a collection to create its positive-price store-distribution report."
          }
        />
      ) : (
        <section
          className="price-study-grid"
          aria-label="Price-monitoring studies"
        >
          {analyses.map((summary) => {
            const result = summary.analysis.result;
            const benchmark = String(
              "benchmark_retailer" in result
                ? result.benchmark_retailer
                : "walmart_us",
            );
            const competitorIds =
              "competitors" in result && Array.isArray(result.competitors)
                ? result.competitors.map(String)
                : [];
            return (
              <article className="price-study-card" key={summary.analysis.id}>
                <header>
                  <span className={`readiness-pill ${summary.quality.tier}`}>
                    {summary.quality.label}
                  </span>
                  <small>{displayDate(summary.observedAt)}</small>
                </header>
                <div>
                  <p className="section-kicker">Current snapshot</p>
                  <h2>{summary.category}</h2>
                  <p>
                    {summary.sourceRows?.toLocaleString() ?? "—"} source rows ·{" "}
                    {summary.sourceScope}
                  </p>
                </div>
                <div className="price-study-retailers">
                  {[benchmark, ...competitorIds].map((retailerId) => (
                    <Link
                      href={`/price-intelligence/${encodeURIComponent(summary.analysis.analysis_id)}?retailer=${encodeURIComponent(retailerId)}`}
                      key={retailerId}
                    >
                      <span>{displayLabel(retailerId)}</span>
                      <strong>Open retailer view →</strong>
                    </Link>
                  ))}
                </div>
              </article>
            );
          })}
        </section>
      )}
    </main>
  );
}
