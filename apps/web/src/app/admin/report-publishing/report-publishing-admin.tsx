"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";

import styles from "./report-publishing-admin.module.css";

interface AdminSession {
  authenticated: boolean;
  configured: boolean;
}
interface DecisionContext {
  profile_id: string;
  radius_miles: 1 | 3 | 5;
  competitor_id: string;
  competitor: string;
  evidence_state:
    "scored" | "local_evidence_limited" | "no_selected_basis_relationship";
  certified_identity_products: number;
  selected_price_basis_products: number;
  locally_scored_products: number;
  scored_product_locations: number;
}
interface AuditDocument {
  status?: string;
  error_count?: number;
  warning_count?: number;
  price_architecture_document_count?: number;
  competitive_portfolio_document_count?: number;
  expected_context_count?: number;
  context_count?: number;
  context_state_counts?: {
    scored: number;
    local_evidence_limited: number;
    no_selected_basis_relationship: number;
  };
  contexts?: DecisionContext[];
}
interface PublishingJob {
  id: string;
  analysis_id: string;
  reporting_status: string;
  product_pack_id: string;
  product_pack_version: string;
  status: string;
  stage: string;
  progress_current: number;
  progress_total: number;
  attempt_count: number;
  max_attempts: number;
  last_error: string | null;
  audit_document: AuditDocument | null;
  created_at: string;
  updated_at: string;
}
interface PublishingSummary {
  active_reports: {
    active_total: number;
    active_ready: number;
    active_pending: number;
    active_blocked: number;
    latest_ready_at: string | null;
  };
  recent_job_counts: Record<string, number>;
  recent_jobs: Array<{
    id: string;
    analysis_id: string;
    product_pack_id: string;
    status: string;
    stage: string;
    progress_current: number;
    progress_total: number;
    last_error: string | null;
    updated_at: string;
  }>;
}
interface CustomerReportGrant {
  access_id: string;
  account_id: string;
  account_slug: string;
  account_display_name: string;
  workspace_id: string | null;
  workspace_slug: string | null;
  workspace_display_name: string | null;
  analysis_id: string;
  analysis_result_id: string;
  title: string;
  category: string | null;
  status: string;
  granted_at: string;
}
interface GrantableCustomerReport {
  analysis_id: string;
  analysis_result_id: string;
  title: string;
  category: string | null;
  product_pack_id: string | null;
  product_pack_version: string | null;
  created_at: string;
}
interface CustomerReportAccessSnapshot {
  schema_version: string;
  grants: CustomerReportGrant[];
  grantable_reports: GrantableCustomerReport[];
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const raw = await response.text();
  const body = raw
    ? (JSON.parse(raw) as T & { error?: string; detail?: string })
    : null;
  if (!response.ok)
    throw new Error(
      body?.error ?? body?.detail ?? `Request failed (${response.status})`,
    );
  return body as T;
}

