import Link from "next/link";

import {
  getApi,
  type AnalysisRecord,
  type CollectionDefinitionRecord,
  type RunRecord,
  type ScheduleRecord,
} from "@/lib/api";
import {
  definitionForRun,
  isActiveRun,
  isOperationalFailure,
  summarizeAnalysis,
} from "@/lib/primary-app";
import { displayDate, displayLabel } from "@/lib/presentation";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [analysisResponse, runResponse, definitionResponse, scheduleResponse] =
    await Promise.all([
      getApi<AnalysisRecord[]>("/api/v1/analyses?limit=20"),
      getApi<RunRecord[]>("/api/v1/collection-runs?limit=50"),
      getApi<CollectionDefinitionRecord[]>("/api/v1/collection-definitions"),
      getApi<ScheduleRecord[]>("/api/v1/collection-schedules"),
    ]);
  const analyses = (analysisResponse.data ?? []).map(summarizeAnalysis);
  const runs = runResponse.data ?? [];
  const definitions = definitionResponse.data ?? [];
  const schedules = scheduleResponse.data ?? [];
  const urgentAnalyses = analyses.filter(({ quality }) =>
    ["blocked", "review_required"].includes(quality.tier),
  );
  const failedRuns = runs.filter((run) =>
    isOperationalFailure(run, definitions),
  );
  const activeRuns = runs.filter(isActiveRun);
  const activeSchedules = schedules.filter((schedule) => schedule.enabled);
  const actualCredits = runs.reduce((sum, run) => sum + run.actual_credits, 0);
  const hasError =
    analysisResponse.error ??
    runResponse.error ??
    definitionResponse.error ??
    scheduleResponse.error;

  return (
    <main className="dashboard-page operational-dashboard">
      <header className="dashboard-welcome">
        <div>
          <p className="eyebrow">Decision-grade market visibility</p>
          <h1>Your competitive intelligence workspace.</h1>
          <p>
            Start new collections, review completed intelligence, and resolve
            the few issues that can change whether a result is ready to use.
          </p>
        </div>
        <div className="button-row">
          <Link className="button primary" href="/collections#new-collection">
            New collection
          </Link>
          <Link className="button secondary" href="/analyses">
            Browse reports
          </Link>
        </div>
      </header>

      {hasError ? (
        <p className="empty-inline">
          Some live workspace data is temporarily unavailable. Available
          sections remain safe to use.
        </p>
      ) : null}

      <section className="dashboard-grid dashboard-priority-grid">
        <article className="dashboard-panel priority-panel">
          <header>
            <div>
              <span className="section-kicker">Needs attention</span>
              <h2>Work that can change a decision</h2>
            </div>
            <Link href="/data-quality">Open quality queue →</Link>
          </header>
          {urgentAnalyses.length === 0 && failedRuns.length === 0 ? (
            <div className="positive-empty-state">
              <span aria-hidden="true">✓</span>
              <div>
                <strong>No urgent work is waiting</strong>
                <p>
                  New collection failures and decision-relevant quality issues
                  will appear here.
                </p>
              </div>
            </div>
          ) : (
            <div className="attention-list">
              {failedRuns.slice(0, 3).map((run) => {
                const definition = definitionForRun(run, definitions);
                return (
                  <Link href={`/collections/runs/${run.id}`} key={run.id}>
                    <span className="status-dot blocked" />
                    <div>
                      <strong>
                        {definition?.definition.name ?? "Collection run"}
                      </strong>
                      <small>
                        Collection failed · {displayDate(run.created_at)}
                      </small>
                    </div>
                    <b>Investigate →</b>
                  </Link>
                );
              })}
              {urgentAnalyses.slice(0, 4).map((summary) => (
                <Link
                  href={`/data-quality?analysis=${encodeURIComponent(summary.analysis.analysis_id)}`}
                  key={summary.analysis.id}
                >
                  <span className={`status-dot ${summary.quality.tier}`} />
                  <div>
                    <strong>{summary.category}</strong>
                    <small>
                      {summary.quality.label} ·{" "}
                      {summary.quality.totalIssues.toLocaleString()} recorded
                      quality flags
                    </small>
                  </div>
                  <b>Review →</b>
                </Link>
              ))}
            </div>
          )}
        </article>

        <aside className="dashboard-panel operations-snapshot">
          <span className="section-kicker">Operations snapshot</span>
          <dl>
            <div>
              <dt>Collections in progress</dt>
              <dd>{activeRuns.length || "None"}</dd>
            </div>
            <div>
              <dt>Upcoming schedules</dt>
              <dd>{activeSchedules.length || "None"}</dd>
            </div>
            <div>
              <dt>Credits in recent runs</dt>
              <dd>{actualCredits.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Published reports</dt>
              <dd>{analyses.length.toLocaleString()}</dd>
            </div>
          </dl>
          <div className="snapshot-actions">
            <Link href="/collections">Collection workspace →</Link>
            <Link href="/automation">Schedules & alerts →</Link>
          </div>
        </aside>
      </section>

      <section className="dashboard-panel latest-intelligence">
        <header>
          <div>
            <span className="section-kicker">Latest intelligence</span>
            <h2>Most recent completed reports</h2>
          </div>
          <Link href="/analyses">View all reports →</Link>
        </header>
        {analyses.length === 0 ? (
          <div className="empty-inline">
            Completed reports will appear here after a collection is analyzed.
          </div>
        ) : (
          <div className="latest-report-grid">
            {analyses.slice(0, 4).map((summary) => (
              <Link
                className="latest-report-card"
                href={`/analyses/${encodeURIComponent(summary.analysis.analysis_id)}`}
                key={summary.analysis.id}
              >
                <header>
                  <span className={`readiness-pill ${summary.quality.tier}`}>
                    {summary.quality.label}
                  </span>
                  <small>{displayDate(summary.observedAt)}</small>
                </header>
                <h3>{summary.category}</h3>
                <p>
                  {summary.benchmarkRetailer} vs.{" "}
                  {summary.competitors.length > 0
                    ? summary.competitors.join(", ")
                    : "configured competitors"}
                </p>
                <footer>
                  <span>{summary.sourceScope}</span>
                  <b>Open →</b>
                </footer>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="dashboard-grid dashboard-operations-grid">
        <article className="dashboard-panel compact-panel">
          <header>
            <div>
              <span className="section-kicker">Collection activity</span>
              <h2>
                {activeRuns.length > 0
                  ? "Currently running"
                  : "Recent collections"}
              </h2>
            </div>
          </header>
          <div className="compact-list">
            {(activeRuns.length > 0 ? activeRuns : runs)
              .slice(0, 4)
              .map((run) => {
                const definition = definitionForRun(run, definitions);
                return (
                  <Link href={`/collections/runs/${run.id}`} key={run.id}>
                    <div>
                      <strong>
                        {definition?.definition.name ?? "Collection run"}
                      </strong>
                      <small>
                        {displayLabel(run.trigger_type)} ·{" "}
                        {displayDate(run.created_at)}
                      </small>
                    </div>
                    <span className={`status-badge ${run.status}`}>
                      {displayLabel(run.status)}
                    </span>
                  </Link>
                );
              })}
            {runs.length === 0 ? (
              <p>No collection runs have been recorded yet.</p>
            ) : null}
          </div>
        </article>

        <article className="dashboard-panel compact-panel">
          <header>
            <div>
              <span className="section-kicker">Next scheduled work</span>
              <h2>Upcoming collections</h2>
            </div>
          </header>
          <div className="compact-list">
            {activeSchedules.slice(0, 4).map((schedule) => (
              <Link href="/automation" key={schedule.id}>
                <div>
                  <strong>{displayLabel(schedule.definition_key)}</strong>
                  <small>{displayDate(schedule.next_run_at)}</small>
                </div>
                <b>View →</b>
              </Link>
            ))}
            {activeSchedules.length === 0 ? (
              <p>No collection schedules are currently active.</p>
            ) : null}
          </div>
        </article>
      </section>
    </main>
  );
}
