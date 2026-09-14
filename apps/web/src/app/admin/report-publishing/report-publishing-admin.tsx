"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
type GrantStatusFilter = "active" | "revoked" | "all";

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

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function normalizeSearch(value: string | null | undefined): string {
  return (value ?? "").toLocaleLowerCase();
}

function grantSearchText(grant: CustomerReportGrant): string {
  return [
    grant.account_display_name,
    grant.account_slug,
    grant.workspace_display_name,
    grant.workspace_slug,
    grant.title,
    grant.category,
    grant.analysis_id,
    grant.access_id,
  ]
    .map(normalizeSearch)
    .join(" ");
}

function reportSearchText(report: GrantableCustomerReport): string {
  return [
    report.title,
    report.category,
    report.analysis_id,
    report.product_pack_id,
    report.product_pack_version,
  ]
    .map(normalizeSearch)
    .join(" ");
}

function matchesSearch(haystack: string, query: string): boolean {
  const terms = normalizeSearch(query).split(/\s+/).filter(Boolean);
  return terms.every((term) => haystack.includes(term));
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
  const [grantSearch, setGrantSearch] = useState("");
  const [reportSearch, setReportSearch] = useState("");
  const [grantStatusFilter, setGrantStatusFilter] =
    useState<GrantStatusFilter>("active");
  const [revokeCandidateAccessId, setRevokeCandidateAccessId] = useState<
    string | null
  >(null);
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
      setRevokeCandidateAccessId(null);
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

  const accessOverview = useMemo(() => {
    const grants = customerAccess?.grants ?? [];
    const activeGrants = grants.filter((grant) => grant.status === "active");
    return {
      activeGrants: activeGrants.length,
      revokedGrants: grants.filter((grant) => grant.status === "revoked")
        .length,
      accountCount: new Set(activeGrants.map((grant) => grant.account_id)).size,
      workspaceCount: new Set(
        activeGrants.map(
          (grant) =>
            `${grant.account_id}:${grant.workspace_id ?? "account-level"}`,
        ),
      ).size,
      readyReports: customerAccess?.grantable_reports.length ?? 0,
    };
  }, [customerAccess]);

  const accountSummaries = useMemo(() => {
    const summaries = new Map<
      string,
      {
        key: string;
        label: string;
        slug: string;
        active: number;
        revoked: number;
        workspaces: Set<string>;
        reports: Set<string>;
      }
    >();
    for (const grant of customerAccess?.grants ?? []) {
      const existing = summaries.get(grant.account_id) ?? {
        key: grant.account_id,
        label: grant.account_display_name,
        slug: grant.account_slug,
        active: 0,
        revoked: 0,
        workspaces: new Set<string>(),
        reports: new Set<string>(),
      };
      if (grant.status === "active") {
        existing.active += 1;
        existing.reports.add(grant.analysis_result_id);
        existing.workspaces.add(grant.workspace_id ?? "Account-level");
      }
      if (grant.status === "revoked") existing.revoked += 1;
      summaries.set(grant.account_id, existing);
    }
    return [...summaries.values()]
      .sort((left, right) => right.active - left.active)
      .slice(0, 4);
  }, [customerAccess]);

  const workspaceSummaries = useMemo(() => {
    const summaries = new Map<
      string,
      {
        key: string;
        accountLabel: string;
        workspaceLabel: string;
        active: number;
        revoked: number;
        reports: Set<string>;
      }
    >();
    for (const grant of customerAccess?.grants ?? []) {
      const key = `${grant.account_id}:${grant.workspace_id ?? "account-level"}`;
      const existing = summaries.get(key) ?? {
        key,
        accountLabel: grant.account_display_name,
        workspaceLabel: grant.workspace_display_name ?? "Account-level",
        active: 0,
        revoked: 0,
        reports: new Set<string>(),
      };
      if (grant.status === "active") {
        existing.active += 1;
        existing.reports.add(grant.analysis_result_id);
      }
      if (grant.status === "revoked") existing.revoked += 1;
      summaries.set(key, existing);
    }
    return [...summaries.values()]
      .sort((left, right) => right.active - left.active)
      .slice(0, 6);
  }, [customerAccess]);

  const filteredGrants = useMemo(() => {
    return (customerAccess?.grants ?? []).filter((grant) => {
      const statusMatches =
        grantStatusFilter === "all" || grant.status === grantStatusFilter;
      return (
        statusMatches && matchesSearch(grantSearchText(grant), grantSearch)
      );
    });
  }, [customerAccess, grantSearch, grantStatusFilter]);

  const filteredGrantableReports = useMemo(() => {
    return (customerAccess?.grantable_reports ?? []).filter((report) =>
      matchesSearch(reportSearchText(report), reportSearch),
    );
  }, [customerAccess, reportSearch]);

  const selectedGrantableReport = useMemo(() => {
    return customerAccess?.grantable_reports.find(
      (report) => report.analysis_result_id === grantAnalysisResultId,
    );
  }, [customerAccess, grantAnalysisResultId]);

  const grantableReportOptions = useMemo(() => {
    if (
      selectedGrantableReport &&
      !filteredGrantableReports.some(
        (report) =>
          report.analysis_result_id ===
          selectedGrantableReport.analysis_result_id,
      )
    ) {
      return [selectedGrantableReport, ...filteredGrantableReports];
    }
    return filteredGrantableReports;
  }, [filteredGrantableReports, selectedGrantableReport]);

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
        <div className={styles.accessMetricGrid} aria-label="Access overview">
          <article>
            <span>Active grants</span>
            <strong>{accessOverview.activeGrants.toLocaleString()}</strong>
            <p>Reports currently visible to customer users.</p>
          </article>
          <article>
            <span>Revoked grants</span>
            <strong>{accessOverview.revokedGrants.toLocaleString()}</strong>
            <p>Access history preserved for audit review.</p>
          </article>
          <article>
            <span>Accounts with access</span>
            <strong>{accessOverview.accountCount.toLocaleString()}</strong>
            <p>Customer accounts represented in the grant ledger.</p>
          </article>
          <article>
            <span>Workspaces in scope</span>
            <strong>{accessOverview.workspaceCount.toLocaleString()}</strong>
            <p>Active account-level or workspace-specific scopes.</p>
          </article>
          <article>
            <span>Ready reports</span>
            <strong>{accessOverview.readyReports.toLocaleString()}</strong>
            <p>Eligible reports that can be granted safely.</p>
          </article>
        </div>
        <div className={styles.accessSummaryGrid}>
          <section aria-label="Customer accounts with report access">
            <div className={styles.subsectionHeader}>
              <h3>Accounts</h3>
              <span>{accountSummaries.length} shown</span>
            </div>
            <div className={styles.summaryCards}>
              {accountSummaries.length ? (
                accountSummaries.map((account) => (
                  <article
                    className={styles.summaryCard}
                    key={account.key}
                    title={`${account.label} has ${account.active} active report grants`}
                  >
                    <strong>{account.label}</strong>
                    <span>{account.slug}</span>
                    <p>
                      {account.active} active · {account.revoked} revoked ·{" "}
                      {account.workspaces.size} workspace scopes
                    </p>
                  </article>
                ))
              ) : (
                <p className={styles.muted}>No customer grants yet.</p>
              )}
            </div>
          </section>
          <section aria-label="Customer workspaces with report access">
            <div className={styles.subsectionHeader}>
              <h3>Workspace scopes</h3>
              <span>{workspaceSummaries.length} shown</span>
            </div>
            <div className={styles.summaryCards}>
              {workspaceSummaries.length ? (
                workspaceSummaries.map((workspace) => (
                  <article
                    className={styles.summaryCard}
                    key={workspace.key}
                    title={`${workspace.workspaceLabel} has ${workspace.active} active report grants`}
                  >
                    <strong>{workspace.workspaceLabel}</strong>
                    <span>{workspace.accountLabel}</span>
                    <p>
                      {workspace.active} active · {workspace.revoked} revoked ·{" "}
                      {workspace.reports.size} reports
                    </p>
                  </article>
                ))
              ) : (
                <p className={styles.muted}>No workspace scopes yet.</p>
              )}
            </div>
          </section>
        </div>
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
            <span>Find ready report</span>
            <input
              onChange={(event) => setReportSearch(event.target.value)}
              placeholder="Search category, title, pack, analysis"
              title="Filter the ready reports available in the report picker."
              value={reportSearch}
            />
          </label>
          <label>
            <span>Ready report</span>
            <select
              disabled={!customerAccess?.grantable_reports.length}
              onChange={(event) => setGrantAnalysisResultId(event.target.value)}
              required
              value={grantAnalysisResultId}
              title="Only ready, non-archived reports are eligible."
            >
              {grantableReportOptions.length ? (
                grantableReportOptions.map((report) => (
                  <option
                    key={report.analysis_result_id}
                    value={report.analysis_result_id}
                  >
                    {report.title} · {report.category ?? "Uncategorized"} ·{" "}
                    {report.analysis_id}
                  </option>
                ))
              ) : (
                <option value="">No ready reports match</option>
              )}
            </select>
          </label>
          <button
            className="button primary"
            disabled={busy || !grantAnalysisResultId}
            title="Grant the selected ready report to the account or workspace scope."
            type="submit"
          >
            {busy ? "Saving…" : "Grant access"}
          </button>
        </form>
        {customerAccess ? (
          <div className={styles.grantLedger}>
            <div className={styles.ledgerToolbar}>
              <label>
                <span>Find grants</span>
                <input
                  onChange={(event) => setGrantSearch(event.target.value)}
                  placeholder="Search account, workspace, report, category"
                  title="Filter the customer report grant ledger."
                  value={grantSearch}
                />
              </label>
              <div className={styles.segmentedControl} role="group">
                {(["active", "revoked", "all"] as const).map((statusFilter) => (
                  <button
                    aria-pressed={grantStatusFilter === statusFilter}
                    key={statusFilter}
                    onClick={() => setGrantStatusFilter(statusFilter)}
                    title={`Show ${statusFilter} customer report grants.`}
                    type="button"
                  >
                    {statusFilter}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.grantTableWrap}>
              <table className={styles.grantTable}>
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Workspace</th>
                    <th>Report</th>
                    <th>Status</th>
                    <th>Granted</th>
                    <th>Customer view</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredGrants.map((grant) => (
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
                        <span>
                          {grant.category ?? "Uncategorized"} ·{" "}
                          {grant.analysis_id}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`${styles.grantStatus} ${styles[grant.status] ?? ""}`}
                        >
                          {grant.status}
                        </span>
                      </td>
                      <td>{formatDateTime(grant.granted_at)}</td>
                      <td>
                        {grant.status === "active" ? (
                          <Link
                            className={styles.inlineLink}
                            href={`/customer/reports/${grant.access_id}`}
                            title="Open the customer-facing report page for this grant."
                          >
                            Open
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {grant.status === "active" ? (
                          <button
                            className="button secondary"
                            onClick={() => {
                              if (revokeCandidateAccessId !== grant.access_id) {
                                setRevokeCandidateAccessId(grant.access_id);
                                return;
                              }
                              void revokeCustomerReport(grant.access_id);
                            }}
                            title="Soft-revoke this report grant without deleting the audit row."
                            type="button"
                          >
                            {revokeCandidateAccessId === grant.access_id
                              ? "Confirm revoke"
                              : "Revoke"}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                  {!filteredGrants.length ? (
                    <tr>
                      <td colSpan={7}>
                        <div className={styles.tableEmpty}>
                          No report grants match the current filters.
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
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
