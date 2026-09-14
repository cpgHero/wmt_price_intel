"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import styles from "./report-detail.module.css";

interface CustomerReport {
  access_id: string;
  analysis_id: string;
  analysis_result_id: string;
  category: string | null;
  checksum: string;
  collection_run_id: string | null;
  created_at: string;
  granted_at: string;
  product_pack_id: string | null;
  product_pack_version: string | null;
  reporting_status: string;
  retailer_count: number | null;
  schema_version: string;
  title: string;
}

interface AnalysisEnvelope {
  analysis_id?: string;
  checksum?: string;
  collection_run_id?: string;
  created_at?: string;
  product_pack_id?: string;
  product_pack_version?: string;
  reporting_status?: string;
  result?: unknown;
  schema_version?: string;
  status?: string;
}

interface CustomerReportDetailResponse {
  analysis: AnalysisEnvelope;
  report: CustomerReport;
  schema_version: string;
  scope: {
    account_id: string | null;
    workspace_id: string | null;
  };
}

type LoadState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { message: string; status: "error" }
  | { data: CustomerReportDetailResponse; status: "ready" };

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function label(value: string | null | undefined): string {
  if (!value) return "Not available";
  return value
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}

function metricValue(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return "Recorded";
}

function metricLabel(row: JsonRecord, index: number): string {
  for (const key of ["label", "name", "title", "metric", "id"]) {
    const value = row[key];
    if (typeof value === "string" && value.trim()) return label(value);
  }
  return `Metric ${index + 1}`;
}

function metricDisplayValue(row: JsonRecord): string {
  for (const key of ["display_value", "formatted_value", "value", "count"]) {
    if (key in row) return metricValue(row[key]);
  }
  return "Recorded";
}

