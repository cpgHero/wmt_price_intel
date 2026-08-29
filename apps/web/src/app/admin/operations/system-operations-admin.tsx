"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import styles from "./system-operations.module.css";

interface AdminSession {
  authenticated: boolean;
  configured: boolean;
}
interface QueueState {
  label: string;
  state: "healthy" | "attention" | "blocked";
  queued: number;
  running: number;
  expired_leases: number;
  failures_24h: number;
}
interface OperationsSnapshot {
  generated_at: string;
  overall_state: "healthy" | "attention" | "blocked";
  release: {
    app_version: string;
    commit_sha: string;
    deployment_id: string;
    environment: string;
    service: string;
    database_migration: string;
    expected_migration_heads: string[];
    migration_matches: boolean;
    product_packs: Array<{ id: string; version: string; checksum: string }>;
    retailer_packs: Array<{ id: string; version: string; checksum: string }>;
  };
  queues: QueueState[];
  publication: {
    active_ready_reports: number;
    active_pending_reports: number;
    active_blocked_reports: number;
    open_validation_blockers: number;
    latest_ready_report_at: string | null;
    latest_successful_collection_at: string | null;
  };
  provider: {
    active_cooldowns: number;
    last_429_at: string | null;
    global_rps: number;
    global_rpm: number;
    maximum_attempts: number;
  };
  spend_30d: {
    search_credits: number;
    pdp_credits: number;
    metricscart_estimated_usd: number;
    ai_estimated_usd: number;
    ai_completed_tasks_without_cost: number;
    provider_billing_is_authoritative: boolean;
  };
  controls: {
    collection_provider: string;
    product_detail_enrichment_enabled: boolean;
    analysis_pipeline_enabled: boolean;
    matching_ai_review_enabled: boolean;
    ai_enabled: boolean;
    openai_matching_max_request_cost_usd: number;
  };
  recovery: {
    database_backup: {
      status: "current" | "stale" | "not_recorded";
      verified_at: string | null;
      maximum_age_hours: number;
    };
    restore_drill: {
      status: "current" | "stale" | "not_recorded";
      verified_at: string | null;
      maximum_age_days: number;
    };
    evidence_source: string;
  };
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const raw = await response.text();
  const body = raw
    ? (JSON.parse(raw) as T & { detail?: string; error?: string })
    : null;
  if (!response.ok) {
    throw new Error(
      body?.error ?? body?.detail ?? `Request failed (${response.status})`,
    );
  }
  return body as T;
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}

function shortCommit(value: string): string {
  return value === "unavailable" ? value : value.slice(0, 12);
}

function StatePill({ state }: Readonly<{ state: string }>) {
  return (
    <span className={`${styles.state} ${styles[state] ?? ""}`}>
      {state.replaceAll("_", " ")}
    </span>
  );
}

