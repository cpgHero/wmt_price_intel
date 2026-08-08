import { DataTable } from "@/app/components/data-table";
import {
  getApi,
  type AlertDefinitionRecord,
  type AlertEventRecord,
  type EmailDeliveryRecord,
  type JsonObject,
  type ScheduleRecord,
} from "@/lib/api";
import { asObject, displayDate, displayLabel } from "@/lib/presentation";

export const dynamic = "force-dynamic";

function conditionSummary(alert: AlertDefinitionRecord): string {
  const condition = asObject(alert.config.condition);
  const change = condition.change_mode
    ? ` (${displayLabel(String(condition.change_mode))})`
    : "";
  return `${String(condition.operator ?? "unknown")} ${String(condition.threshold ?? "—")}${change}`;
}

export default async function AutomationPage() {
  const [scheduleResponse, alertResponse, eventResponse, deliveryResponse] =
    await Promise.all([
      getApi<ScheduleRecord[]>("/api/v1/collection-schedules"),
      getApi<AlertDefinitionRecord[]>("/api/v1/alert-definitions"),
      getApi<AlertEventRecord[]>("/api/v1/alert-events?limit=50"),
      getApi<EmailDeliveryRecord[]>("/api/v1/email-deliveries?limit=50"),
    ]);
  const schedules = scheduleResponse.data ?? [];
  const alerts = alertResponse.data ?? [];
  const events = eventResponse.data ?? [];
  const deliveries = deliveryResponse.data ?? [];
  const error =
    scheduleResponse.error ??
    alertResponse.error ??
    eventResponse.error ??
    deliveryResponse.error;

  const scheduleRows: JsonObject[] = schedules.map((schedule) => ({
    definition: schedule.definition_key,
    cadence: schedule.cron_expression,
    timezone: schedule.timezone,
    enabled: schedule.enabled,
    next_run: displayDate(schedule.next_run_at),
    last_run_id: schedule.last_collection_run_id,
    last_error: schedule.last_error,
  }));
  const alertRows: JsonObject[] = alerts.map((alert) => ({
    alert: alert.name,
    stable_key: alert.stable_key,
    version: alert.version,
    active: alert.active,
    condition: conditionSummary(alert),
    published: displayDate(alert.created_at),
  }));
  const eventRows: JsonObject[] = events.map((event) => ({
    alert: event.alert_key,
    analysis: event.analysis_id,
    baseline: event.baseline_analysis_id,
    status: event.status,
    current: event.current_value,
    baseline_value: event.baseline_value,
    change: event.change_value,
    evidence: event.evidence,
    evaluated: displayDate(event.created_at),
  }));
  const deliveryRows: JsonObject[] = deliveries.map((delivery) => ({
    type: delivery.delivery_type,
    analysis: delivery.analysis_id,
    recipients: delivery.recipients,
    subject: delivery.subject,
    status: delivery.status,
    attempts: `${delivery.attempt_count}/${delivery.max_attempts}`,
    evidence: delivery.evidence,
    last_error: delivery.last_error,
    sent: delivery.sent_at ? displayDate(delivery.sent_at) : null,
  }));

  return (
    <main className="analysis-page">
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Scheduled intelligence</p>
          <h1>Automation</h1>
        </div>
        <p>
          Durable schedules, versioned alert rules, evidence-backed events, and
          retryable email delivery—all coordinated through Postgres.
        </p>
      </header>

      {error ? <p className="empty-inline">{error}</p> : null}

      <section className="metric-grid automation-metrics">
        <div className="metric-card">
          <span>Active schedules</span>
          <strong>
            {schedules.filter((schedule) => schedule.enabled).length}
          </strong>
        </div>
        <div className="metric-card">
          <span>Active alerts</span>
          <strong>{alerts.filter((alert) => alert.active).length}</strong>
        </div>
        <div className="metric-card">
          <span>Triggered events</span>
          <strong>
            {events.filter((event) => event.status === "triggered").length}
          </strong>
        </div>
        <div className="metric-card">
          <span>Pending deliveries</span>
          <strong>
            {
              deliveries.filter((delivery) => delivery.status === "pending")
                .length
            }
          </strong>
        </div>
      </section>

      <section className="workspace-section">
        <header>
          <div>
            <h2>Collection schedules</h2>
            <p>Cron definitions and their next idempotent scheduling slot.</p>
          </div>
        </header>
        <DataTable
          rows={scheduleRows}
          emptyMessage="No scheduled collections are active."
        />
      </section>

      <section className="workspace-section">
        <header>
          <div>
            <h2>Alert definitions</h2>
            <p>
              Versioned rules evaluated only against validated AnalysisResult
              metrics.
            </p>
          </div>
        </header>
        <DataTable
          rows={alertRows}
          emptyMessage="No alert definitions have been published."
        />
      </section>

      <section className="workspace-section">
        <header>
          <div>
            <h2>Alert events</h2>
            <p>
              Current, baseline, change, and immutable JSON evidence references.
            </p>
          </div>
        </header>
        <DataTable
          rows={eventRows}
          emptyMessage="No alert evaluations have been recorded."
        />
      </section>

      <section className="workspace-section">
        <header>
          <div>
            <h2>Email delivery</h2>
            <p>
              Leased, idempotent delivery attempts with evidence and retry
              state.
            </p>
          </div>
        </header>
        <DataTable
          rows={deliveryRows}
          emptyMessage="No email deliveries have been queued."
        />
      </section>
    </main>
  );
}