function JobCard({
  job,
  retry,
}: Readonly<{ job: PublishingJob; retry: (id: string) => void }>) {
  const percent = job.progress_total
    ? Math.round((job.progress_current / job.progress_total) * 100)
    : 0;
  const audit = job.audit_document;
  return (
    <article className={styles.job}>
      <div className={styles.jobHeader}>
        <div>
          <h2>{job.analysis_id}</h2>
          <p>
            {job.product_pack_id} · Product Pack {job.product_pack_version}
          </p>
        </div>
        <span className={`${styles.status} ${styles[job.status] ?? ""}`}>
          {job.status.replaceAll("_", " ")}
        </span>
      </div>
      <div aria-label={`${percent}% complete`} className={styles.progress}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className={styles.meta}>
        <span>
          <b>Stage:</b> {job.stage.replaceAll("_", " ")}
        </span>
        <span>
          <b>Progress:</b> {job.progress_current} of {job.progress_total || "—"}
        </span>
        <span>
          <b>Attempt:</b> {job.attempt_count} of {job.max_attempts}
        </span>
        <span>
          <b>Report:</b> {job.reporting_status}
        </span>
        <span>
          <b>Updated:</b> {new Date(job.updated_at).toLocaleString()}
        </span>
      </div>
      {job.last_error ? (
        <div className={styles.error}>{job.last_error}</div>
      ) : null}
      {audit ? (
        <details className={styles.audit}>
          <summary>Trust audit · {audit.status ?? "recorded"}</summary>
          <div className={styles.auditGrid}>
            <span>{audit.error_count ?? 0} blocking errors</span>
            <span>{audit.warning_count ?? 0} disclosed warnings</span>
            <span>
              {audit.price_architecture_document_count ?? 0} price matrices
            </span>
            <span>
              {audit.competitive_portfolio_document_count ?? 0} competitive
              views
            </span>
            {audit.expected_context_count !== undefined ? (
              <span>
                {audit.context_count ?? 0} of {audit.expected_context_count}{" "}
                retailer × basis × radius contexts
              </span>
            ) : null}
          </div>
          {audit.context_state_counts ? (
            <div className={styles.contextSummary}>
              <span>
                <b>{audit.context_state_counts.scored}</b> scored
              </span>
              <span>
                <b>{audit.context_state_counts.local_evidence_limited}</b>{" "}
                local-evidence limited
              </span>
              <span>
                <b>
                  {audit.context_state_counts.no_selected_basis_relationship}
                </b>{" "}
                without selected-basis relationships
              </span>
            </div>
          ) : null}
          {audit.contexts?.length ? (
            <div className={styles.contextTableWrap}>
              <table className={styles.contextTable}>
                <thead>
                  <tr>
                    <th>Retailer</th>
                    <th>Basis</th>
                    <th>Radius</th>
                    <th>Evidence state</th>
                    <th>Certified</th>
                    <th>Basis eligible</th>
                    <th>Locally scored</th>
                    <th>Scored locations</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.contexts.map((context) => (
                    <tr
                      key={`${context.profile_id}-${context.radius_miles}-${context.competitor_id}`}
                    >
                      <td>{context.competitor}</td>
                      <td>{context.profile_id.replaceAll("_", " ")}</td>
                      <td>{context.radius_miles} mi</td>
                      <td>
                        <span
                          className={`${styles.contextState} ${styles[context.evidence_state] ?? ""}`}
                        >
                          {context.evidence_state.replaceAll("_", " ")}
                        </span>
                      </td>
                      <td>{context.certified_identity_products}</td>
                      <td>{context.selected_price_basis_products}</td>
                      <td>{context.locally_scored_products}</td>
                      <td>{context.scored_product_locations}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </details>
      ) : null}
      {job.status === "blocked" || job.status === "retry_wait" ? (
        <button
          className="button secondary"
          onClick={() => retry(job.id)}
          type="button"
        >
          Retry safely
        </button>
      ) : null}
    </article>
  );
}

export function ReportPublishingAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [jobs, setJobs] = useState<PublishingJob[]>([]);
  const [summary, setSummary] = useState<PublishingSummary | null>(null);
  const [customerAccess, setCustomerAccess] =
    useState<CustomerReportAccessSnapshot | null>(null);
  const [grantAccount, setGrantAccount] = useState("ghretail");
  const [grantWorkspace, setGrantWorkspace] = useState("");
  const [grantAnalysisResultId, setGrantAnalysisResultId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadCustomerAccess = useCallback(async () => {
    const snapshot = await jsonRequest<CustomerReportAccessSnapshot>(
      "/api/admin/customer-report-access?limit=100",
    );
    setCustomerAccess(snapshot);
    setGrantAnalysisResultId((current) => {
      if (current) return current;
      return snapshot.grantable_reports[0]?.analysis_result_id ?? "";
    });
  }, []);

  const loadJobs = useCallback(async () => {
    const nextJobs = await jsonRequest<PublishingJob[]>(
      "/api/admin/report-publishing",
    );
    setJobs(nextJobs);
    try {
      setSummary(
        await jsonRequest<PublishingSummary>(
          "/api/admin/report-publishing/summary",
        ),
      );
    } catch {
      setSummary(null);
    }
  }, []);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then(async (value) => {
        setSession(value);
        if (value.authenticated) {
          await Promise.all([loadJobs(), loadCustomerAccess()]);
        }
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to check administrator access.",
        ),
      );
  }, [loadCustomerAccess, loadJobs]);

  useEffect(() => {
    if (!session?.authenticated) return;
    const timer = window.setInterval(() => void loadJobs(), 5_000);
    return () => window.clearInterval(timer);
  }, [loadJobs, session]);

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
      await Promise.all([loadJobs(), loadCustomerAccess()]);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to authenticate.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function retry(id: string) {
    setError(null);
    try {
      await jsonRequest(`/api/admin/report-publishing/${id}/retry`, {
        method: "POST",
        body: "{}",
      });
      await loadJobs();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to retry the job.",
      );
    }
  }

  async function grantCustomerReport(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await jsonRequest("/api/admin/customer-report-access", {
        method: "POST",
        body: JSON.stringify({
          account: grantAccount,
          workspace: grantWorkspace.trim() || null,
          analysis_result_id: grantAnalysisResultId,
        }),
      });
      await loadCustomerAccess();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to grant report access.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function revokeCustomerReport(accessId: string) {
    setError(null);
    try {
      await jsonRequest(
        `/api/admin/customer-report-access/${encodeURIComponent(accessId)}`,
        {
          method: "DELETE",
        },
      );
      await loadCustomerAccess();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to revoke report access.",
      );
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
          Pipeline Status contains release diagnostics, report readiness, and
          retry controls.
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
              {busy ? "Checking…" : "Open Pipeline Status"}
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
  return (
    <section className={styles.workspace}>
      <div className={styles.toolbar}>
        <p className={styles.summary}>
          This page tracks report pipeline jobs. Completed reports remain
          available in the report library even when no job is currently running.
        </p>
        <button
          className="button secondary"
          onClick={() => void loadJobs()}
          type="button"
        >
          Refresh
        </button>
      </div>
      {summary ? (
        <section className={styles.statusPanel} aria-label="Publishing status">
          <div>
            <span className="section-kicker">Active report library</span>
            <h2>{summary.active_reports.active_ready} ready reports</h2>
            <p>
              {summary.active_reports.active_pending} pending ·{" "}
              {summary.active_reports.active_blocked} blocked ·{" "}
              {summary.active_reports.active_total} active total
            </p>
          </div>
          <div className={styles.statusPanelMeta}>
            <span>
              <b>Latest ready:</b>{" "}
              {summary.active_reports.latest_ready_at
                ? new Date(
                    summary.active_reports.latest_ready_at,
                  ).toLocaleString()
                : "—"}
            </span>
            <span>
              <b>Recent jobs:</b>{" "}
              {Object.entries(summary.recent_job_counts).length
                ? Object.entries(summary.recent_job_counts)
                    .map(([status, count]) => `${count} ${status}`)
                    .join(" · ")
                : "none in the last 14 days"}
            </span>
          </div>
        </section>
      ) : null}
      <section
        className={styles.customerAccessPanel}
        aria-label="Customer report access"
      >
        <header>
          <div>
            <span className="section-kicker">Customer access</span>
            <h2>Grant reports to customer accounts</h2>
            <p>
              Only ready, non-archived reports can be granted. Customer report
              detail pages remain keyed by the grant ID, not by a global
              analysis URL.
            </p>
          </div>
          <button
            className="button secondary"
            onClick={() => void loadCustomerAccess()}
            type="button"
          >
            Refresh access
          </button>
        </header>
        <form className={styles.grantForm} onSubmit={grantCustomerReport}>
          <label>
            <span>Account slug or ID</span>
            <input
              onChange={(event) => setGrantAccount(event.target.value)}
              placeholder="ghretail"
              required
              value={grantAccount}
            />
          </label>
          <label>
            <span>Workspace slug or ID</span>
            <input
              onChange={(event) => setGrantWorkspace(event.target.value)}
              placeholder="Optional"
              value={grantWorkspace}
            />
          </label>
          <label>
            <span>Ready report</span>
            <select
              onChange={(event) => setGrantAnalysisResultId(event.target.value)}
              required
              value={grantAnalysisResultId}
            >
              {customerAccess?.grantable_reports.map((report) => (
                <option
                  key={report.analysis_result_id}
                  value={report.analysis_result_id}
                >
                  {report.title} · {report.analysis_id}
                </option>
              ))}
            </select>
          </label>
          <button className="button primary" disabled={busy} type="submit">
            {busy ? "Saving…" : "Grant access"}
          </button>
        </form>
        {customerAccess ? (
          <div className={styles.grantTableWrap}>
            <table className={styles.grantTable}>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Workspace</th>
                  <th>Report</th>
                  <th>Status</th>
                  <th>Granted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {customerAccess.grants.map((grant) => (
                  <tr key={grant.access_id}>
                    <td>
                      <strong>{grant.account_display_name}</strong>
                      <span>{grant.account_slug}</span>
                    </td>
                    <td>
                      {grant.workspace_display_name ?? "Account-level"}
                      <span>
                        {grant.workspace_slug ?? grant.workspace_id ?? "—"}
                      </span>
                    </td>
                    <td>
                      <strong>{grant.title}</strong>
                      <span>{grant.analysis_id}</span>
                    </td>
                    <td>{grant.status}</td>
                    <td>{new Date(grant.granted_at).toLocaleDateString()}</td>
                    <td>
                      {grant.status === "active" ? (
                        <button
                          className="button secondary"
                          onClick={() =>
                            void revokeCustomerReport(grant.access_id)
                          }
                          type="button"
                        >
                          Revoke
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="builder-loading">Loading customer access grants…</div>
        )}
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <div className={styles.jobs}>
        {jobs.length ? (
          jobs.map((job) => <JobCard job={job} key={job.id} retry={retry} />)
        ) : (
          <div className={styles.empty}>
            <h2>No report pipeline jobs are running</h2>
            <p>
              This does not mean there are no reports. Open the report library
              to view active reports; new reprocessing jobs will appear here
              while they are being prepared, audited, or retried.
            </p>
            <Link className="button secondary" href="/analyses">
              Open report library
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}
