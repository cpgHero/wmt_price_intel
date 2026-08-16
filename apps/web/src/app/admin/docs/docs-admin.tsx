"use client";

import Link from "next/link";
import {
  FormEvent,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  PlatformDocBlock,
  PlatformDocGroupId,
  PlatformDocGuide,
  PlatformDocumentation,
} from "@/lib/platform-docs";

import styles from "./docs-admin.module.css";

interface AdminSession {
  authenticated: boolean;
  configured: boolean;
}

const platformDocGroups: ReadonlyArray<{
  id: PlatformDocGroupId;
  label: string;
}> = [
  { id: "orientation", label: "Start here" },
  { id: "workflows", label: "Workflows" },
  { id: "governance", label: "Trust & governance" },
  { id: "operations", label: "Operations" },
  { id: "reference", label: "Reference" },
];

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const raw = await response.text();
  let body: (T & { detail?: string; error?: string }) | null = null;
  if (raw) {
    try {
      body = JSON.parse(raw) as T & { detail?: string; error?: string };
    } catch {
      if (!response.ok) throw new Error(raw || `Request failed (${response.status})`);
      throw new Error("The server returned an unreadable response.");
    }
  }
  if (!response.ok) {
    throw new Error(
      body?.error ?? body?.detail ?? `Request failed (${response.status})`,
    );
  }
  return body as T;
}

function blockSearchText(block: PlatformDocBlock): string {
  if (block.kind === "paragraphs") return block.paragraphs.join(" ");
  if (block.kind === "list") return block.items.join(" ");
  if (block.kind === "steps") {
    return block.items.map((item) => `${item.title} ${item.detail}`).join(" ");
  }
  if (block.kind === "definitions") {
    return block.items
      .map((item) => `${item.term} ${item.definition}`)
      .join(" ");
  }
  if (block.kind === "table") {
    return `${block.columns.join(" ")} ${block.rows.flat().join(" ")}`;
  }
  return `${block.title} ${block.text}`;
}

function guideSearchText(guide: PlatformDocGuide): string {
  return [
    guide.title,
    guide.summary,
    guide.audience,
    ...guide.blocks.map((block) => `${block.title ?? ""} ${blockSearchText(block)}`),
  ]
    .join(" ")
    .toLocaleLowerCase();
}

