"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import styles from "./customer-workspace.module.css";

interface CustomerPrincipalResponse {
  schema_version: string;
  auth: {
    provider: string;
    source: string;
  };
  principal: {
    account_id: string | null;
    email: string;
    entitlements: string[];
    is_system_actor: boolean;
    permissions: string[];
    roles: string[];
    user_id: string;
    workspace_id: string | null;
  };
}

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

interface CustomerReportListResponse {
  reports: CustomerReport[];
  schema_version: string;
  scope: {
    account_id: string | null;
    workspace_id: string | null;
  };
}

type ReportLoadState =
  | { status: "loading" }
  | { data: CustomerReportListResponse; status: "ready" }
  | { message: string; status: "error" };

type LoadState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { message: string; status: "error" }
  | {
      data: CustomerPrincipalResponse;
      reports: ReportLoadState;
      status: "ready";
    };

function label(value: string): string {
  return value
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function Card({
  children,
  kicker,
  title,
}: Readonly<{
  children: React.ReactNode;
  kicker: string;
  title: string;
}>) {
  return (
    <article className={styles.card}>
      <span>{kicker}</span>
      <strong>{title}</strong>
      {children}
    </article>
  );
}

export function CustomerWorkspace() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function loadCustomerWorkspace() {
      try {
        const response = await fetch("/api/auth/me", {
          cache: "no-store",
          credentials: "include",
          headers: { accept: "application/json" },
        });
        if (cancelled) return;
        if (response.status === 401 || response.status === 403) {
          setState({ status: "anonymous" });
          return;
        }
        const payload = (await response.json()) as
          CustomerPrincipalResponse | { error?: string; detail?: string };
        if (!response.ok || !("principal" in payload)) {
          setState({
            status: "error",
            message:
              "detail" in payload && typeof payload.detail === "string"
                ? payload.detail
                : "The customer workspace is temporarily unavailable.",
          });
          return;
        }
        setState({
          status: "ready",
          data: payload,
          reports: { status: "loading" },
        });
        const reportsResponse = await fetch("/api/customer/reports?limit=25", {
          cache: "no-store",
          credentials: "include",
          headers: { accept: "application/json" },
        });
        if (cancelled) return;
        const reportPayload = (await reportsResponse.json()) as
          CustomerReportListResponse | { error?: string; detail?: string };
        setState({
          status: "ready",
          data: payload,
          reports:
            reportsResponse.ok && "reports" in reportPayload
              ? { status: "ready", data: reportPayload }
              : {
                  status: "error",
                  message:
                    "detail" in reportPayload &&
                    typeof reportPayload.detail === "string"
                      ? reportPayload.detail
                      : "Granted reports are temporarily unavailable.",
                },
        });
      } catch {
        if (!cancelled) {
          setState({
            status: "error",
            message: "The customer workspace is temporarily unavailable.",
          });
        }
      }
    }
    loadCustomerWorkspace();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <main className={styles.workspace}>
        <div className="builder-loading">Resolving your CPGHero account…</div>
      </main>
    );
  }

  if (state.status === "anonymous") {
    return (
      <main className={styles.workspace}>
        <section className={styles.hero}>
          <p className="eyebrow">Customer access</p>
          <h1>Sign in to open your CPGHero workspace.</h1>
          <p>
            Customer access is in a controlled canary. Sign in with an approved
            invitation email to validate account, workspace, role, and
            entitlement resolution.
          </p>
          <div className={styles.actions}>
            <Link
              className="button primary"
              href="/api/auth/login?return_to=/customer"
            >
              Sign in
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className={styles.workspace}>
        <section className={styles.hero}>
          <p className="eyebrow">Customer access</p>
          <h1>Customer workspace is not ready.</h1>
          <p>{state.message}</p>
          <div className={styles.actions}>
            <Link className="button secondary" href="/api/auth/logout">
              Clear session
            </Link>
          </div>
        </section>
      </main>
    );
  }

  const { principal } = state.data;
  const { reports } = state;
  const hasAnalytics = principal.permissions.includes("analytics.view");
  const hasExports = principal.permissions.includes("exports.download");
  const hasProjects = principal.permissions.includes("projects.create");
  const hasEntitlements = principal.entitlements.length > 0;

  return (
    <main className={styles.workspace}>
      <section className={styles.hero}>
        <div>
          <p className="eyebrow">Customer workspace</p>
          <h1>Welcome to CPGHero.</h1>
          <p>
            This page shows the account and role state resolved from your live
            CPGHero customer session. These are the values future tenant-scoped
            report and project routes will enforce.
          </p>
        </div>
        <div className={styles.identityCard}>
          <span>Signed in as</span>
          <strong>{principal.email}</strong>
          <small>{principal.roles.map(label).join(" · ")}</small>
        </div>
      </section>

      <section className={styles.grid} aria-label="Customer access summary">
        <Card kicker="Account" title={principal.account_id ?? "Not assigned"}>
          <p>
            Active account resolved from the authenticated customer identity.
          </p>
        </Card>
        <Card
          kicker="Workspace"
          title={principal.workspace_id ?? "Account-level access"}
        >
          <p>
            Active workspace selected for customer analytics and future project
            scoping.
          </p>
        </Card>
        <Card kicker="Roles" title={principal.roles.length.toString()}>
          <div className={styles.pillRow}>
            {principal.roles.map((role) => (
              <span key={role}>{label(role)}</span>
            ))}
          </div>
        </Card>
        <Card
          kicker="Configured entitlements"
          title={principal.entitlements.length.toString()}
        >
          {hasEntitlements ? (
            <div className={styles.pillRow}>
              {principal.entitlements.map((entitlement) => (
                <span key={entitlement}>{label(entitlement)}</span>
              ))}
            </div>
          ) : (
            <p>
              No paid product entitlements have been granted to this canary
              account yet.
            </p>
          )}
        </Card>
      </section>

      <section className={styles.panel}>
        <header>
          <div>
            <span className="section-kicker">What this account can do</span>
            <h2>Resolved permissions</h2>
          </div>
          <Link className="button secondary" href="/api/auth/logout">
            Sign out
          </Link>
        </header>
        <div className={styles.permissionGrid}>
          <article className={hasAnalytics ? styles.enabled : ""}>
            <strong>View analytics</strong>
            <span>{hasAnalytics ? "Enabled" : "Not enabled"}</span>
          </article>
          <article className={hasProjects ? styles.enabled : ""}>
            <strong>Create projects</strong>
            <span>{hasProjects ? "Enabled" : "Not enabled"}</span>
          </article>
          <article className={hasExports ? styles.enabled : ""}>
            <strong>Download exports</strong>
            <span>{hasExports ? "Enabled" : "Not enabled"}</span>
          </article>
        </div>
        <details className={styles.details}>
          <summary>Show full permission list</summary>
          <div className={styles.pillRow}>
            {principal.permissions.map((permission) => (
              <span key={permission}>{label(permission)}</span>
            ))}
          </div>
        </details>
      </section>

      <section className={styles.panel}>
        <header>
          <div>
            <span className="section-kicker">Granted report access</span>
            <h2>Your reports</h2>
          </div>
        </header>
        {reports.status === "loading" ? (
          <div className="builder-loading">Loading granted reports…</div>
        ) : reports.status === "error" ? (
          <div className={styles.emptyState}>
            <strong>Report access could not be loaded.</strong>
            <p>{reports.message}</p>
          </div>
        ) : reports.data.reports.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>No customer reports have been granted yet.</strong>
            <p>
              This is expected for a fresh canary account. Existing global
              internal reports are not shown here until a CPGHero administrator
              explicitly grants them to this account or workspace.
            </p>
          </div>
        ) : (
          <div className={styles.reportList}>
            {reports.data.reports.map((report) => (
              <article key={report.access_id}>
                <div>
                  <span>{report.category ?? "Report"}</span>
                  <strong>{report.title}</strong>
                  <small>
                    {report.product_pack_id
                      ? `${label(report.product_pack_id)} ${report.product_pack_version ?? ""}`
                      : report.schema_version}
                  </small>
                </div>
                <div className={styles.reportMeta}>
                  <span>{label(report.reporting_status)}</span>
                  <small>
                    Granted {new Date(report.granted_at).toLocaleDateString()}
                  </small>
                </div>
                <Link
                  className={styles.reportAction}
                  href={`/customer/reports/${encodeURIComponent(report.access_id)}`}
                >
                  Open report
                </Link>
              </article>
            ))}
          </div>
        )}
        <p className={styles.scopeNote}>
          Scope checked by the API: account{" "}
          <code>
            {reports.status === "ready"
              ? reports.data.scope.account_id
              : principal.account_id}
          </code>{" "}
          · workspace{" "}
          <code>
            {reports.status === "ready"
              ? (reports.data.scope.workspace_id ?? "account-level")
              : (principal.workspace_id ?? "account-level")}
          </code>
        </p>
      </section>
    </main>
  );
}
