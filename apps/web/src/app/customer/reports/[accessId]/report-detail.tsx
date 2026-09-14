"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CanonicalReportWorkspace } from "@/app/analyses/[analysisId]/canonical-report-workspace";
import type { AnalysisRecord, AnalysisReportView } from "@/lib/api";

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

interface CustomerReportViewResponse {
  analysis: AnalysisRecord;
  report: CustomerReport;
  schema_version: string;
  scope: {
    account_id: string | null;
    workspace_id: string | null;
  };
  view: AnalysisReportView;
}

type LoadState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { message: string; status: "error" }
  | { data: CustomerReportViewResponse; status: "ready" };

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
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
          `/api/customer/reports/${encodeURIComponent(accessId)}/report`,
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
          CustomerReportViewResponse | { detail?: string; error?: string };
        if (!response.ok || !("report" in payload) || !("view" in payload)) {
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
            Report access is checked against your account, workspace,
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

  const { report } = state.data;

  return (
    <main className={styles.workspace}>
      <div className={styles.customerReportToolbar}>
        <Link className="text-link" href="/customer">
          ← Back to customer workspace
        </Link>
        <span>
          Granted report · {report.category ?? "Product intelligence"}
        </span>
      </div>
      <section
        className={styles.reportContext}
        aria-label="Customer report access summary"
      >
        <article>
          <span>Report</span>
          <strong>{report.title}</strong>
          <p>{report.product_pack_version ?? report.schema_version}</p>
        </article>
        <article>
          <span>Status</span>
          <strong>{report.reporting_status.replaceAll("_", " ")}</strong>
          <p>Access granted {formatDate(report.granted_at)}</p>
        </article>
        <article>
          <span>Trust boundary</span>
          <strong>Grant-gated</strong>
          <p>Report data, evidence, and downloads use this access grant.</p>
        </article>
        <details className={styles.reportAudit}>
          <summary>Audit identifiers</summary>
          <dl>
            <div>
              <dt>Analysis</dt>
              <dd>{report.analysis_id}</dd>
            </div>
            <div>
              <dt>Result</dt>
              <dd>{report.analysis_result_id}</dd>
            </div>
            <div>
              <dt>Checksum</dt>
              <dd>{report.checksum}</dd>
            </div>
          </dl>
        </details>
      </section>
      <CanonicalReportWorkspace
        analysis={state.data.analysis}
        customerAccessId={accessId}
        reportView={state.data.view}
      />
    </main>
  );
}
