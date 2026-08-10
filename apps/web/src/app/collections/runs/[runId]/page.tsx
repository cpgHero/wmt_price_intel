import Link from "next/link";
import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/app/components/breadcrumbs";
import { EmptyState } from "@/app/components/empty-state";
import {
  getApi,
  type AnalysisRecord,
  type CollectionDefinitionRecord,
  type CollectionTask,
  type RunMonitor,
} from "@/lib/api";
import { definitionForRun } from "@/lib/primary-app";
import { displayDate, displayDuration, displayLabel } from "@/lib/presentation";

import { RunActions } from "./run-actions";
import { RunAutoRefresh } from "./run-auto-refresh";

export const dynamic = "force-dynamic";

export default async function RunMonitorPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const [response, analysisResponse, definitionResponse, failureResponse] =
    await Promise.all([
      getApi<RunMonitor>(
        `/api/v1/collection-runs/${encodeURIComponent(runId)}/monitor`,
      ),
      getApi<AnalysisRecord>(
        `/api/v1/collection-runs/${encodeURIComponent(runId)}/analysis`,
      ),
      getApi<CollectionDefinitionRecord[]>("/api/v1/collection-definitions"),
      getApi<CollectionTask[]>(
        `/api/v1/collection-runs/${encodeURIComponent(runId)}/tasks?status=failed&limit=2000`,
      ),
    ]);
  if (response.status === 404) notFound();
  if (!response.data)
    return (
      <main>
        <EmptyState
          eyebrow="Monitor unavailable"
          title="The collection run could not be loaded"
          message={response.error ?? "Try again when the API is available."}
        />
      </main>
    );
  const monitor = response.data;
  const analysis = analysisResponse.data;
  const definitions = definitionResponse.data ?? [];
  const failedTasks = failureResponse.data ?? [];
  const { run, usage, provider_state: provider } = monitor;
  const definition = definitionForRun(run, definitions);
  const terminal = [
    "succeeded",
    "completed_with_warnings",
    "failed",
    "cancelled",
  ].includes(run.status);
  const coolingDown = provider?.paused_until
    ? new Date(provider.paused_until) > new Date()
    : false;
  const finishedTasks =
    usage.succeeded_tasks + usage.failed_tasks + usage.cancelled_tasks;
  const totalTasks = finishedTasks + usage.pending_tasks + usage.running_tasks;
  const progress =
    totalTasks > 0 ? Math.round((finishedTasks / totalTasks) * 100) : 0;
  const title = definition?.definition.name ?? "Collection run";
  return (
    <main>
      <RunAutoRefresh active={!terminal || (terminal && !analysis)} />
      <Breadcrumbs
        items={[
          { label: "Collections", href: "/collections" },
          { label: title },
        ]}
      />
      <header className="workspace-header run-monitor-header">
        <div>
          <p className="eyebrow">Collection monitor</p>
          <h1>{title}</h1>
          <p className="workspace-meta">
            {definition
              ? `${displayLabel(definition.productPackId)} · ${definition.benchmarkRetailer} vs. ${definition.retailers.filter((retailer) => retailer !== definition.benchmarkRetailer).join(", ") || "configured competitors"}`
              : "Stored collection definition"}
          </p>
          <p className="workspace-meta">
            Started {displayDate(run.created_at)} ·{" "}
            {displayLabel(run.trigger_type)} run
          </p>
        </div>
        <div className="workspace-status">
          <span className={`status-badge ${run.status}`}>
            {displayLabel(run.status)}
          </span>
          <RunActions
            runId={run.id}
            cancellable={!run.completed_at && !run.cancel_requested_at}
          />
          {analysis && (
            <Link
              className="button primary"
              href={`/analyses/${encodeURIComponent(analysis.analysis_id)}`}
            >
              Open report
            </Link>
          )}
        </div>
      </header>

      {!terminal ? (
        <section className="run-progress" aria-label={`${progress}% complete`}>
          <div>
            <strong>Collection progress</strong>
            <span>{progress}% complete</span>
          </div>
          <div className="run-progress-track">
            <span style={{ width: `${progress}%` }} />
          </div>
        </section>
      ) : null}

      {coolingDown && (
        <div className="cooldown-banner">
          <b>Provider cooldown active</b>
          <span>
            Collection workers are safely paused until{" "}
            {displayDate(provider!.paused_until!)}.
          </span>
        </div>
      )}
      {run.availability_gate_status !== "skipped" && (
        <div
          className={`gate-banner ${run.availability_gate_status}`}
          data-status={run.availability_gate_status}
        >
          <b>
            ALDI availability check:{" "}
            {displayLabel(run.availability_gate_status)}
          </b>
          <span>
            This safeguard checks a small location sample before the remaining
            billable ALDI work begins.
          </span>
        </div>
      )}
      {terminal &&
        !analysis &&
        run.status !== "failed" &&
        run.status !== "cancelled" && (
          <div className="analysis-pending-banner">
            <b>Collection complete · analysis queued</b>
            <span>
              This page refreshes while normalization and Product Pack analytics
              run.
            </span>
          </div>
        )}

      {run.trigger_type === "historical_import" && totalTasks === 0 ? (
        <section className="historical-run-context">
          <div>
            <span className="section-kicker">Historical source import</span>
            <strong>Provider task metrics do not apply to this run</strong>
            <p>
              This analysis was created from supplied source artifacts rather
              than live MetricsCart collection tasks, so pages, credits,
              retries, and elapsed provider time are intentionally omitted.
            </p>
          </div>
          {analysis ? (
            <Link
              className="button secondary"
              href={`/analyses/${encodeURIComponent(analysis.analysis_id)}`}
            >
              Review imported analysis
            </Link>
          ) : null}
        </section>
      ) : (
        <section className="metric-grid monitor-metrics">
          <div className="metric-card">
            <span>Successful pages</span>
            <strong>
              {usage.actual_success_pages.toLocaleString()} /{" "}
              {usage.estimated_pages.toLocaleString()}
            </strong>
          </div>
          <div className="metric-card">
            <span>Credits used</span>
            <strong>
              {usage.actual_credits.toLocaleString()} /{" "}
              {usage.estimated_credits.toLocaleString()}
            </strong>
          </div>
          <div className="metric-card">
            <span>Retries</span>
            <strong>{monitor.retry_attempts.toLocaleString()}</strong>
          </div>
          <div className="metric-card">
            <span>Elapsed</span>
            <strong>{displayDuration(monitor.elapsed_seconds)}</strong>
          </div>
        </section>
      )}

      <section className="workspace-section retailer-progress-section">
        <header>
          <div>
            <span className="section-kicker">Retailer progress</span>
            <h2>Collection status by retailer</h2>
            <p>
              Expand a retailer to review failures and the exact ZIP/store
              context currently available for investigation.
            </p>
          </div>
        </header>
        {monitor.retailers.length === 0 ? (
          <div className="empty-inline">
            {run.trigger_type === "historical_import"
              ? "Retailer task progress is not recorded for historical imports. The report preserves source-level retailer coverage and evidence."
              : "No retailer tasks have been created for this run yet."}
          </div>
        ) : (
          <div className="retailer-progress-list">
            {monitor.retailers.map((row) => {
              const retailerFailures = failedTasks.filter(
                (task) => task.retailer_id === row.retailer_id,
              );
              const retailerTotal =
                row.pending_tasks +
                row.running_tasks +
                row.succeeded_tasks +
                row.failed_tasks +
                row.cancelled_tasks;
              return (
                <details
                  key={row.retailer_id}
                  className="retailer-progress-card"
                >
                  <summary>
                    <span>
                      <strong>{displayLabel(row.retailer_id)}</strong>
                      <small>
                        {row.succeeded_tasks.toLocaleString()} of{" "}
                        {retailerTotal.toLocaleString()} tasks succeeded
                      </small>
                    </span>
                    <dl>
                      <div>
                        <dt>Failed</dt>
                        <dd>{row.failed_tasks.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>Retries</dt>
                        <dd>{row.retries.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>Credits</dt>
                        <dd>{row.billable_credits.toLocaleString()}</dd>
                      </div>
                    </dl>
                  </summary>
                  {retailerFailures.length > 0 ? (
                    <div className="task-failure-list">
                      {retailerFailures.slice(0, 100).map((task) => (
                        <article key={task.id}>
                          <div>
                            <strong>ZIP {task.zipcode}</strong>
                            <span>
                              {task.store_number
                                ? `Store ${task.store_number}`
                                : "ZIP-level request"}{" "}
                              · Page {task.page_number}
                            </span>
                          </div>
                          <div>
                            <span>
                              {displayLabel(
                                task.failure_class ?? "request failed",
                              )}
                            </span>
                            <small>
                              {task.http_status
                                ? `HTTP ${task.http_status}`
                                : "No HTTP response"}{" "}
                              · {task.attempt_count}/{task.max_attempts}{" "}
                              attempts
                            </small>
                          </div>
                        </article>
                      ))}
                      {retailerFailures.length > 100 ? (
                        <p>
                          Showing 100 of{" "}
                          {retailerFailures.length.toLocaleString()} failed
                          tasks.
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <div className="empty-inline success">
                      No failed tasks are recorded for this retailer.
                    </div>
                  )}
                </details>
              );
            })}
          </div>
        )}
      </section>

      <details className="technical-diagnostics">
        <summary>Technical diagnostics and immutable identifiers</summary>
        <div className="two-column">
          <section>
            <h2>Provider safeguards</h2>
            {provider ? (
              <dl className="object-grid">
                <div>
                  <dt>Provider</dt>
                  <dd>{displayLabel(provider.provider)}</dd>
                </div>
                <div>
                  <dt>Current second</dt>
                  <dd>
                    {provider.second_count} / {monitor.configured_global_rps}
                  </dd>
                </div>
                <div>
                  <dt>Current minute</dt>
                  <dd>
                    {provider.minute_count} / {monitor.configured_global_rpm}
                  </dd>
                </div>
                <div>
                  <dt>Last 429</dt>
                  <dd>
                    {provider.last_429_at
                      ? displayDate(provider.last_429_at)
                      : "None"}
                  </dd>
                </div>
              </dl>
            ) : (
              <p>No provider permits have been issued yet.</p>
            )}
          </section>
          <section>
            <h2>Failure classes</h2>
            {Object.keys(monitor.failure_classes).length ? (
              <dl className="object-grid">
                {Object.entries(monitor.failure_classes).map(([key, count]) => (
                  <div key={key}>
                    <dt>{displayLabel(key)}</dt>
                    <dd>{count}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>No task failures recorded.</p>
            )}
          </section>
        </div>
        <dl className="identifier-grid">
          <div>
            <dt>Collection run ID</dt>
            <dd>
              <code>{run.id}</code>
            </dd>
          </div>
          <div>
            <dt>Definition version ID</dt>
            <dd>
              <code>{run.definition_version_id}</code>
            </dd>
          </div>
        </dl>
      </details>
    </main>
  );
}
