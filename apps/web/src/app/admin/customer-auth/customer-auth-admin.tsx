"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import styles from "./customer-auth.module.css";

const DEFAULT_READINESS_EMAIL = "brian@cpghero.com";

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

function FoundationWorkspace({
  data,
  accountSlug,
  onAccountSlugChange,
  onRefresh,
}: Readonly<{
  data: CustomerAccountFoundation;
  accountSlug: string;
  onAccountSlugChange: (value: string) => void;
  onRefresh: () => void;
}>) {
  return (
    <section className={styles.foundation}>
      <header className={styles.sectionHeader}>
        <div>
          <span className={styles.kicker}>
            Account administration foundation
          </span>
          <h2>Accounts, workspaces, access, and entitlements</h2>
          <p>
            Read-only CPGHero source-of-truth view for customer account
            structure. Mutating account, role, entitlement, and workspace
            settings should remain gated until policy workflows are finalized.
          </p>
        </div>
        <div className={styles.inlineActions}>
          <label>
            Account slug
            <input
              onChange={(event) => onAccountSlugChange(event.target.value)}
              placeholder="Filter by account slug"
              value={accountSlug}
            />
          </label>
          <button onClick={onRefresh} type="button">
            Refresh foundation
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

      <section className={styles.grid}>
        <article className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Accounts</span>
              <h3>Customer and system account inventory</h3>
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
                {data.accounts.map((account) => (
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
                      <span>{formatNumber(account.member_count)} total</span>
                    </td>
                    <td>
                      {formatNumber(account.active_entitlement_count)} active
                      <span>
                        {formatNumber(account.entitlement_count)} total
                      </span>
                    </td>
                    <td>
                      {formatNumber(account.active_report_grant_count)} active
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
                ))}
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
                {data.workspaces.map((workspace) => (
                  <tr key={workspace.workspace_id}>
                    <td>
                      <strong>{workspace.workspace_display_name}</strong>
                      <span>{workspace.workspace_slug}</span>
                    </td>
                    <td>{workspace.account_display_name}</td>
                    <td>{workspace.workspace_status}</td>
                    <td>{formatNumber(workspace.active_member_count)}</td>
                    <td>
                      {formatNumber(workspace.active_report_grant_count)} active
                      <span>
                        {formatNumber(workspace.revoked_report_grant_count)}{" "}
                        revoked
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

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
                {data.members.map((member) => {
                  const rowKey = [
                    member.account_id,
                    member.user_id,
                    member.workspace_slug ?? "account",
                  ].join("-");
                  return (
                    <tr key={rowKey}>
                      <td>
                        <strong>{member.display_name ?? member.email}</strong>
                        <span>{member.email}</span>
                      </td>
                      <td>{member.account_display_name}</td>
                      <td>
                        {member.workspace_display_name ?? "Account-level"}
                      </td>
                      <td>
                        {member.account_membership_status} /{" "}
                        {member.workspace_membership_status ?? "none"}
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
                })}
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
                {data.entitlements.map((entitlement) => (
                  <tr
                    key={`${entitlement.account_id}-${entitlement.entitlement_key}`}
                  >
                    <td>{entitlement.account_display_name}</td>
                    <td>{entitlement.entitlement_key}</td>
                    <td>{entitlement.entitlement_status}</td>
                    <td>{formatTime(entitlement.starts_at)}</td>
                    <td>{formatTime(entitlement.expires_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>
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
        <h2>Sign in to view customer-auth readiness</h2>
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
            Customer-facing surfaces remain CPGHero branded. This view shows
            internal provider status only for platform administrators.
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
          <small>Provider state</small>
          <strong>
            {data.customer_login_enabled ? "Enabled" : "Disabled"}
          </strong>
          <span>Internal provider: {data.customer_auth_provider}</span>
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
          <small>Webhooks</small>
          <strong>{data.recent_webhook_events.length.toLocaleString()}</strong>
          <span>Recent identity events received and inspected</span>
        </article>
      </section>

      {data.blockers.length ? (
        <section className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Go/no-go blockers</span>
              <h3>Resolve before customer-auth cutover</h3>
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
                {data.invitations.map((invitation) => (
                  <tr key={`${invitation.account_slug}-${invitation.email}`}>
                    <td>{invitation.email}</td>
                    <td>
                      <strong>{invitation.account_display_name}</strong>
                      <span>{invitation.account_slug}</span>
                    </td>
                    <td>{invitation.invitation_status}</td>
                    <td>
                      {invitation.account_membership_status ?? "unknown"} /
                      {invitation.workspace_membership_status ?? "unknown"}
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
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <header>
            <div>
              <span className={styles.kicker}>Webhook processing</span>
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
                {data.recent_webhook_events.map((event) => (
                  <tr key={`${event.event_type}-${event.received_at}`}>
                    <td>{event.event_type}</td>
                    <td>{event.processing_status}</td>
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
                ))}
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
  const [accountSlug, setAccountSlug] = useState("");
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

  const loadFoundation = useCallback(async (slugValue: string) => {
    const query = slugValue.trim()
      ? `?account_slug=${encodeURIComponent(slugValue.trim())}`
      : "";
    setFoundation(
      await jsonRequest<CustomerAccountFoundation>(
        `/api/admin/customer-auth/account-foundation${query}`,
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
            loadFoundation(""),
          ]).catch((err: unknown) => {
            setError(
              err instanceof Error
                ? err.message
                : "Unable to load customer administration data.",
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
      await Promise.all([load(email), loadFoundation(accountSlug)]);
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
      await Promise.all([load(email), loadFoundation(accountSlug)]);
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
          <FoundationWorkspace
            accountSlug={accountSlug}
            data={foundation}
            onAccountSlugChange={setAccountSlug}
            onRefresh={refresh}
          />
          <ReadinessWorkspace
            data={data}
            email={email}
            onEmailChange={setEmail}
            onRefresh={refresh}
          />
        </div>
      ) : (
        <div className="builder-loading">Loading customer administration…</div>
      )}
    </>
  );
}
