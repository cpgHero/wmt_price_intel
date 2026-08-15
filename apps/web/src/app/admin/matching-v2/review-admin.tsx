"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

interface AdminSession {
  configured: boolean;
  authenticated: boolean;
}

interface QueueSummary {
  queue_id: string;
  version: string;
  product_pack: { id: string; version: string };
  case_count: number;
  reviewed_case_count: number;
  adjudicated_case_count: number;
  created_at: string;
}

interface ListingSummary {
  listing_id: string;
  retailer_id: string;
  retailer_product_id: string;
  title: string | null;
  brand: string | null;
  brand_type: string;
  brand_verified: boolean;
  image_url: string | null;
  product_url: string | null;
  attributes: Record<
    string,
    {
      value: unknown;
      source: string;
      reliability: number;
      review_status: string;
    }
  >;
}

interface ReviewSubmission {
  id: string;
  reviewer_id: string;
  verdict: string;
  allowed_tiers: string[];
  rationale: string;
  evidence_refs: string[];
}

interface ReviewCase {
  case_id: string;
  stratum: string;
  critical: boolean;
  benchmark_listing: ListingSummary;
  competitor_listing: ListingSummary;
  engine_proposal: {
    tier: string | null;
    status: string;
    decision_reason: string;
    evidence_coverage: { critical_coverage: number };
  };
  edge: {
    attribute_evidence: Array<{
      attribute: string;
      role: string;
      benchmark_value: unknown;
      competitor_value: unknown;
      outcome: string;
      benchmark_source: string | null;
      competitor_source: string | null;
      reliability: number;
    }>;
  };
  evidence_refs: string[];
  review_status: string;
  review_submissions: ReviewSubmission[];
  adjudication: null | {
    verdict: string;
    allowed_tiers: string[];
    rationale: string;
  };
}

interface QueueView {
  authoritative: false;
  queue: QueueSummary;
  status_counts: Record<string, number>;
  total_cases: number;
  selected_case_count: number;
  offset: number;
  limit: number;
  cases: ReviewCase[];
}

interface ReviewDraft {
  verdict: "comparable" | "not_comparable" | "insufficient_evidence";
  tier: string;
  rationale: string;
}

const DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001";
const TIERS = [
  "exact_item",
  "exact_specification",
  "equivalent_product",
  "comparable_substitute",
  "custom_approved",
] as const;
const PAGE_SIZE = 50;

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

function label(value: string | null | undefined) {
  if (!value) return "Unresolved";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function evidenceValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ProductIdentity({ listing }: Readonly<{ listing: ListingSummary }>) {
  return (
    <article className="cert-product">
      <span className="cert-product-image">
        {listing.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={listing.image_url} alt="" />
        ) : (
          <b>{listing.retailer_id.slice(0, 1).toUpperCase()}</b>
        )}
      </span>
      <div>
        <small>
          {label(listing.retailer_id)} · {label(listing.brand_type)}
        </small>
        <strong>{listing.title || listing.retailer_product_id}</strong>
        <span>{listing.brand || "Brand unresolved"}</span>
        <code>{listing.retailer_product_id}</code>
        {listing.product_url ? (
          <a href={listing.product_url} target="_blank" rel="noreferrer">
            Open retailer product
          </a>
        ) : null}
      </div>
    </article>
  );
}

function defaultDraft(reviewCase: ReviewCase): ReviewDraft {
  return {
    verdict: reviewCase.engine_proposal.tier
      ? "comparable"
      : "insufficient_evidence",
    tier: reviewCase.engine_proposal.tier ?? "equivalent_product",
    rationale: "",
  };
}