function OperationsWorkspace({
  snapshot,
}: Readonly<{ snapshot: OperationsSnapshot }>) {
  const queueBlocked = snapshot.queues.reduce(
    (total, queue) => total + queue.expired_leases,
    0,
  );
  return (
    <div className={styles.workspace}>
      <section className={styles.statusHero}>
        <div>
          <span className={styles.kicker}>
            Current control-plane assessment
          </span>
          <h2>
            {snapshot.overall_state === "healthy"
              ? "Production controls are healthy"
              : snapshot.overall_state === "blocked"
                ? "A release-blocking condition needs attention"
                : "Operational follow-up is required"}
          </h2>
          <p>
            Generated {formatTime(snapshot.generated_at)} from live Postgres
            control state and non-secret Railway runtime metadata.
          </p>
        </div>
        <StatePill state={snapshot.overall_state} />
      </section>

      <section className={styles.metrics} aria-label="Production summary">
        <article>
          <small>Ready reports</small>
          <strong>{snapshot.publication.active_ready_reports}</strong>
          <span>
            {snapshot.publication.active_pending_reports} pending activation
          </span>
        </article>
        <article>
          <small>Expired leases</small>
          <strong>{queueBlocked}</strong>
          <span>Across all durable queues</span>
        </article>
        <article>
          <small>Provider cooldowns</small>
          <strong>{snapshot.provider.active_cooldowns}</strong>
          <span>Last 429: {formatTime(snapshot.provider.last_429_at)}</span>
        </article>
        <article>
          <small>30-day provider estimate</small>
          <strong>
            ${snapshot.spend_30d.metricscart_estimated_usd.toFixed(2)}
          </strong>
          <span>Provider billing remains authoritative</span>
        </article>
        <article>
          <small>30-day AI estimate</small>
          <strong>${snapshot.spend_30d.ai_estimated_usd.toFixed(2)}</strong>
          <span>
            {snapshot.spend_30d.ai_completed_tasks_without_cost} tasks lack cost
            metadata
          </span>
        </article>
      </section>

      <section className={styles.panel}>
        <header>
          <div>
            <span className={styles.kicker}>Release identity</span>
            <h2>Deployed contract</h2>
          </div>
          <StatePill
            state={snapshot.release.migration_matches ? "healthy" : "blocked"}
          />
        </header>
        <dl className={styles.releaseGrid}>
          <div>
            <dt>Commit</dt>
            <dd>{shortCommit(snapshot.release.commit_sha)}</dd>
          </div>
          <div>
            <dt>Deployment</dt>
            <dd>{snapshot.release.deployment_id}</dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{snapshot.release.environment}</dd>
          </div>
          <div>
            <dt>API version</dt>
            <dd>{snapshot.release.app_version}</dd>
          </div>
          <div>
            <dt>Database migration</dt>
            <dd>{snapshot.release.database_migration}</dd>
          </div>
          <div>
            <dt>Expected head</dt>
            <dd>{snapshot.release.expected_migration_heads.join(", ")}</dd>
          </div>
        </dl>
        <details>
          <summary>
            View deployed Product Pack and Retailer Pack versions
          </summary>
          <div className={styles.packColumns}>
            <div>
              <h3>Product Packs</h3>
              {snapshot.release.product_packs.map((pack) => (
                <p key={`${pack.id}-${pack.version}`}>
                  <b>{pack.id}</b>
                  <span>
                    {pack.version} · {pack.checksum.slice(0, 10)}
                  </span>
                </p>
              ))}
            </div>
            <div>
              <h3>Retailer Packs</h3>
              {snapshot.release.retailer_packs.map((pack) => (
                <p key={`${pack.id}-${pack.version}`}>
                  <b>{pack.id}</b>
                  <span>
                    {pack.version} · {pack.checksum.slice(0, 10)}
                  </span>
                </p>
              ))}
            </div>
          </div>
        </details>
      </section>

      <section className={styles.panel}>
        <header>
          <div>
            <span className={styles.kicker}>Durable work</span>
            <h2>Queue health</h2>
          </div>
        </header>
        <div className={styles.queueTableWrap}>
          <table className={styles.queueTable}>
            <thead>
              <tr>
                <th>Queue</th>
                <th>State</th>
                <th>Waiting</th>
                <th>Running</th>
                <th>Expired leases</th>
                <th>Failures / review in 24h</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.queues.map((queue) => (
                <tr key={queue.label}>
                  <th>{queue.label}</th>
                  <td>
                    <StatePill state={queue.state} />
                  </td>
                  <td>{queue.queued}</td>
                  <td>{queue.running}</td>
                  <td>{queue.expired_leases}</td>
                  <td>{queue.failures_24h}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className={styles.twoColumn}>
        <section className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Spending controls</span>
              <h2>Provider and AI boundary</h2>
            </div>
          </header>
          <dl className={styles.compactList}>
            <div>
              <dt>Search credits / 30 days</dt>
              <dd>{snapshot.spend_30d.search_credits.toLocaleString()}</dd>
            </div>
            <div>
              <dt>PDP credits / 30 days</dt>
              <dd>{snapshot.spend_30d.pdp_credits.toLocaleString()}</dd>
            </div>
            <div>
              <dt>MetricsCart permit</dt>
              <dd>
                {snapshot.provider.global_rps}/sec ·{" "}
                {snapshot.provider.global_rpm}/min
              </dd>
            </div>
            <div>
              <dt>Matching AI request ceiling</dt>
              <dd>
                $
                {snapshot.controls.openai_matching_max_request_cost_usd.toFixed(
                  2,
                )}
              </dd>
            </div>
            <div>
              <dt>Collection provider</dt>
              <dd>{snapshot.controls.collection_provider}</dd>
            </div>
          </dl>
          <p className={styles.note}>
            Application estimates support reconciliation; MetricsCart and OpenAI
            billing portals remain the financial authority.
          </p>
        </section>
        <section className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Recovery evidence</span>
              <h2>Backup and restore readiness</h2>
            </div>
          </header>
          <div className={styles.recoveryRows}>
            <article>
              <div>
                <b>Database backup verification</b>
                <span>
                  {formatTime(snapshot.recovery.database_backup.verified_at)}
                </span>
              </div>
              <StatePill state={snapshot.recovery.database_backup.status} />
            </article>
            <article>
              <div>
                <b>Non-production restore drill</b>
                <span>
                  {formatTime(snapshot.recovery.restore_drill.verified_at)}
                </span>
              </div>
              <StatePill state={snapshot.recovery.restore_drill.status} />
            </article>
          </div>
          <p className={styles.note}>
            These timestamps are operator attestations, not a substitute for
            Railway backup evidence or a completed restore test.
          </p>
        </section>
      </div>
    </div>
  );
}

export function SystemOperationsAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [snapshot, setSnapshot] = useState<OperationsSnapshot | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadSnapshot = useCallback(async () => {
    setSnapshot(await jsonRequest<OperationsSnapshot>("/api/admin/operations"));
  }, []);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then(async (value) => {
        setSession(value);
        if (value.authenticated) await loadSnapshot();
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to check administrator access.",
        ),
      );
  }, [loadSnapshot]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await jsonRequest("/api/admin/session", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setSession({ authenticated: true, configured: true });
      setPassword("");
      await loadSnapshot();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to authenticate.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (session === null)
    return (
      <div className="builder-loading">Checking administrator access…</div>
    );
  if (!session.authenticated)
    return (
      <section className="admin-auth-card">
        <span className="section-kicker">Restricted operations</span>
        <h2>Administrator authentication required</h2>
        <p>
          System Operations exposes release identity, queue state, costs, and
          recovery evidence.
        </p>
        {session.configured ? (
          <form onSubmit={signIn}>
            <label>
              <span>Administrator password</span>
              <input
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <button className="button primary" disabled={busy} type="submit">
              {busy ? "Checking…" : "Open System Operations"}
            </button>
          </form>
        ) : (
          <div className="builder-alert warning">
            Administrator authentication is not configured.
          </div>
        )}
        {error ? <p className="form-error">{error}</p> : null}
      </section>
    );
  if (!snapshot)
    return (
      <div className="builder-loading">
        {error ?? "Loading live operational state…"}
      </div>
    );
  return (
    <>
      <div className={styles.toolbar}>
        <p>
          Refresh after deployments, queue interventions, backup verification,
          and incident recovery.
        </p>
        <button
          className="button secondary"
          onClick={() => void loadSnapshot()}
          type="button"
        >
          Refresh live state
        </button>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <OperationsWorkspace snapshot={snapshot} />
    </>
  );
}
