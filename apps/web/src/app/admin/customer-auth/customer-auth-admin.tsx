"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import styles from "./customer-auth.module.css";

const DEFAULT_READINESS_EMAIL = "brian@cpghero.com";

type FoundationView = "overview" | "accounts" | "members" | "readiness";
type AccountTypeFilter = "customer" | "all";

interface AdminSession {
  authenticated: boolean;
  configured: boolean;
}

interface CustomerAuthReadiness {
  schema_version: string;
  customer_auth_provider: string;
  customer_login_enabled: boolean;
  canary: {
    enabled: boolean;
    configured: boolean;
    allowed_email_count: number;
    allowed_domain_count: number;
  };
  cutover_ready: boolean;
  blockers: string[];
  invitations: Array<{
    email: string;
    account_slug: string;
    account_display_name: string;
    workspace_slug: string | null;
    workspace_display_name: string | null;
    invitation_status: string;
    account_membership_status: string | null;
    workspace_membership_status: string | null;
    role_keys: string[];
    entitlement_keys: string[];
    has_external_user_mapping: boolean;
    has_external_organization_mapping: boolean;
    has_workos_invitation: boolean;
    accepted: boolean;
    prepared_at: string;
    updated_at: string;
  }>;
  recent_webhook_events: Array<{
    event_type: string;
    processing_status: string;
    email_snapshot: string | null;
    has_workos_user: boolean;
    has_workos_organization: boolean;
    has_workos_invitation: boolean;
    processed: boolean;
    received_at: string;
    processed_at: string | null;
  }>;
}

