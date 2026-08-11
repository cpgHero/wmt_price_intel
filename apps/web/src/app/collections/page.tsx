import Link from "next/link";

import {
  getApi,
  type CollectionDefinitionRecord,
  type RunRecord,
} from "@/lib/api";
import { definitionForRun, summarizeDefinition } from "@/lib/primary-app";
import { displayDate, displayLabel } from "@/lib/presentation";

export const dynamic = "force-dynamic";

interface CollectionSearchParams {
  q?: string;
  status?: string;
}

export default async function CollectionsPage({
  searchParams,
}: {
  searchParams: Promise<CollectionSearchParams>;
}) {
  const [{ q = "", status = "all" }, definitionResponse, runResponse] =
    await Promise.all([
      searchParams,
      getApi<CollectionDefinitionRecord[]>("/api/v1/collection-definitions"),
      getApi<RunRecord[]>("/api/v1/collection-runs?limit=100"),
    ]);
  const definitions = definitionResponse.data ?? [];
  const definitionSummaries = definitions.map(summarizeDefinition);
  const normalizedQuery = q.trim().toLowerCase();
  const runs = (runResponse.data ?? []).filter((run) => {
    const definition = definitionForRun(run, definitions);
    const matchesQuery =
      normalizedQuery === "" ||
      definition?.definition.name.toLowerCase().includes(normalizedQuery) ||
      definition?.productPackId.toLowerCase().includes(normalizedQuery) ||
      run.id.toLowerCase().includes(normalizedQuery);
    return matchesQuery && (status === "all" || run.status === status);
  });
  const error = definitionResponse.error ?? runResponse.error;

  return (
    <main>
      <header className="page-header compact collection-page-header">
        <div>
          <p className="eyebrow">Collection workspace</p>
          <h1>Collections</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Revisit saved definitions, monitor every run, and approve the exact
            credit ceiling before new provider work starts.
          </p>
          <Link className="button primary" href="/collections/new">
            New collection
          </Link>
        </div>
      </header>

      {error ? (
        <p className="empty-inline">
          Some collection history is temporarily unavailable. The launch wizard
          remains disabled unless its required Product Pack catalog is
          available.
        </p>
      ) : null}

      <section className="workspace-section collection-history">
        <header>
          <div>
            <span className="section-kicker">Run history</span>
            <h2>Recent collection activity</h2>
            <p>
              Open any run to review retailer progress, billable credits,
              retries, and failure details.
            </p>
          </div>
        </header>
        <form className="filter-bar" method="get">
          <label>
            <span>Search collections</span>
            <input
              type="search"
              name="q"
              defaultValue={q}
              placeholder="Collection, category, or run ID"
            />
          </label>
          <label>
            <span>Status</span>
            <select name="status" defaultValue={status}>
              <option value="all">All statuses</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="succeeded">Succeeded</option>
              <option value="completed_with_warnings">
                Completed with warnings
              </option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <button className="button secondary" type="submit">
            Apply filters
          </button>
          {q || status !== "all" ? (
            <Link className="text-link" href="/collections">
              Clear
            </Link>
          ) : null}
        </form>
        {runs.length === 0 ? (
          <div className="empty-inline">
            {q || status !== "all"
              ? "No collection runs match these filters."
              : "No collection runs have been recorded yet."}
          </div>
        ) : (
          <div className="collection-run-list">
            {runs.map((run) => {
              const definition = definitionForRun(run, definitions);
              return (
                <article className="collection-run-row" key={run.id}>
                  <Link
                    href={`/collections/runs/${run.id}`}
                    aria-label={`Open ${definition?.definition.name ?? "collection run"}`}
                  />
                  <span className={`status-badge ${run.status}`}>
                    {displayLabel(run.status)}
                  </span>
                  <div className="collection-run-title">
                    <h3>{definition?.definition.name ?? "Collection run"}</h3>
                    <p>
                      {definition
                        ? `${displayLabel(definition.productPackId)} · ${definition.benchmarkRetailer} vs. ${definition.retailers.filter((retailer) => retailer !== definition.benchmarkRetailer).join(", ") || "configured competitors"}`
                        : `Definition version ${run.definition_version_id.slice(0, 8)}`}
                    </p>
                  </div>
                  <dl>
                    <div>
                      <dt>Started</dt>
                      <dd>{displayDate(run.created_at)}</dd>
                    </div>
                    <div>
                      <dt>Credits</dt>
                      <dd>
                        {run.actual_credits.toLocaleString()} /{" "}
                        {run.estimated_credits.toLocaleString()}
                      </dd>
                    </div>
                    <div>
                      <dt>Trigger</dt>
                      <dd>{displayLabel(run.trigger_type)}</dd>
                    </div>
                  </dl>
                  <b aria-hidden="true">→</b>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="workspace-section saved-definitions">
        <header>
          <div>
            <span className="section-kicker">Reusable scope</span>
            <h2>Saved collection definitions</h2>
            <p>
              Versioned definitions preserve the category, retailers, geography,
              schedule, and budget used by each run.
            </p>
          </div>
        </header>
        {definitionSummaries.length === 0 ? (
          <div className="empty-inline">
            No saved collection definitions are available yet.
          </div>
        ) : (
          <div className="definition-grid">
            {definitionSummaries.map((summary) => (
              <article className="definition-card" key={summary.definition.id}>
                <header>
                  <span
                    className={`status-badge ${summary.definition.active ? "succeeded" : "cancelled"}`}
                  >
                    {summary.definition.active ? "Active" : "Inactive"}
                  </span>
                  <small>Version {summary.definition.version}</small>
                </header>
                <h3>{summary.definition.name}</h3>
                <p>{displayLabel(summary.productPackId)}</p>
                <dl>
                  <div>
                    <dt>Retailers</dt>
                    <dd>{summary.retailers.join(", ")}</dd>
                  </div>
                  <div>
                    <dt>Geography</dt>
                    <dd>{summary.geography}</dd>
                  </div>
                  <div>
                    <dt>Schedule</dt>
                    <dd>{summary.schedule}</dd>
                  </div>
                </dl>
                <details className="audit-disclosure">
                  <summary>Audit details</summary>
                  <code>{summary.definition.stable_key}</code>
                  <span>Product Pack v{summary.productPackVersion ?? "—"}</span>
                </details>
                <Link
                  className="button secondary definition-edit-link"
                  href={`/collections/definitions/${encodeURIComponent(summary.definition.stable_key)}/edit`}
                >
                  Create new version
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="new-collection-section builder-invitation">
        <header className="section-heading">
          <div>
            <span className="section-kicker">Create</span>
            <h2>Launch a new collection</h2>
          </div>
          <p>
            Build a dynamic footprint by retailer locations, state, city, ZIP,
            or deterministic per-state sampling. Review it on a map and approve
            the exact Search ceiling before launch.
          </p>
        </header>
        <Link className="button primary" href="/collections/new">
          Open collection builder
        </Link>
      </section>
    </main>
  );
}
