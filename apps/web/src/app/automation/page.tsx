import Link from "next/link";

import {
  getApi,
  type AlertDefinitionRecord,
  type AlertEventRecord,
  type CollectionDefinitionRecord,
  type EmailDeliveryRecord,
  type ScheduleRecord,
} from "@/lib/api";
import {
  describeAlertCondition,
  isInternalAcceptanceRecord,
} from "@/lib/primary-app";
import { asObject, displayDate, displayLabel } from "@/lib/presentation";

export const dynamic = "force-dynamic";

function cadence(schedule: ScheduleRecord): string {
  const [minute, hour, day, month, weekday] =
    schedule.cron_expression.split(" ");
  if ([minute, hour, day, month, weekday].every((value) => value === "*")) {
    return "Every minute";
  }
  if (
    minute === "0" &&
    hour &&
    day === "*" &&
    month === "*" &&
    weekday === "*"
  ) {
    const numericHour = Number(hour);
    if (
      Number.isInteger(numericHour) &&
      numericHour >= 0 &&
      numericHour <= 23
    ) {
      const period = numericHour >= 12 ? "PM" : "AM";
      const shownHour = numericHour % 12 || 12;
      return `Daily at ${shownHour}:00 ${period}`;
    }
  }
  return "Custom schedule";
}

function alertScope(alert: AlertDefinitionRecord): string {
  const scope = asObject(alert.config.scope);
  const packs = Array.isArray(scope.product_pack_ids)
    ? scope.product_pack_ids.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  return packs.length > 0
    ? packs.map(displayLabel).join(", ")
    : "Configured reports";
}

