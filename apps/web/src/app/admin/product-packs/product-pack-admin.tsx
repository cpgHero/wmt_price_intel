"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

interface AdminSession {
  configured: boolean;
  authenticated: boolean;
}

interface BuilderStatus {
  enabled: boolean;
  writes_require_authentication: boolean;
  production_safe: boolean;
}

interface ProductPackSummary {
  id: string;
  name: string;
  version: string;
  default_keyword: string;
}

interface ProductPackDraft {
  id: string;
  product_pack_id: string;
  base_version: string | null;
  proposed_version: string;
  status: string;
  revision: number;
  config: Record<string, unknown>;
  checksum: string;
  updated_at: string;
}

interface CollectionOptions {
  product_packs: ProductPackSummary[];
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const body = (await response.json()) as T & {
    error?: string;
    detail?: string;
  };
  if (!response.ok)
    throw new Error(
      body.error ?? body.detail ?? `Request failed (${response.status})`,
    );
  return body;
}

function displayDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ProductPackAdmin() {
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [status, setStatus] = useState<BuilderStatus | null>(null);
  const [packs, setPacks] = useState<ProductPackSummary[]>([]);
  const [drafts, setDrafts] = useState<ProductPackDraft[]>([]);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [mode, setMode] = useState<"clone" | "new">("clone");
  const [sourceId, setSourceId] = useState("");
  const [packId, setPackId] = useState("");
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [categoryFamily, setCategoryFamily] = useState("");
  const [keyword, setKeyword] = useState("");

  const loadWorkspace = useCallback(async () => {
    const [builderStatus, collectionOptions, draftRows] = await Promise.all([
      jsonRequest<BuilderStatus>("/api/admin/product-packs/status"),
      jsonRequest<CollectionOptions>("/api/collections/options"),
      jsonRequest<ProductPackDraft[]>("/api/admin/product-packs/drafts"),
    ]);
    setStatus(builderStatus);
    setPacks(collectionOptions.product_packs);
    setDrafts(draftRows);
    if (!sourceId && collectionOptions.product_packs[0]) {
      setSourceId(collectionOptions.product_packs[0].id);
    }
  }, [sourceId]);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then((value) => {
        setSession(value);
        if (value.authenticated) return loadWorkspace();
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load admin access.",
        ),
      );
  }, [loadWorkspace]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await jsonRequest("/api/admin/session", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setSession({ configured: true, authenticated: true });
      setPassword("");
      await loadWorkspace();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to authenticate.",
      );
    } finally {
      setBusy(false);
    }
  }

  function selectSource(value: string) {
    setSourceId(value);
    const source = packs.find((pack) => pack.id === value);
    if (!source) return;
    setPackId(source.id);
    setName(source.name);
    setKeyword(source.default_keyword);
    const [major, minor] = source.version.split(".").map(Number);
    setVersion(`${major}.${minor + 1}.0`);
    setCategoryFamily(source.id.replace(/^fresh_/, "").replaceAll("_", " "));
  }

  async function createDraft(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const source = packs.find((pack) => pack.id === sourceId);
      const draft = await jsonRequest<ProductPackDraft>(
        "/api/admin/product-packs/drafts",
        {
          method: "POST",
          body: JSON.stringify({
            product_pack_id: packId,
            name,
            proposed_version: version,
            category_family: categoryFamily,
            default_keyword: keyword,
            source_pack_id: mode === "clone" ? source?.id : null,
            source_version: mode === "clone" ? source?.version : null,
          }),
        },
      );
      router.push(`/admin/product-packs/drafts/${draft.id}`);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to create the draft.",
      );
      setBusy(false);
    }
  }

  if (session === null) {
    return (
      <div className="builder-loading">Checking administrator access…</div>
    );
  }
  if (!session.authenticated) {
    return (
      <section className="admin-auth-card">
        <span className="section-kicker">Restricted workspace</span>
        <h2>Administrator authentication required</h2>
        <p>
          Product Pack drafts can change future analytics. Access is isolated
          from the public reporting application and expires after eight hours.
        </p>
        {!session.configured ? (
          <div className="builder-alert warning">
            <b>Authentication is not configured</b>
            <span>
              Add PRODUCT_PACK_ADMIN_PASSWORD and PRODUCT_PACK_SESSION_SECRET to
              the Railway web service before enabling this workspace.
            </span>
          </div>
        ) : (
          <form onSubmit={signIn}>
            <label>
              <span>Administrator password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? "Checking…" : "Open Product Pack builder"}
            </button>
          </form>
        )}
        {error ? <p className="form-error">{error}</p> : null}
      </section>
    );
  }

  return (
    <div className="product-pack-admin-shell">
      {error ? (
        <div className="builder-alert error">
          <b>Unable to complete the request</b>
          <span>{error}</span>
        </div>
      ) : null}
      {status && !status.enabled ? (
        <div className="builder-alert warning">
          <b>Authoring is disabled</b>
          <span>
            Set PRODUCT_PACK_BUILDER_ENABLED=true after the production
            authentication secrets are installed.
          </span>
        </div>
      ) : null}

      <section className="product-pack-overview-grid">
        <article>
          <span>Active Product Packs</span>
          <strong>{packs.length}</strong>
          <small>Certified versions available to Collection Builder</small>
        </article>
        <article>
          <span>Open drafts</span>
          <strong>
            {drafts.filter((draft) => draft.status !== "published").length}
          </strong>
          <small>Mutable, revisioned authoring workspaces</small>
        </article>
        <article>
          <span>Certified or published</span>
          <strong>
            {
              drafts.filter((draft) =>
                ["certified", "published"].includes(draft.status),
              ).length
            }
          </strong>
          <small>Passed publication-level governance</small>
        </article>
      </section>

      <section className="workspace-section product-pack-catalog">
        <header>
          <div>
            <span className="section-kicker">Immutable catalog</span>
            <h2>Published category intelligence</h2>
            <p>
              Active versions are exact inputs to collections, analytics,
              matching, and reporting.
            </p>
          </div>
          <button
            className="button primary"
            type="button"
            onClick={() => setShowCreate((value) => !value)}
          >
            {showCreate ? "Close" : "New Product Pack"}
          </button>
        </header>
        {showCreate ? (
          <form className="product-pack-create-form" onSubmit={createDraft}>
            <div
              className="segmented-control"
              aria-label="Product Pack starting point"
            >
              <button
                type="button"
                className={mode === "clone" ? "active" : ""}
                onClick={() => setMode("clone")}
              >
                Clone certified pack
              </button>
              <button
                type="button"
                className={mode === "new" ? "active" : ""}
                onClick={() => setMode("new")}
              >
                Start a new category
              </button>
            </div>
            {mode === "clone" ? (
              <label>
                <span>Starting version</span>
                <select
                  value={sourceId}
                  onChange={(event) => selectSource(event.target.value)}
                >
                  <option value="">Select a Product Pack</option>
                  {packs.map((pack) => (
                    <option value={pack.id} key={pack.id}>
                      {pack.name} · v{pack.version}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <div className="product-pack-create-grid">
              <label>
                <span>Stable ID</span>
                <input
                  value={packId}
                  onChange={(event) =>
                    setPackId(
                      event.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9_]/g, "_"),
                    )
                  }
                  placeholder="fresh_category"
                  required
                />
              </label>
              <label>
                <span>Name</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Fresh Category"
                  required
                />
              </label>
              <label>
                <span>Proposed version</span>
                <input
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                  pattern="[0-9]+\.[0-9]+\.[0-9]+"
                  required
                />
              </label>
              <label>
                <span>Category family</span>
                <input
                  value={categoryFamily}
                  onChange={(event) => setCategoryFamily(event.target.value)}
                  placeholder="category term"
                  required
                />
              </label>
              <label>
                <span>Default search keyword</span>
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="category term"
                  required
                />
              </label>
            </div>
            <div className="builder-alert">
              <b>No paid calls</b>
              <span>
                Creating a draft copies configuration only. SERP, PDP, web, and
                AI work remain separately governed.
              </span>
            </div>
            <button
              className="button primary"
              disabled={busy || !status?.enabled}
            >
              {busy ? "Creating…" : "Create governed draft"}
            </button>
          </form>
        ) : null}
        <div className="product-pack-release-grid">
          {packs.map((pack) => (
            <article key={pack.id}>
              <div>
                <span className="status-badge succeeded">Active</span>
                <small>v{pack.version}</small>
              </div>
              <h3>{pack.name}</h3>
              <p>{pack.default_keyword}</p>
              <code>{pack.id}</code>
            </article>
          ))}
        </div>
      </section>

      <section className="workspace-section product-pack-drafts">
        <header>
          <div>
            <span className="section-kicker">Authoring queue</span>
            <h2>Drafts and candidates</h2>
            <p>
              Every save creates an immutable revision; validation results
              remain tied to the exact checksum.
            </p>
          </div>
        </header>
        {drafts.length ? (
          <div className="product-pack-draft-list">
            {drafts.map((draft) => (
              <Link
                href={`/admin/product-packs/drafts/${draft.id}`}
                key={draft.id}
              >
                <span
                  className={`status-badge ${draft.status === "published" ? "succeeded" : draft.status === "certified" ? "running" : "queued"}`}
                >
                  {draft.status.replaceAll("_", " ")}
                </span>
                <div>
                  <h3>{String(draft.config.name ?? draft.product_pack_id)}</h3>
                  <p>
                    {draft.product_pack_id} · proposed v{draft.proposed_version}
                  </p>
                </div>
                <dl>
                  <div>
                    <dt>Revision</dt>
                    <dd>{draft.revision}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{displayDate(draft.updated_at)}</dd>
                  </div>
                </dl>
                <b>→</b>
              </Link>
            ))}
          </div>
        ) : (
          <div className="positive-empty-state">
            <span>✓</span>
            <div>
              <b>No open drafts</b>
              <p>
                Clone a certified version or begin a new category when the
                evidence is ready.
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