export function CustomerReportDetail({
  accessId,
}: Readonly<{ accessId: string }>) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function loadReport() {
      try {
        const response = await fetch(
          `/api/customer/reports/${encodeURIComponent(accessId)}`,
          {
            cache: "no-store",
            credentials: "include",
            headers: { accept: "application/json" },
          },
        );
        if (cancelled) return;
        if (response.status === 401 || response.status === 403) {
          setState({ status: "anonymous" });
          return;
        }
        const payload = (await response.json()) as
          CustomerReportDetailResponse | { detail?: string; error?: string };
        if (!response.ok || !("report" in payload)) {
          setState({
            status: "error",
            message:
              "detail" in payload && typeof payload.detail === "string"
                ? payload.detail
                : "The granted report could not be loaded.",
          });
          return;
        }
        setState({ status: "ready", data: payload });
      } catch {
        if (!cancelled) {
          setState({
            status: "error",
            message: "The granted report could not be loaded.",
          });
        }
      }
    }
    void loadReport();
    return () => {
      cancelled = true;
    };
  }, [accessId]);

  const reportDocument =
    state.status === "ready" ? state.data.analysis.result : null;
  const sections = useMemo(() => {
    if (!isRecord(reportDocument)) return [];
    return asArray(reportDocument.sections).filter(isRecord).slice(0, 12);
  }, [reportDocument]);
  const topMetrics = useMemo(() => {
    if (!isRecord(reportDocument)) return [];
    const directMetrics = asArray(reportDocument.metrics).filter(isRecord);
    if (directMetrics.length) return directMetrics.slice(0, 8);
    return sections
      .flatMap((section) => asArray(section.metrics).filter(isRecord))
      .slice(0, 8);
  }, [reportDocument, sections]);

  if (state.status === "loading") {
    return (
      <main className={styles.workspace}>
        <div className="builder-loading">Loading granted report…</div>
      </main>
    );
  }

  if (state.status === "anonymous") {
    return (
      <main className={styles.workspace}>
        <section className={styles.hero}>
          <p className="eyebrow">Customer report</p>
          <h1>Sign in to open this granted CPGHero report.</h1>
          <p>
            Report detail access is checked against your account, workspace,
            permissions, entitlements, and the active report grant.
          </p>
          <Link
            className="button primary"
            href={`/api/auth/login?return_to=/customer/reports/${encodeURIComponent(accessId)}`}
          >
            Sign in
          </Link>
        </section>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className={styles.workspace}>
        <section className={styles.hero}>
          <p className="eyebrow">Customer report</p>
          <h1>This report is not available.</h1>
          <p>{state.message}</p>
          <Link className="button secondary" href="/customer">
            Back to workspace
          </Link>
        </section>
      </main>
    );
  }

  const { analysis, report, scope } = state.data;

  return (
    <main className={styles.workspace}>
      <section className={styles.hero}>
        <div>
          <p className="eyebrow">Granted customer report</p>
          <h1>{report.title}</h1>
          <p>
            This read-only view was loaded through a customer-scoped report
            grant. Interactive analytics modules will be added here only after
            their downstream APIs are customer-gated.
          </p>
        </div>
        <div className={styles.identityCard}>
          <span>Access scope</span>
          <strong>{scope.account_id ?? "No account"}</strong>
          <small>{scope.workspace_id ?? "Account-level grant"}</small>
        </div>
      </section>

      <section className={styles.grid} aria-label="Report identity">
        <article>
          <span>Category</span>
          <strong>{report.category ?? "Report"}</strong>
          <small>{label(report.product_pack_id)}</small>
        </article>
        <article>
          <span>Status</span>
          <strong>{label(report.reporting_status)}</strong>
          <small>Granted {formatDate(report.granted_at)}</small>
        </article>
        <article>
          <span>Retailer scope</span>
          <strong>
            {report.retailer_count === null
              ? "Recorded"
              : report.retailer_count.toLocaleString()}
          </strong>
          <small>Retailers represented in the source report</small>
        </article>
        <article>
          <span>Source checksum</span>
          <strong>{report.checksum.slice(0, 12)}…</strong>
          <small>{report.schema_version}</small>
        </article>
      </section>

      {topMetrics.length ? (
        <section className={styles.panel}>
          <header>
            <div>
              <span className="section-kicker">Report metrics</span>
              <h2>Top recorded measures</h2>
            </div>
          </header>
          <div className={styles.metricGrid}>
            {topMetrics.map((metric, index) => (
              <article key={`${metricLabel(metric, index)}-${index}`}>
                <span>{metricLabel(metric, index)}</span>
                <strong>{metricDisplayValue(metric)}</strong>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.panel}>
        <header>
          <div>
            <span className="section-kicker">Report sections</span>
            <h2>Available content</h2>
          </div>
          <Link className="button secondary" href="/customer">
            Back to workspace
          </Link>
        </header>
        {sections.length ? (
          <div className={styles.sectionList}>
            {sections.map((section, index) => (
              <article key={`${String(section.id ?? section.title ?? index)}`}>
                <div>
                  <span>
                    {String(section.kind ?? section.visualization ?? "Section")}
                  </span>
                  <strong>
                    {typeof section.title === "string"
                      ? section.title
                      : `Section ${index + 1}`}
                  </strong>
                  {typeof section.empty_state === "string" ? (
                    <small>{section.empty_state}</small>
                  ) : null}
                </div>
                <div>
                  <span>{asArray(section.metrics).length} metrics</span>
                  <span>{asArray(section.records).length} records</span>
                  <span>
                    {asArray(section.evidence_sets).length} evidence sets
                  </span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.emptyState}>
            <strong>
              No section inventory was recorded in this report payload.
            </strong>
            <p>
              The source report is still available as a granted immutable
              analysis result; customer-native section rendering will be added
              as each interactive module receives tenant-scoped APIs.
            </p>
          </div>
        )}
      </section>

      <section className={styles.panel}>
        <header>
          <div>
            <span className="section-kicker">Source identity</span>
            <h2>Audit trail</h2>
          </div>
        </header>
        <dl className={styles.auditGrid}>
          <div>
            <dt>Analysis</dt>
            <dd>{analysis.analysis_id ?? report.analysis_id}</dd>
          </div>
          <div>
            <dt>Analysis result</dt>
            <dd>{report.analysis_result_id}</dd>
          </div>
          <div>
            <dt>Collection run</dt>
            <dd>
              {analysis.collection_run_id ??
                report.collection_run_id ??
                "Not recorded"}
            </dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{formatDate(report.created_at)}</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
