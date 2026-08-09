import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { displayDate, displayLabel } from "@/lib/presentation";

export const dynamic = "force-dynamic";

export default async function AnalysesPage() {
  const response = await getApi<AnalysisRecord[]>("/api/v1/analyses");
  const analyses = response.data ?? [];
  return (
    <main>
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Canonical results</p>
          <h1>Reports</h1>
        </div>
        <p>
          Immutable analytical records, evidence, and delivery
          artifacts—versioned by Product Pack and source run.
        </p>
      </header>
      {analyses.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No results yet"}
          title="No analyses to display"
          message={
            response.error ??
            "Publish a validated AnalysisResult from a completed collection run to populate this workspace."
          }
        />
      ) : (
        <section className="analysis-list">
          {analyses.map((analysis) => (
            <Link
              className="analysis-row"
              href={`/analyses/${encodeURIComponent(analysis.analysis_id)}`}
              key={analysis.id}
            >
              <span className={`status-badge ${analysis.status}`}>
                {displayLabel(analysis.status)}
              </span>
              <div>
                <h2>{displayLabel(analysis.product_pack_id)}</h2>
                <p>{analysis.analysis_id}</p>
              </div>
              <dl>
                <div>
                  <dt>Generated</dt>
                  <dd>{displayDate(analysis.created_at)}</dd>
                </div>
                <div>
                  <dt>Product Pack</dt>
                  <dd>v{analysis.product_pack_version}</dd>
                </div>
              </dl>
              <b aria-hidden="true">→</b>
            </Link>
          ))}
        </section>
      )}
    </main>
  );
}
