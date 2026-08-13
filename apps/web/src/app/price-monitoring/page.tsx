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
          Track the package prices each retailer presents at each observed store
          or service area. Select a study, then drill from country to state,
          city, product, and location.
        </p>
      </header>
      <section className="source-authority-banner">
        <span>Source authority</span>
        <strong>Search determines price and location</strong>
        <p>
          PDP data adds product identity, imagery, and brand detail. It never
          replaces the store-specific Search price.
        </p>
      </section>
      {analyses.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No observations yet"}
          title="No price-monitoring studies are available"
          message={
            response.error ??
            "Complete and analyze a collection to create a store-level price view."
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