export default async function AutomationPage() {
  const [
    scheduleResponse,
    alertResponse,
    eventResponse,
    deliveryResponse,
    definitionResponse,
  ] = await Promise.all([
    getApi<ScheduleRecord[]>("/api/v1/collection-schedules"),
    getApi<AlertDefinitionRecord[]>("/api/v1/alert-definitions"),
    getApi<AlertEventRecord[]>("/api/v1/alert-events?limit=100"),
    getApi<EmailDeliveryRecord[]>("/api/v1/email-deliveries?limit=100"),
    getApi<CollectionDefinitionRecord[]>("/api/v1/collection-definitions"),
  ]);
  const allSchedules = scheduleResponse.data ?? [];
  const allAlerts = alertResponse.data ?? [];
  const allEvents = eventResponse.data ?? [];
  const allDeliveries = deliveryResponse.data ?? [];
  const definitions = definitionResponse.data ?? [];
  const schedules = allSchedules.filter(
    (schedule) => !isInternalAcceptanceRecord(schedule.definition_key),
  );
  const alerts = allAlerts.filter(
    (alert) =>
      !isInternalAcceptanceRecord(alert.stable_key) &&
      !isInternalAcceptanceRecord(alert.name),
  );
  const events = allEvents.filter(
    (event) => !isInternalAcceptanceRecord(event.alert_key),
  );
  const deliveries = allDeliveries.filter(
    (delivery) =>
      !isInternalAcceptanceRecord(delivery.analysis_id) &&
      !isInternalAcceptanceRecord(delivery.subject),
  );
  const hiddenRecords =
    allSchedules.length -
    schedules.length +
    (allAlerts.length - alerts.length) +
    (allEvents.length - events.length) +
    (allDeliveries.length - deliveries.length);
  const definitionNames = new Map(
    definitions.map((definition) => [definition.stable_key, definition.name]),
  );
  const error =
    scheduleResponse.error ??
    alertResponse.error ??
    eventResponse.error ??
    deliveryResponse.error ??
    definitionResponse.error;

  return (
    <main className="automation-page">
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Scheduled intelligence</p>
          <h1>Schedules &amp; Alerts</h1>
        </div>
        <div className="page-header-actions">
          <p>
            See when intelligence will refresh, which conditions are being
            watched, and whether scheduled delivery is healthy.
          </p>
          <Link className="button secondary" href="/collections">
            Open collections
          </Link>
        </div>
      </header>

      {error ? <p className="empty-inline">{error}</p> : null}

      <section className="automation-summary" aria-label="Automation summary">
        <span>
          <b>{schedules.filter((schedule) => schedule.enabled).length}</b>{" "}
          active schedules
        </span>
        <span>
          <b>{alerts.filter((alert) => alert.active).length}</b> active alerts
        </span>
        <span>
          <b>{events.filter((event) => event.status === "triggered").length}</b>{" "}
          triggered events
        </span>
        <span>
          <b>
            {
              deliveries.filter((delivery) => delivery.status === "pending")
                .length
            }
          </b>{" "}
          pending deliveries
        </span>
      </section>

      <section className="workspace-section automation-workspace-section">
        <header>
          <div>
            <span className="section-kicker">Collection schedules</span>
            <h2>Upcoming intelligence refreshes</h2>
            <p>
              Each schedule reuses a versioned collection definition and its
              stored budget safeguards.
            </p>
          </div>
        </header>
        {schedules.length === 0 ? (
          <div className="empty-state-inline-action">
            <div>
              <strong>No user-facing schedules are active</strong>
              <p>
                Scheduled definitions will appear here with their next run,
                timezone, and latest outcome.
              </p>
            </div>
            <Link className="button secondary" href="/collections">
              Review definitions
            </Link>
          </div>
        ) : (
          <div className="automation-card-grid">
            {schedules.map((schedule) => (
              <article className="automation-card" key={schedule.id}>
                <header>
                  <span
                    className={`status-badge ${schedule.enabled ? "succeeded" : "cancelled"}`}
                  >
                    {schedule.enabled ? "Active" : "Paused"}
                  </span>
                  <small>{cadence(schedule)}</small>
                </header>
                <h3>
                  {definitionNames.get(schedule.definition_key) ??
                    displayLabel(schedule.definition_key)}
                </h3>
                <p>
                  Next run {displayDate(schedule.next_run_at)} ·{" "}
                  {schedule.timezone}
                </p>
                {schedule.last_error ? (
                  <div className="inline-warning">
                    Last scheduling error: {schedule.last_error}
                  </div>
                ) : null}
                <footer>
                  {schedule.last_collection_run_id ? (
                    <Link
                      href={`/collections/runs/${schedule.last_collection_run_id}`}
                    >
                      Open latest run →
                    </Link>
                  ) : (
                    <span>No run has been created yet.</span>
                  )}
                </footer>
                <details className="audit-disclosure">
                  <summary>Technical schedule</summary>
                  <code>{schedule.cron_expression}</code>
                  <span>{schedule.definition_key}</span>
                </details>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-section automation-workspace-section">
        <header>
          <div>
            <span className="section-kicker">Alert rules</span>
            <h2>Conditions being watched</h2>
            <p>
              Alerts evaluate stored deterministic metrics and never change a
              price, match, or report automatically.
            </p>
          </div>
        </header>
        {alerts.length === 0 ? (
          <div className="empty-inline">
            No user-facing alert rules have been published.
          </div>
        ) : (
          <div className="automation-card-grid">
            {alerts.map((alert) => (
              <article className="automation-card" key={alert.id}>
                <header>
                  <span
                    className={`status-badge ${alert.active ? "succeeded" : "cancelled"}`}
                  >
                    {alert.active ? "Active" : "Inactive"}
                  </span>
                  <small>Version {alert.version}</small>
                </header>
                <h3>{alert.name}</h3>
                <p>{describeAlertCondition(alert)}</p>
                <dl>
                  <div>
                    <dt>Scope</dt>
                    <dd>{alertScope(alert)}</dd>
                  </div>
                  <div>
                    <dt>Published</dt>
                    <dd>{displayDate(alert.created_at)}</dd>
                  </div>
                </dl>
                <details className="audit-disclosure">
                  <summary>Audit details</summary>
                  <code>{alert.stable_key}</code>
                  <span>Checksum {alert.checksum.slice(0, 16)}…</span>
                </details>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="dashboard-grid dashboard-operations-grid">
        <section className="dashboard-panel compact-panel">
          <header>
            <div>
              <span className="section-kicker">Alert activity</span>
              <h2>Recent evaluations</h2>
            </div>
          </header>
          <div className="compact-list">
            {events.slice(0, 10).map((event) => (
              <Link
                href={`/analyses/${encodeURIComponent(event.analysis_id)}`}
                key={event.id}
              >
                <div>
                  <strong>{displayLabel(event.alert_key)}</strong>
                  <small>
                    {displayDate(event.created_at)} · Current value{" "}
                    {String(event.current_value ?? "—")}
                  </small>
                </div>
                <span
                  className={`status-badge ${event.status === "triggered" ? "running" : "succeeded"}`}
                >
                  {displayLabel(event.status)}
                </span>
              </Link>
            ))}
            {events.length === 0 ? (
              <p>No alert activity is recorded yet.</p>
            ) : null}
          </div>
        </section>

        <section className="dashboard-panel compact-panel">
          <header>
            <div>
              <span className="section-kicker">Delivery health</span>
              <h2>Recent report and alert delivery</h2>
            </div>
          </header>
          <div className="compact-list">
            {deliveries.slice(0, 10).map((delivery) => (
              <article key={delivery.id}>
                <div>
                  <strong>{delivery.subject}</strong>
                  <small>
                    {delivery.recipients.length.toLocaleString()} recipient
                    {delivery.recipients.length === 1 ? "" : "s"} ·{" "}
                    {delivery.sent_at
                      ? displayDate(delivery.sent_at)
                      : displayDate(delivery.created_at)}
                  </small>
                </div>
                <span className={`status-badge ${delivery.status}`}>
                  {displayLabel(delivery.status)}
                </span>
              </article>
            ))}
            {deliveries.length === 0 ? (
              <p>No user-facing deliveries are recorded yet.</p>
            ) : null}
          </div>
        </section>
      </div>

      {hiddenRecords > 0 ? (
        <details className="technical-diagnostics internal-records-note">
          <summary>Internal acceptance records</summary>
          <p>
            {hiddenRecords.toLocaleString()} Phase 09 acceptance record
            {hiddenRecords === 1 ? " is" : "s are"} retained for audit but
            hidden from the business workspace.
          </p>
        </details>
      ) : null}
    </main>
  );
}