function GuideBlock({ block, index }: Readonly<{ block: PlatformDocBlock; index: number }>) {
  const headingId = `guide-section-${index}`;
  if (block.kind === "callout") {
    return (
      <aside className={`${styles.callout} ${styles[block.tone]}`}>
        <span aria-hidden="true" className={styles.calloutMark} />
        <div>
          <h3>{block.title}</h3>
          <p>{block.text}</p>
        </div>
      </aside>
    );
  }
  if (block.kind === "paragraphs") {
    return (
      <section className={styles.guideSection}>
        {block.title ? <h2 id={headingId}>{block.title}</h2> : null}
        {block.paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </section>
    );
  }
  if (block.kind === "list") {
    return (
      <section className={styles.guideSection}>
        {block.title ? <h2 id={headingId}>{block.title}</h2> : null}
        <ul className={styles.bulletList}>
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    );
  }
  if (block.kind === "steps") {
    return (
      <section className={styles.guideSection}>
        {block.title ? <h2 id={headingId}>{block.title}</h2> : null}
        <ol className={styles.stepList}>
          {block.items.map((item, stepIndex) => (
            <li key={`${item.title}-${stepIndex}`}>
              <span className={styles.stepNumber}>{stepIndex + 1}</span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
                {item.link ? (
                  <Link href={item.link.href}>{item.link.label} →</Link>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </section>
    );
  }
  if (block.kind === "definitions") {
    return (
      <section className={styles.guideSection}>
        {block.title ? <h2 id={headingId}>{block.title}</h2> : null}
        <dl className={styles.definitions}>
          {block.items.map((item) => (
            <div key={item.term}>
              <dt>{item.term}</dt>
              <dd>{item.definition}</dd>
            </div>
          ))}
        </dl>
      </section>
    );
  }
  return (
    <section className={styles.guideSection}>
      {block.title ? <h2 id={headingId}>{block.title}</h2> : null}
      <div className={styles.tableScroll}>
        <table>
          <thead>
            <tr>
              {block.columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={`${row[0]}-${rowIndex}`}>
                {row.map((cell, cellIndex) =>
                  cellIndex === 0 ? (
                    <th key={cellIndex} scope="row">
                      {cell}
                    </th>
                  ) : (
                    <td key={cellIndex}>{cell}</td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DocsWorkspace({ documentation }: Readonly<{ documentation: PlatformDocumentation }>) {
  const [selectedGuideId, setSelectedGuideId] = useState("start-here");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const articleRef = useRef<HTMLElement>(null);

  const visibleGuides = useMemo(() => {
    if (!deferredQuery) return documentation.guides;
    return documentation.guides.filter((guide) =>
      guideSearchText(guide).includes(deferredQuery),
    );
  }, [deferredQuery, documentation.guides]);

  const selectedGuide =
    visibleGuides.find((guide) => guide.id === selectedGuideId) ??
    visibleGuides[0] ??
    null;

  function selectGuide(guideId: string) {
    setSelectedGuideId(guideId);
    window.requestAnimationFrame(() =>
      articleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  }

  return (
    <div className={styles.docsWorkspace}>
      <section className={styles.docsHero}>
        <div>
          <span className={styles.heroKicker}>Maintained operating manual</span>
          <h2>{documentation.title}</h2>
          <p>
            Understand what the platform does at every step, which evidence is
            authoritative, where human decisions enter, and how changes are
            tested and recorded.
          </p>
        </div>
        <dl>
          <div>
            <dt>Docs version</dt>
            <dd>{documentation.version}</dd>
          </div>
          <div>
            <dt>Last verified</dt>
            <dd>{documentation.lastVerified}</dd>
          </div>
          <div>
            <dt>Baseline</dt>
            <dd>{documentation.baseline}</dd>
          </div>
          <div>
            <dt>Maintenance owner</dt>
            <dd>{documentation.maintenanceOwner}</dd>
          </div>
        </dl>
      </section>

      <section className={styles.searchBar} aria-label="Documentation search">
        <label htmlFor="platform-doc-search">
          <span>Search all platform docs</span>
          <input
            autoComplete="off"
            id="platform-doc-search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Try “PDP”, “rate limit”, “match certification”, or “lower-price share”"
            type="search"
            value={query}
          />
        </label>
        <span className={styles.resultCount} aria-live="polite">
          {deferredQuery
            ? `${visibleGuides.length} guide${visibleGuides.length === 1 ? "" : "s"} found`
            : `${documentation.guides.length} maintained guides`}
        </span>
      </section>

      <div className={styles.docsLayout}>
        <aside className={styles.guideNavigation} aria-label="Documentation guides">
          {platformDocGroups.map((group) => {
            const groupGuides = visibleGuides.filter(
              (guide) => guide.group === group.id,
            );
            if (groupGuides.length === 0) return null;
            return (
              <section key={group.id}>
                <h2>{group.label}</h2>
                <div>
                  {groupGuides.map((guide) => (
                    <button
                      aria-current={selectedGuide?.id === guide.id ? "page" : undefined}
                      key={guide.id}
                      onClick={() => selectGuide(guide.id)}
                      type="button"
                    >
                      <strong>{guide.title}</strong>
                      <span>{guide.readingTime}</span>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
          {visibleGuides.length === 0 ? (
            <div className={styles.emptySearch}>
              <strong>No guide contains “{query}”</strong>
              <button onClick={() => setQuery("")} type="button">
                Clear search
              </button>
            </div>
          ) : null}
        </aside>

        {selectedGuide ? (
          <article className={styles.guideArticle} ref={articleRef}>
            <header className={styles.guideHeader}>
              <div className={styles.guideStatusRow}>
                <span className={styles.statusPill}>{selectedGuide.status}</span>
                <span>{selectedGuide.readingTime} read</span>
              </div>
              <h1>{selectedGuide.title}</h1>
              <p>{selectedGuide.summary}</p>
              <dl>
                <div>
                  <dt>Audience</dt>
                  <dd>{selectedGuide.audience}</dd>
                </div>
                <div>
                  <dt>Last verified</dt>
                  <dd>{selectedGuide.lastVerified}</dd>
                </div>
              </dl>
              {selectedGuide.links?.length ? (
                <nav aria-label="Related application pages">
                  {selectedGuide.links.map((link) => (
                    <Link href={link.href} key={link.href}>
                      {link.label} →
                    </Link>
                  ))}
                </nav>
              ) : null}
            </header>
            <div className={styles.guideBody}>
              {selectedGuide.blocks.map((block, index) => (
                <GuideBlock block={block} index={index} key={`${block.kind}-${block.title ?? index}`} />
              ))}
            </div>
            <footer className={styles.guideFooter}>
              <strong>Found something that no longer matches the app?</strong>
              <span>
                Treat it as a documentation defect and record the correction in
                Change orders &amp; documentation maintenance.
              </span>
            </footer>
          </article>
        ) : (
          <section className={styles.noGuide}>
            <h2>No documentation matches this search</h2>
            <p>Try a broader term or clear the search to restore every guide.</p>
          </section>
        )}
      </div>
    </div>
  );
}

export function DocsAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [documentation, setDocumentation] =
    useState<PlatformDocumentation | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadDocumentation() {
    setDocumentation(
      await jsonRequest<PlatformDocumentation>("/api/admin/docs"),
    );
  }

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then(async (value) => {
        setSession(value);
        if (value.authenticated) await loadDocumentation();
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to check administrator access.",
        ),
      );
  }, []);

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
      await loadDocumentation();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to authenticate.");
    } finally {
      setBusy(false);
    }
  }

  if (session === null) {
    return <div className="builder-loading">Checking administrator access…</div>;
  }
  if (!session.authenticated) {
    return (
      <section className="admin-auth-card">
        <span className="section-kicker">Restricted reference</span>
        <h2>Administrator authentication required</h2>
        <p>
          These operating docs describe platform administration, evidence
          governance, spending controls, and production workflows. Access uses
          the same protected administrator session as the other admin workspaces.
        </p>
        {!session.configured ? (
          <div className="builder-alert warning">
            <b>Authentication is not configured</b>
            <span>
              Configure the administrator password and session secret on the
              Railway web service before exposing this reference.
            </span>
          </div>
        ) : (
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
              {busy ? "Checking…" : "Open Platform Docs"}
            </button>
          </form>
        )}
        {error ? <p className="form-error">{error}</p> : null}
      </section>
    );
  }
  if (!documentation) {
    return (
      <div className="builder-loading">
        {error ? error : "Loading maintained platform documentation…"}
      </div>
    );
  }
  return <DocsWorkspace documentation={documentation} />;
}
