"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import styles from "./report-publishing-admin.module.css";

interface AdminSession {
  authenticated: boolean;
  configured: boolean;
}
interface AuditDocument {
  status?: string;
  error_count?: number;
  warning_count?: number;
  price_architecture_document_count?: number;
  competitive_portfolio_document_count?: number;
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
          </div>
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
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadJobs = useCallback(async () => {
    setJobs(await jsonRequest<PublishingJob[]>("/api/admin/report-publishing"));
  }, []);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then(async (value) => {
        setSession(value);
        if (value.authenticated) await loadJobs();
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to check administrator access.",
        ),
      );
  }, [loadJobs]);

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
      await loadJobs();
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
          Report-publishing status contains release diagnostics and retry
          controls.
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
              {busy ? "Checking…" : "Open Report Publishing"}
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
          New reports remain pending until every read model is complete and the
          semantic audit passes.
        </p>
        <button
          className="button secondary"
          onClick={() => void loadJobs()}
          type="button"
        >
          Refresh
        </button>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <div className={styles.jobs}>
        {jobs.length ? (
          jobs.map((job) => <JobCard job={job} key={job.id} retry={retry} />)
        ) : (
          <div className={styles.empty}>
            <h2>No publishing jobs yet</h2>
            <p>
              The five certified baseline reports remain active. Future replays
              will appear here.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