export function MatchingV2ReviewAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [password, setPassword] = useState("");
  const [queues, setQueues] = useState<QueueSummary[]>([]);
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const [view, setView] = useState<QueueView | null>(null);
  const [reviewerId, setReviewerId] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [offset, setOffset] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadQueues = useCallback(async () => {
    const response = await jsonRequest<{
      queues: QueueSummary[];
    }>("/api/admin/matching-v2/review-queues?limit=100");
    setQueues(response.queues);
    setSelectedQueueId(
      (current) => current ?? response.queues[0]?.queue_id ?? null,
    );
  }, []);

  const loadQueue = useCallback(async () => {
    if (!selectedQueueId) return;
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (statusFilter !== "all") query.set("review_status", statusFilter);
    const response = await jsonRequest<QueueView>(
      `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId)}?${query}`,
    );
    setView(response);
    setDrafts((current) => {
      const next = { ...current };
      for (const reviewCase of response.cases) {
        next[reviewCase.case_id] ??= defaultDraft(reviewCase);
      }
      return next;
    });
  }, [offset, selectedQueueId, statusFilter]);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then((value) => {
        setSession(value);
        if (value.authenticated) return loadQueues();
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load admin access.",
        ),
      );
  }, [loadQueues]);

  useEffect(() => {
    // The state updates occur after the queue fetch resolves; this effect synchronizes
    // the selected server-backed queue whenever its filters change.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (session?.authenticated) void loadQueue().catch(handleError);
  }, [loadQueue, session?.authenticated]);

  const progress = useMemo(() => {
    if (!view) return 0;
    return view.total_cases
      ? ((view.status_counts.adjudicated ?? 0) / view.total_cases) * 100
      : 0;
  }, [view]);

  function handleError(cause: unknown) {
    setError(cause instanceof Error ? cause.message : "The request failed.");
  }

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
      await loadQueues();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function importQueue(file: File) {
    setBusy(true);
    setError(null);
    try {
      // Keep the queue as raw JSON until the Python API validates it. Parsing and
      // re-serializing here can round integers beyond JavaScript's safe range and
      // invalidate the queue's canonical checksum.
      const queueJson = await file.text();
      const response = await jsonRequest<{ queue_id: string }>(
        "/api/admin/matching-v2/review-queues/import",
        {
          method: "POST",
          body: JSON.stringify({
            organization_id: DEFAULT_ORGANIZATION_ID,
            imported_by: "authenticated-match-certification-admin",
            queue_json: queueJson,
          }),
        },
      );
      await loadQueues();
      setSelectedQueueId(response.queue_id);
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  function updateDraft(caseId: string, values: Partial<ReviewDraft>) {
    setDrafts((current) => ({
      ...current,
      [caseId]: { ...current[caseId], ...values },
    }));
  }

  async function submitReview(reviewCase: ReviewCase) {
    const draft = drafts[reviewCase.case_id];
    if (!reviewerId.trim()) {
      setError("Enter a stable reviewer identity before submitting a review.");
      return;
    }
    if (!draft?.rationale.trim()) {
      setError("Explain the evidence behind the review decision.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await jsonRequest(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/cases/${encodeURIComponent(reviewCase.case_id)}/submissions`,
        {
          method: "POST",
          body: JSON.stringify({
            reviewer_id: reviewerId.trim(),
            verdict: draft.verdict,
            allowed_tiers: draft.verdict === "comparable" ? [draft.tier] : [],
            rationale: draft.rationale,
            evidence_refs: reviewCase.evidence_refs,
          }),
        },
      );
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function finalizeConsensus(reviewCase: ReviewCase) {
    const reviews = reviewCase.review_submissions;
    const reviewers = new Set(reviews.map((review) => review.reviewer_id));
    if (reviewers.size < 2) {
      setError("Two independent reviewer submissions are required.");
      return;
    }
    const signatures = new Set(
      reviews.map(
        (review) =>
          `${review.verdict}:${[...review.allowed_tiers].sort().join(",")}`,
      ),
    );
    if (signatures.size !== 1) {
      setError("Reviewer decisions disagree and require manual adjudication.");
      return;
    }
    const consensus = reviews[0];
    setBusy(true);
    setError(null);
    try {
      await jsonRequest(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/cases/${encodeURIComponent(reviewCase.case_id)}/adjudications`,
        {
          method: "POST",
          body: JSON.stringify({
            adjudicator_id: reviewerId.trim() || "dual-review-consensus",
            verdict: consensus.verdict,
            allowed_tiers: consensus.allowed_tiers,
            rationale: `Independent reviewer consensus: ${reviews
              .map((review) => review.rationale)
              .join(" | ")}`,
            evidence_refs: reviewCase.evidence_refs,
            submission_ids: reviews.map((review) => review.id),
          }),
        },
      );
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  if (session === null)
    return (
      <div className="builder-loading">Checking administrator access…</div>
    );
  if (!session.authenticated) {
    return (
      <section className="admin-auth-card">
        <span className="section-kicker">Restricted workspace</span>
        <h2>Administrator authentication required</h2>
        <p>
          Certification decisions become durable release evidence and require
          the protected administrator session.
        </p>
        {session.configured ? (
          <form onSubmit={signIn}>
            <label>
              <span>Administrator password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? "Checking…" : "Open certification workbench"}
            </button>
          </form>
        ) : (
          <p className="form-error">
            Administrator sessions are not configured.
          </p>
        )}
        {error ? <p className="form-error">{error}</p> : null}
      </section>
    );
  }

  return (
    <section className="cert-workbench">
      <div className="cert-toolbar">
        <label>
          <span>Review queue</span>
          <select
            value={selectedQueueId ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              setSelectedQueueId(value || null);
              if (!value) setView(null);
              setOffset(0);
            }}
          >
            <option value="">Select a queue</option>
            {queues.map((queue) => (
              <option value={queue.queue_id} key={queue.queue_id}>
                {label(queue.product_pack.id)} · {queue.case_count} cases
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Queue status</span>
          <select
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value);
              setOffset(0);
            }}
          >
            <option value="pending">Pending</option>
            <option value="in_review">One review</option>
            <option value="ready_for_adjudication">Two reviews</option>
            <option value="adjudicated">Adjudicated</option>
            <option value="all">All cases</option>
          </select>
        </label>
        <label>
          <span>Current reviewer identity</span>
          <input
            value={reviewerId}
            onChange={(event) => setReviewerId(event.target.value)}
            placeholder="name@company.com"
          />
        </label>
        <label className="button secondary cert-file-button">
          {busy ? "Working…" : "Import review queue"}
          <input
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importQueue(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>

      {error ? <p className="form-error cert-error">{error}</p> : null}

      {view ? (
        <>
          <section className="cert-summary">
            <div>
              <small>Human release evidence</small>
              <h2>{label(view.queue.product_pack.id)}</h2>
              <p>
                Product Pack v{view.queue.product_pack.version} · queue v
                {view.queue.version}
              </p>
            </div>
            <div>
              <strong>{view.selected_case_count.toLocaleString()}</strong>
              <span>Cases matching this view</span>
            </div>
            <div>
              <strong>{view.status_counts.adjudicated ?? 0}</strong>
              <span>Adjudicated</span>
            </div>
            <div className="cert-progress">
              <span style={{ width: `${progress}%` }} />
              <small>{progress.toFixed(1)}% complete</small>
            </div>
            <a
              className="button secondary cert-gold-link"
              href={`/api/admin/matching-v2/review-queues/${encodeURIComponent(view.queue.queue_id)}/gold-set`}
              target="_blank"
              rel="noreferrer"
            >
              Open adjudicated gold set
            </a>
          </section>

          <div className="cert-case-list">
            {view.cases.map((reviewCase) => {
              const draft =
                drafts[reviewCase.case_id] ?? defaultDraft(reviewCase);
              return (
                <article className="cert-case" key={reviewCase.case_id}>
                  <header>
                    <div>
                      <small>{label(reviewCase.stratum)}</small>
                      <strong>{label(reviewCase.engine_proposal.tier)}</strong>
                    </div>
                    <span className={`cert-status ${reviewCase.review_status}`}>
                      {label(reviewCase.review_status)}
                    </span>
                    <em>
                      {Math.round(
                        reviewCase.engine_proposal.evidence_coverage
                          .critical_coverage * 100,
                      )}
                      % critical evidence
                    </em>
                  </header>
                  <div className="cert-product-pair">
                    <ProductIdentity listing={reviewCase.benchmark_listing} />
                    <span className="cert-pair-mark">compared with</span>
                    <ProductIdentity listing={reviewCase.competitor_listing} />
                  </div>
                  <p className="cert-engine-reason">
                    <b>Engine proposal:</b>{" "}
                    {reviewCase.engine_proposal.decision_reason}
                  </p>
                  <details className="cert-evidence">
                    <summary>Inspect attribute evidence</summary>
                    <div role="table">
                      <div role="row" className="cert-evidence-head">
                        <span>Attribute</span>
                        <span>Primary</span>
                        <span>Competitor</span>
                        <span>Outcome</span>
                      </div>
                      {reviewCase.edge.attribute_evidence.map((evidence) => (
                        <div role="row" key={evidence.attribute}>
                          <span>
                            <b>{label(evidence.attribute)}</b>
                            <small>{label(evidence.role)}</small>
                          </span>
                          <span>{evidenceValue(evidence.benchmark_value)}</span>
                          <span>
                            {evidenceValue(evidence.competitor_value)}
                          </span>
                          <span className={`evidence-${evidence.outcome}`}>
                            {label(evidence.outcome)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </details>

                  {reviewCase.review_submissions.length ? (
                    <div className="cert-review-history">
                      {reviewCase.review_submissions.map((review) => (
                        <span key={review.id}>
                          <b>{review.reviewer_id}</b>
                          {label(review.verdict)}
                          <small>{review.rationale}</small>
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {reviewCase.adjudication ? (
                    <p className="cert-final-decision">
                      <b>
                        Final decision: {label(reviewCase.adjudication.verdict)}
                      </b>
                      {reviewCase.adjudication.rationale}
                    </p>
                  ) : (
                    <div className="cert-review-form">
                      <label>
                        <span>Decision</span>
                        <select
                          value={draft.verdict}
                          onChange={(event) =>
                            updateDraft(reviewCase.case_id, {
                              verdict: event.target
                                .value as ReviewDraft["verdict"],
                            })
                          }
                        >
                          <option value="comparable">Comparable</option>
                          <option value="not_comparable">Not comparable</option>
                          <option value="insufficient_evidence">
                            Insufficient evidence
                          </option>
                        </select>
                      </label>
                      <label>
                        <span>Approved tier</span>
                        <select
                          value={draft.tier}
                          disabled={draft.verdict !== "comparable"}
                          onChange={(event) =>
                            updateDraft(reviewCase.case_id, {
                              tier: event.target.value,
                            })
                          }
                        >
                          {TIERS.map((tier) => (
                            <option value={tier} key={tier}>
                              {label(tier)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="cert-rationale">
                        <span>Evidence rationale</span>
                        <textarea
                          value={draft.rationale}
                          onChange={(event) =>
                            updateDraft(reviewCase.case_id, {
                              rationale: event.target.value,
                            })
                          }
                          placeholder="Explain the package, claims, identity, and conflicts that support this decision."
                        />
                      </label>
                      <button
                        className="button primary"
                        type="button"
                        disabled={busy}
                        onClick={() => void submitReview(reviewCase)}
                      >
                        Submit independent review
                      </button>
                      {reviewCase.review_status === "ready_for_adjudication" ? (
                        <button
                          className="button secondary"
                          type="button"
                          disabled={busy}
                          onClick={() => void finalizeConsensus(reviewCase)}
                        >
                          Finalize reviewer consensus
                        </button>
                      ) : null}
                    </div>
                  )}
                </article>
              );
            })}
            {view.cases.length === 0 ? (
              <section className="cert-empty">
                <h2>No cases match this status</h2>
                <p>Select another queue status or import a new review queue.</p>
              </section>
            ) : null}
          </div>
          {view.selected_case_count > PAGE_SIZE ? (
            <nav className="cert-pagination" aria-label="Review queue pages">
              <button
                className="button secondary"
                type="button"
                disabled={busy || offset === 0}
                onClick={() =>
                  setOffset((current) => Math.max(0, current - PAGE_SIZE))
                }
              >
                Previous cases
              </button>
              <span>
                {offset + 1}–
                {Math.min(offset + PAGE_SIZE, view.selected_case_count)} of{" "}
                {view.selected_case_count.toLocaleString()}
              </span>
              <button
                className="button secondary"
                type="button"
                disabled={
                  busy || offset + PAGE_SIZE >= view.selected_case_count
                }
                onClick={() => setOffset((current) => current + PAGE_SIZE)}
              >
                Next cases
              </button>
            </nav>
          ) : null}
        </>
      ) : (
        <section className="cert-empty">
          <h2>No review queue selected</h2>
          <p>
            Import one of the validated Matching v2 queue JSON files to begin.
          </p>
        </section>
      )}
    </section>
  );
}