interface CustomerAccountFoundation {
  schema_version: string;
  summary: {
    accounts: number;
    customer_accounts: number;
    active_accounts: number;
    workspaces: number;
    active_workspaces: number;
    members: number;
    active_members: number;
    entitlements: number;
    active_entitlements: number;
    active_report_grants: number;
  };
  accounts: Array<{
    account_id: string;
    account_slug: string;
    account_display_name: string;
    account_type: string;
    account_status: string;
    workspace_count: number;
    member_count: number;
    active_member_count: number;
    entitlement_count: number;
    active_entitlement_count: number;
    active_report_grant_count: number;
    revoked_report_grant_count: number;
    has_identity_provider_organization_binding: boolean;
    created_at: string;
  }>;
  workspaces: Array<{
    workspace_id: string;
    account_id: string;
    account_slug: string;
    account_display_name: string;
    workspace_slug: string;
    workspace_display_name: string;
    workspace_status: string;
    active_member_count: number;
    active_report_grant_count: number;
    revoked_report_grant_count: number;
    created_at: string;
  }>;
  members: Array<{
    user_id: string;
    email: string;
    display_name: string | null;
    account_id: string;
    account_slug: string;
    account_display_name: string;
    account_membership_status: string;
    workspace_slug: string | null;
    workspace_display_name: string | null;
    workspace_membership_status: string | null;
    account_role_keys: string[];
    workspace_role_keys: string[];
    has_identity_provider_user_binding: boolean;
    created_at: string;
  }>;
  entitlements: Array<{
    account_id: string;
    account_slug: string;
    account_display_name: string;
    entitlement_key: string;
    entitlement_status: string;
    starts_at: string | null;
    expires_at: string | null;
    created_at: string;
  }>;
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

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function roleList(values: string[]): string {
  return values.length ? values.join(", ") : "No role recorded";
}

function readableStatus(value: string | null): string {
  return value ? value.replaceAll("_", " ") : "not recorded";
}

function StatusPill({
  active,
  trueLabel,
  falseLabel,
}: Readonly<{ active: boolean; trueLabel: string; falseLabel: string }>) {
  return (
    <span className={`${styles.pill} ${active ? styles.good : styles.warn}`}>
      {active ? trueLabel : falseLabel}
    </span>
  );
}

function FoundationTabs({
  activeView,
  onViewChange,
}: Readonly<{
  activeView: FoundationView;
  onViewChange: (view: FoundationView) => void;
}>) {
  const tabs: Array<{ label: string; value: FoundationView }> = [
    { label: "Overview", value: "overview" },
    { label: "Account directory", value: "accounts" },
    { label: "Users & roles", value: "members" },
    { label: "Login readiness", value: "readiness" },
  ];
  return (
    <nav aria-label="Accounts and access views" className={styles.tabs}>
      {tabs.map((tab) => (
        <button
          aria-pressed={activeView === tab.value}
          className={activeView === tab.value ? styles.activeTab : ""}
          key={tab.value}
          onClick={() => onViewChange(tab.value)}
          type="button"
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

function FoundationWorkspace({
  data,
  accountSearch,
  accountTypeFilter,
  selectedAccountId,
  view,
  onAccountSearchChange,
  onAccountTypeFilterChange,
  onRefresh,
  onSelectAccount,
}: Readonly<{
  data: CustomerAccountFoundation;
  accountSearch: string;
  accountTypeFilter: AccountTypeFilter;
  selectedAccountId: string | null;
  view: FoundationView;
  onAccountSearchChange: (value: string) => void;
  onAccountTypeFilterChange: (value: AccountTypeFilter) => void;
  onRefresh: () => void;
  onSelectAccount: (accountId: string | null) => void;
}>) {
  const visibleAccounts = useMemo(() => {
    const normalizedSearch = accountSearch.trim().toLowerCase();
    return data.accounts.filter((account) => {
      const isVisibleType =
        accountTypeFilter === "all" || account.account_type === "customer";
      if (!isVisibleType) return false;
      if (!normalizedSearch) return true;

      const accountText = [
        account.account_display_name,
        account.account_slug,
        account.account_type,
        account.account_status,
      ]
        .join(" ")
        .toLowerCase();
      const memberText = data.members
        .filter((member) => member.account_id === account.account_id)
        .map((member) => `${member.email} ${member.display_name ?? ""}`)
        .join(" ")
        .toLowerCase();
      return (
        accountText.includes(normalizedSearch) ||
        memberText.includes(normalizedSearch)
      );
    });
  }, [accountSearch, accountTypeFilter, data.accounts, data.members]);

  const visibleAccountIds = useMemo(
    () => new Set(visibleAccounts.map((account) => account.account_id)),
    [visibleAccounts],
  );
  const selectedAccount =
    data.accounts.find((account) => account.account_id === selectedAccountId) ??
    visibleAccounts[0] ??
    null;
  const selectedAccountIds = selectedAccount
    ? new Set([selectedAccount.account_id])
    : visibleAccountIds;
  const scopedWorkspaces = data.workspaces.filter((workspace) =>
    selectedAccountIds.has(workspace.account_id),
  );
  const scopedMembers = data.members.filter((member) =>
    selectedAccountIds.has(member.account_id),
  );
  const scopedEntitlements = data.entitlements.filter((entitlement) =>
    selectedAccountIds.has(entitlement.account_id),
  );
  const selectedReportGrantCount = scopedWorkspaces.reduce(
    (total, workspace) => total + workspace.active_report_grant_count,
    0,
  );

  function resetView() {
    onAccountSearchChange("");
    onAccountTypeFilterChange("customer");
    onSelectAccount(null);
  }

  return (
    <section className={styles.foundation}>
      <header className={styles.sectionHeader}>
        <div>
          <span className={styles.kicker}>Account access foundation</span>
          <h2>Accounts, workspaces, access, and entitlements</h2>
          <p>
            Read-only CPGHero source-of-truth view for customer account
            structure. Mutating account, role, entitlement, and workspace
            settings should remain gated until policy workflows are finalized.
          </p>
        </div>
        <div className={styles.inlineActions}>
          <label>
            Search
            <input
              onChange={(event) => onAccountSearchChange(event.target.value)}
              placeholder="Account, slug, user email"
              value={accountSearch}
            />
          </label>
          <button
            aria-pressed={accountTypeFilter === "customer"}
            className={
              accountTypeFilter === "customer" ? styles.activeChip : ""
            }
            onClick={() => onAccountTypeFilterChange("customer")}
            type="button"
          >
            Customer accounts only
          </button>
          <button
            aria-pressed={accountTypeFilter === "all"}
            className={accountTypeFilter === "all" ? styles.activeChip : ""}
            onClick={() => onAccountTypeFilterChange("all")}
            type="button"
          >
            All account types
          </button>
          <button
            className={styles.secondaryButton}
            onClick={resetView}
            type="button"
          >
            Reset view
          </button>
          <button onClick={onRefresh} type="button">
            Refresh
          </button>
        </div>
      </header>

      <section className={styles.metrics}>
        <article>
          <small>Customer accounts</small>
          <strong>{formatNumber(data.summary.customer_accounts)}</strong>
          <span>
            {formatNumber(data.summary.active_accounts)} active of{" "}
            {formatNumber(data.summary.accounts)} total account records
          </span>
        </article>
        <article>
          <small>Workspaces</small>
          <strong>{formatNumber(data.summary.workspaces)}</strong>
          <span>
            {formatNumber(data.summary.active_workspaces)} active workspace
            scopes
          </span>
        </article>
        <article>
          <small>Members</small>
          <strong>{formatNumber(data.summary.active_members)}</strong>
          <span>
            Active of {formatNumber(data.summary.members)} total membership
            records
          </span>
        </article>
        <article>
          <small>Active report grants</small>
          <strong>{formatNumber(data.summary.active_report_grants)}</strong>
          <span>Customer report access grants currently available</span>
        </article>
      </section>

      {view === "overview" ? (
        <section className={styles.split}>
          <article className={styles.panel}>
            <header>
              <div>
                <span className={styles.kicker}>Account directory</span>
                <h3>Customer account selector</h3>
              </div>
              <span className={styles.meta}>
                {formatNumber(visibleAccounts.length)} shown
              </span>
            </header>
            <div className={styles.accountList}>
              {visibleAccounts.length ? (
                visibleAccounts.map((account) => (
                  <button
                    aria-pressed={
                      selectedAccount?.account_id === account.account_id
                    }
                    className={`${styles.accountCard} ${
                      selectedAccount?.account_id === account.account_id
                        ? styles.selected
                        : ""
                    }`}
                    key={account.account_id}
                    onClick={() => onSelectAccount(account.account_id)}
                    type="button"
                  >
                    <span>
                      <strong>{account.account_display_name}</strong>
                      <small>{account.account_slug}</small>
                    </span>
                    <span>
                      {formatNumber(account.active_member_count)} members ·{" "}
                      {formatNumber(account.workspace_count)} workspaces
                    </span>
                  </button>
                ))
              ) : (
                <div className={styles.emptyState}>
                  No customer accounts match the current search and filter.
                </div>
              )}
            </div>
          </article>

          <article className={`${styles.panel} ${styles.detailPanel}`}>
            <header>
              <div>
                <span className={styles.kicker}>Account detail</span>
                <h3>
                  {selectedAccount
                    ? selectedAccount.account_display_name
                    : "No account selected"}
                </h3>
              </div>
              {selectedAccount ? (
                <button
                  className={styles.linkButton}
                  onClick={() => onSelectAccount(null)}
                  type="button"
                >
                  Clear selection
                </button>
              ) : null}
            </header>

            {selectedAccount ? (
              <div className={styles.detailStack}>
                <div className={styles.metaGrid}>
                  <span>
                    <small>Status</small>
                    <strong>
                      {selectedAccount.account_type} /{" "}
                      {selectedAccount.account_status}
                    </strong>
                  </span>
                  <span>
                    <small>Identity binding</small>
                    <StatusPill
                      active={
                        selectedAccount.has_identity_provider_organization_binding
                      }
                      trueLabel="Bound"
                      falseLabel="Not bound"
                    />
                  </span>
                  <span>
                    <small>Report grants</small>
                    <strong>{formatNumber(selectedReportGrantCount)}</strong>
                  </span>
                  <span>
                    <small>Created</small>
                    <strong>{formatTime(selectedAccount.created_at)}</strong>
                  </span>
                </div>

                <section className={styles.subsection}>
                  <h4>Workspace access</h4>
                  {scopedWorkspaces.length ? (
                    <div className={styles.compactRows}>
                      {scopedWorkspaces.map((workspace) => (
                        <div key={workspace.workspace_id}>
                          <span>
                            <strong>{workspace.workspace_display_name}</strong>
                            <small>{workspace.workspace_slug}</small>
                          </span>
                          <span>
                            {formatNumber(workspace.active_member_count)}{" "}
                            members ·{" "}
                            {formatNumber(workspace.active_report_grant_count)}{" "}
                            active grants
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.emptyState}>
                      No workspace scopes are configured for this account.
                    </div>
                  )}
                </section>

                <section className={styles.subsection}>
                  <h4>Users and roles</h4>
                  {scopedMembers.length ? (
                    <div className={styles.compactRows}>
                      {scopedMembers.map((member) => (
                        <div
                          key={`${member.account_id}-${member.user_id}-${
                            member.workspace_slug ?? "account"
                          }`}
                        >
                          <span>
                            <strong>
                              {member.display_name ?? member.email}
                            </strong>
                            <small>{member.email}</small>
                          </span>
                          <span>
                            {roleList(member.account_role_keys)}
                            {member.workspace_role_keys.length
                              ? ` · ${roleList(member.workspace_role_keys)}`
                              : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.emptyState}>
                      No active users are visible for this account.
                    </div>
                  )}
                </section>

                <section className={styles.subsection}>
                  <h4>Enabled capabilities</h4>
                  {scopedEntitlements.length ? (
                    <div className={styles.compactRows}>
                      {scopedEntitlements.map((entitlement) => (
                        <div
                          key={`${entitlement.account_id}-${entitlement.entitlement_key}`}
                        >
                          <span>
                            <strong>{entitlement.entitlement_key}</strong>
                            <small>{entitlement.entitlement_status}</small>
                          </span>
                          <span>
                            Expires {formatTime(entitlement.expires_at)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.emptyState}>
                      No account entitlements are configured yet.
                    </div>
                  )}
                </section>
              </div>
            ) : (
              <div className={styles.emptyState}>
                Select a customer account to inspect workspaces, members, roles,
                entitlements, and report-access counts.
              </div>
            )}
          </article>
        </section>
      ) : null}

      {view === "accounts" ? (
        <section className={styles.grid}>
          <article className={styles.panel}>
            <header>
              <div>
                <span className={styles.kicker}>Accounts</span>
                <h3>Customer account inventory</h3>
              </div>
            </header>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Status</th>
                    <th>Workspaces</th>
                    <th>Members</th>
                    <th>Entitlements</th>
                    <th>Report grants</th>
                    <th>Identity</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleAccounts.length ? (
                    visibleAccounts.map((account) => (
                      <tr key={account.account_id}>
                        <td>
                          <strong>{account.account_display_name}</strong>
                          <span>{account.account_slug}</span>
                        </td>
                        <td>
                          {account.account_type} / {account.account_status}
                        </td>
                        <td>{formatNumber(account.workspace_count)}</td>
                        <td>
                          {formatNumber(account.active_member_count)} active
                          <span>
                            {formatNumber(account.member_count)} total
                          </span>
                        </td>
                        <td>
                          {formatNumber(account.active_entitlement_count)}{" "}
                          active
                          <span>
                            {formatNumber(account.entitlement_count)} total
                          </span>
                        </td>
                        <td>
                          {formatNumber(account.active_report_grant_count)}{" "}
                          active
                          <span>
                            {formatNumber(account.revoked_report_grant_count)}{" "}
                            revoked
                          </span>
                        </td>
                        <td>
                          <StatusPill
                            active={
                              account.has_identity_provider_organization_binding
                            }
                            trueLabel="Bound"
                            falseLabel="Not bound"
                          />
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>
                        <div className={styles.emptyState}>
                          No accounts match the current search and type filter.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className={styles.panel}>
            <header>
              <div>
                <span className={styles.kicker}>Workspace scopes</span>
                <h3>Workspace access and report grants</h3>
              </div>
            </header>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Workspace</th>
                    <th>Account</th>
                    <th>Status</th>
                    <th>Active members</th>
                    <th>Report grants</th>
                  </tr>
                </thead>
                <tbody>
                  {scopedWorkspaces.length ? (
                    scopedWorkspaces.map((workspace) => (
                      <tr key={workspace.workspace_id}>
                        <td>
                          <strong>{workspace.workspace_display_name}</strong>
                          <span>{workspace.workspace_slug}</span>
                        </td>
                        <td>{workspace.account_display_name}</td>
                        <td>{workspace.workspace_status}</td>
                        <td>{formatNumber(workspace.active_member_count)}</td>
                        <td>
                          {formatNumber(workspace.active_report_grant_count)}{" "}
                          active
                          <span>
                            {formatNumber(workspace.revoked_report_grant_count)}{" "}
                            revoked
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5}>
                        <div className={styles.emptyState}>
                          No workspace scopes are visible for the current
                          account view.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      ) : null}

      {view === "members" ? (
        <section className={styles.grid}>
          <article className={styles.panel}>
            <header>
              <div>
                <span className={styles.kicker}>Members</span>
                <h3>Users, role scopes, and identity binding</h3>
              </div>
            </header>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Account</th>
                    <th>Workspace</th>
                    <th>Status</th>
                    <th>Roles</th>
                    <th>Identity</th>
                  </tr>
                </thead>
                <tbody>
                  {scopedMembers.length ? (
                    scopedMembers.map((member) => {
                      const rowKey = [
                        member.account_id,
                        member.user_id,
                        member.workspace_slug ?? "account",
                      ].join("-");
                      return (
                        <tr key={rowKey}>
                          <td>
                            <strong>
                              {member.display_name ?? member.email}
                            </strong>
                            <span>{member.email}</span>
                          </td>
                          <td>{member.account_display_name}</td>
                          <td>
                            {member.workspace_display_name ?? "Account-level"}
                          </td>
                          <td>
                            {readableStatus(member.account_membership_status)} /{" "}
                            {readableStatus(member.workspace_membership_status)}
                          </td>
                          <td>
                            {roleList(member.account_role_keys)}
                            <span>{roleList(member.workspace_role_keys)}</span>
                          </td>
                          <td>
                            <StatusPill
                              active={member.has_identity_provider_user_binding}
                              trueLabel="Bound"
                              falseLabel="Not bound"
                            />
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={6}>
                        <div className={styles.emptyState}>
                          No members match the current account view.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className={styles.panel}>
            <header>
              <div>
                <span className={styles.kicker}>Entitlements</span>
                <h3>Enabled account capabilities</h3>
              </div>
            </header>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Entitlement</th>
                    <th>Status</th>
                    <th>Starts</th>
                    <th>Expires</th>
                  </tr>
                </thead>
                <tbody>
                  {scopedEntitlements.length ? (
                    scopedEntitlements.map((entitlement) => (
                      <tr
                        key={`${entitlement.account_id}-${entitlement.entitlement_key}`}
                      >
                        <td>{entitlement.account_display_name}</td>
                        <td>{entitlement.entitlement_key}</td>
                        <td>{entitlement.entitlement_status}</td>
                        <td>{formatTime(entitlement.starts_at)}</td>
                        <td>{formatTime(entitlement.expires_at)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5}>
                        <div className={styles.emptyState}>
                          No account entitlements are configured for this view.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      ) : null}
    </section>
  );
}

function AdminLogin({
  configured,
  onLogin,
}: Readonly<{ configured: boolean; onLogin: (password: string) => void }>) {
  const [password, setPassword] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onLogin(password);
  }

  return (
    <section className="admin-auth-card">
      <div>
        <p className="eyebrow">Administrator session required</p>
        <h2>Sign in to view Accounts &amp; Access</h2>
        <p>
          This page is protected because it exposes internal rollout status and
          operational identity-provider health.
        </p>
      </div>
      {configured ? (
        <form onSubmit={submit}>
          <input
            aria-label="Administrator password"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Administrator password"
            type="password"
            value={password}
          />
          <button type="submit">Unlock</button>
        </form>
      ) : (
        <p>
          Configure the administrator password and session secret before using
          this workspace.
        </p>
      )}
    </section>
  );
}

function ReadinessWorkspace({
  data,
  email,
  onEmailChange,
  onRefresh,
}: Readonly<{
  data: CustomerAuthReadiness;
  email: string;
  onEmailChange: (value: string) => void;
  onRefresh: () => void;
}>) {
  return (
    <div className={styles.workspace}>
      <section className={styles.hero}>
        <div>
          <span className={styles.kicker}>Customer login readiness</span>
          <h2>
            {data.cutover_ready
              ? "Cutover checks are clear"
              : "Cutover is intentionally blocked"}
          </h2>
          <p>
            Customer-facing surfaces remain CPGHero branded. This readiness view
            checks login state, controlled-rollout guardrails, invitation
            status, and recent identity event processing.
          </p>
        </div>
        <StatusPill
          active={data.cutover_ready}
          trueLabel="Ready"
          falseLabel="Blocked"
        />
      </section>

      <section className={styles.toolbar}>
        <label>
          Filter by email
          <input
            onChange={(event) => onEmailChange(event.target.value)}
            placeholder="brian@cpghero.com"
            type="email"
            value={email}
          />
        </label>
        <button onClick={onRefresh} type="button">
          Refresh readiness
        </button>
      </section>

      <section className={styles.metrics}>
        <article>
          <small>Login provider state</small>
          <strong>
            {data.customer_login_enabled ? "Enabled" : "Disabled"}
          </strong>
          <span>
            {data.customer_auth_provider === "disabled"
              ? "Customer login remains disabled for production users."
              : "Customer login is configured behind controlled rollout rules."}
          </span>
        </article>
        <article>
          <small>Canary guardrail</small>
          <strong>{data.canary.enabled ? "On" : "Off"}</strong>
          <span>
            {data.canary.configured
              ? `${data.canary.allowed_email_count} emails · ${data.canary.allowed_domain_count} domains`
              : "No allowlist configured"}
          </span>
        </article>
        <article>
          <small>Invitations</small>
          <strong>{data.invitations.length.toLocaleString()}</strong>
          <span>Prepared customer users visible to this check</span>
        </article>
        <article>
          <small>Identity events</small>
          <strong>{data.recent_webhook_events.length.toLocaleString()}</strong>
          <span>Recent inbound events received and inspected</span>
        </article>
      </section>

      {data.blockers.length ? (
        <section className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Go/no-go blockers</span>
              <h3>Resolve before customer-login cutover</h3>
            </div>
          </header>
          <ul className={styles.blockers}>
            {data.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={styles.grid}>
        <article className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Invitation readiness</span>
              <h3>Prepared users</h3>
            </div>
          </header>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Account</th>
                  <th>Invitation</th>
                  <th>Membership</th>
                  <th>Bindings</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.invitations.length ? (
                  data.invitations.map((invitation) => (
                    <tr key={`${invitation.account_slug}-${invitation.email}`}>
                      <td>{invitation.email}</td>
                      <td>
                        <strong>{invitation.account_display_name}</strong>
                        <span>{invitation.account_slug}</span>
                      </td>
                      <td>{readableStatus(invitation.invitation_status)}</td>
                      <td>
                        {readableStatus(invitation.account_membership_status)} /{" "}
                        {readableStatus(invitation.workspace_membership_status)}
                      </td>
                      <td>
                        <StatusPill
                          active={invitation.has_external_user_mapping}
                          trueLabel="User"
                          falseLabel="No user"
                        />
                        <StatusPill
                          active={invitation.has_external_organization_mapping}
                          trueLabel="Org"
                          falseLabel="No org"
                        />
                        <StatusPill
                          active={invitation.has_workos_invitation}
                          trueLabel="Invite"
                          falseLabel="No invite"
                        />
                      </td>
                      <td>{formatTime(invitation.updated_at)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>
                      <div className={styles.emptyState}>
                        No prepared customer invitations match this email
                        filter.
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Event processing</span>
              <h3>Recent identity events</h3>
            </div>
          </header>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Status</th>
                  <th>Email</th>
                  <th>Evidence</th>
                  <th>Processed</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_webhook_events.length ? (
                  data.recent_webhook_events.map((event) => (
                    <tr key={`${event.event_type}-${event.received_at}`}>
                      <td>{event.event_type}</td>
                      <td>{readableStatus(event.processing_status)}</td>
                      <td>{event.email_snapshot ?? "unknown"}</td>
                      <td>
                        <StatusPill
                          active={event.has_workos_user}
                          trueLabel="User"
                          falseLabel="No user"
                        />
                        <StatusPill
                          active={event.has_workos_organization}
                          trueLabel="Org"
                          falseLabel="No org"
                        />
                      </td>
                      <td>
                        {formatTime(event.processed_at ?? event.received_at)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5}>
                      <div className={styles.emptyState}>
                        No recent identity events are available for this check.
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </div>
  );
}

export function CustomerAuthAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [data, setData] = useState<CustomerAuthReadiness | null>(null);
  const [foundation, setFoundation] =
    useState<CustomerAccountFoundation | null>(null);
  const [email, setEmail] = useState(DEFAULT_READINESS_EMAIL);
  const [accountSearch, setAccountSearch] = useState("");
  const [accountTypeFilter, setAccountTypeFilter] =
    useState<AccountTypeFilter>("customer");
  const [activeView, setActiveView] = useState<FoundationView>("overview");
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (emailValue: string) => {
    const query = emailValue.trim()
      ? `?email=${encodeURIComponent(emailValue.trim())}`
      : "";
    setData(
      await jsonRequest<CustomerAuthReadiness>(
        `/api/admin/customer-auth${query}`,
      ),
    );
  }, []);

  const loadFoundation = useCallback(async () => {
    setFoundation(
      await jsonRequest<CustomerAccountFoundation>(
        "/api/admin/customer-auth/account-foundation",
      ),
    );
  }, []);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then((value) => {
        setSession(value);
        if (value.authenticated) {
          void Promise.all([
            load(DEFAULT_READINESS_EMAIL),
            loadFoundation(),
          ]).catch((err: unknown) => {
            setError(
              err instanceof Error
                ? err.message
                : "Unable to load account administration data.",
            );
          });
        }
      })
      .catch((err: unknown) => {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check administrator access.",
        );
        setSession({ authenticated: false, configured: false });
      });
  }, [load, loadFoundation]);

  async function login(password: string) {
    try {
      setError(null);
      await jsonRequest("/api/admin/session", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setSession({ authenticated: true, configured: true });
      await Promise.all([load(email), loadFoundation()]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to unlock administrator session.",
      );
    }
  }

  async function refresh() {
    try {
      setError(null);
      await Promise.all([load(email), loadFoundation()]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to refresh admin data.",
      );
    }
  }

  if (!session) {
    return (
      <div className="builder-loading">Checking administrator access…</div>
    );
  }

  if (!session.authenticated) {
    return (
      <>
        {error ? <p className={styles.error}>{error}</p> : null}
        <AdminLogin configured={session.configured} onLogin={login} />
      </>
    );
  }

  return (
    <>
      {error ? <p className={styles.error}>{error}</p> : null}
      {data && foundation ? (
        <div className={styles.workspace}>
          <FoundationTabs
            activeView={activeView}
            onViewChange={setActiveView}
          />
          {activeView === "readiness" ? (
            <ReadinessWorkspace
              data={data}
              email={email}
              onEmailChange={setEmail}
              onRefresh={refresh}
            />
          ) : (
            <FoundationWorkspace
              accountSearch={accountSearch}
              accountTypeFilter={accountTypeFilter}
              data={foundation}
              onAccountSearchChange={setAccountSearch}
              onAccountTypeFilterChange={setAccountTypeFilter}
              onRefresh={refresh}
              onSelectAccount={setSelectedAccountId}
              selectedAccountId={selectedAccountId}
              view={activeView}
            />
          )}
        </div>
      ) : (
        <div className="builder-loading">Loading account administration…</div>
      )}
    </>
  );
}
