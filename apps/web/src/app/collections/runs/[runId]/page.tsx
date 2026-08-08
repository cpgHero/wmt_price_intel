import { notFound } from "next/navigation";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type RunMonitor } from "@/lib/api";
import { displayDate, displayDuration, displayLabel } from "@/lib/presentation";

import { RunActions } from "./run-actions";

export const dynamic = "force-dynamic";

export default async function RunMonitorPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const response = await getApi<RunMonitor>(
    `/api/v1/collection-runs/${encodeURIComponent(runId)}/monitor`,
  );
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
  const { run, usage, provider_state: provider } = monitor;
  const coolingDown = provider?.paused_until
    ? new Date(provider.paused_until) > new Date()
    : false;
  return (
    <main>
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Live collection monitor</p>
          <h1>Run {run.id.slice(0, 8)}</h1>
          <p className="workspace-meta">
            Created {displayDate(run.created_at)} · Definition{" "}
            {run.definition_version_id}
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
        </div>
      </header>
      {coolingDown && (
        <div className="cooldown-banner">
          <b>Shared 429 cooldown active</b>
          <span>
            All worker replicas are paused until{" "}
            {displayDate(provider!.paused_until!)}.
          </span>
        </div>
      )}
      <section className="metric-grid monitor-metrics">
        <div className="metric-card">
          <span>Successful pages</span>
          <strong>
            {usage.actual_success_pages} / {usage.estimated_pages}
          </strong>
        </div>
        <div className="metric-card">
          <span>Credits</span>
          <strong>
            {usage.actual_credits} / {usage.estimated_credits}
          </strong>
        </div>
        <div className="metric-card">
          <span>Retries</span>
          <strong>{monitor.retry_attempts}</strong>
        </div>
        <div className="metric-card">
          <span>Elapsed</span>
          <strong>{displayDuration(monitor.elapsed_seconds)}</strong>
        </div>
      </section>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Retailer progress</h2>
            <p>Exact task status counts and billable provider activity.</p>
          </div>
        </header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Retailer</th>
                <th>Pending</th>
                <th>Running</th>
                <th>Succeeded</th>
                <th>Failed</th>
                <th>Cancelled</th>
                <th>Attempts</th>
                <th>Retries</th>
                <th>Credits</th>
              </tr>
            </thead>
            <tbody>
              {monitor.retailers.map((row) => (
                <tr key={row.retailer_id}>
                  <td>
                    <b>{displayLabel(row.retailer_id)}</b>
                  </td>
                  <td>{row.pending_tasks}</td>
                  <td>{row.running_tasks}</td>
                  <td>{row.succeeded_tasks}</td>
                  <td>{row.failed_tasks}</td>
                  <td>{row.cancelled_tasks}</td>
                  <td>{row.attempts}</td>
                  <td>{row.retries}</td>
                  <td>{row.billable_credits}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="two-column">
        <section className="workspace-section">
          <header>
            <div>
              <h2>Global provider budget</h2>
              <p>Shared across every worker replica.</p>
            </div>
          </header>
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
            <div className="empty-inline">
              No provider permits have been issued yet.
            </div>
          )}
        </section>
        <section className="workspace-section">
          <header>
            <div>
              <h2>Failure classes</h2>
              <p>Terminal and retryable task outcomes.</p>
            </div>
          </header>
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
            <div className="empty-inline success">
              No task failures recorded.
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
