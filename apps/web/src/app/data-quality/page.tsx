import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import {
  asObject,
  displayDate,
  displayLabel,
  displayValue,
} from "@/lib/presentation";

export const dynamic = "force-dynamic";

export default async function DataQualityPage() {
  const response = await getApi<AnalysisRecord[]>("/api/v1/analyses");
  const analyses = response.data ?? [];
  return (
    <main>
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Quality control</p>
          <h1>Data Quality</h1>
        </div>
        <p>
          Validation status and pipeline-authored QA flags across every
          immutable analysis.
        </p>
      </header>
      {analyses.length === 0 ? (
        <EmptyState
          eyebrow={response.error ? "API unavailable" : "No validations yet"}
          title="No quality records to review"
          message={
            response.error ??
            "Quality evidence appears here after an AnalysisResult is published."
          }
        />
      ) : (
        <section className="quality-grid">
          {analyses.map((analysis) => {
            const validation = asObject(analysis.result.validation);
            const quality = asObject(analysis.result.data_quality);
            return (
              <Link
                href={`/analyses/${encodeURIComponent(analysis.analysis_id)}`}
                className="quality-card"
                key={analysis.id}
              >
                <header>
                  <span className={`status-badge ${String(validation.status)}`}>
                    {displayLabel(String(validation.status ?? "unknown"))}
                  </span>
                  <small>{displayDate(analysis.created_at)}</small>
                </header>
                <h2>{displayLabel(analysis.product_pack_id)}</h2>
                <p>{analysis.analysis_id}</p>
                <dl>
                  {Object.entries(quality)
                    .slice(0, 4)
                    .map(([key, value]) => (
                      <div key={key}>
                        <dt>{displayLabel(key)}</dt>
                        <dd>{displayValue(value)}</dd>
                      </div>
                    ))}
                </dl>
              </Link>
            );
          })}
        </section>
      )}
    </main>
  );
}
