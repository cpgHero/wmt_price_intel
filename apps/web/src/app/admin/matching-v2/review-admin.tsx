"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
  brand_governance?: Record<string, unknown>;
  seller_governance?: Record<string, unknown>;
  pdp_evidence?: Record<string, unknown>;
  observed_location_count?: number;
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

type AIDraftStatus = "queued" | "running" | "succeeded" | "needs_review";

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
  ai_draft?: null | {
    id: string;
    status: AIDraftStatus;
    model_id: string;
    requested_by: string;
    output_document?: {
      authoritative: false;
      human_review_required: true;
      result: {
        verdict_proposal:
          "comparable" | "not_comparable" | "insufficient_evidence";
        tier_proposal: string | null;
        rationale: string;
        attribute_proposals: Array<{
          attribute: string;
          value: string;
          evidence_source: "structured" | "image";
          confidence: number;
          visible_text: string | null;
          source_image_url: string | null;
        }>;
        conflicts: string[];
        requires_human_review: true;
      };
    };
    usage?: {
      estimated_cost_usd?: number | null;
    };
    last_error_message?: string | null;
  };
}

interface QueueView {
  authoritative: false;
  queue: QueueSummary;
  ai_review_policy?: {
    enabled: boolean;
    model_id: string | null;
    max_batch_cases: number;
    max_request_cost_usd: number;
    vision_policy: string;
    authoritative: false;
    human_review_required: true;
  };
  status_counts: Record<string, number>;
  competitor_retailers: Array<{
    retailer_id: string;
    case_count: number;
  }>;
  total_cases: number;
  selected_case_count: number;
  offset: number;
  limit: number;
  cases: ReviewCase[];
}

interface ReviewDraft {
  verdict: "" | "comparable" | "not_comparable" | "insufficient_evidence";
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
const DISABLED_AI_POLICY: NonNullable<QueueView["ai_review_policy"]> = {
  enabled: false,
  model_id: null,
  max_batch_cases: 25,
  max_request_cost_usd: 0,
  vision_policy: "missing_or_conflicting_critical_evidence_only",
  authoritative: false,
  human_review_required: true,
};

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const payload = await response.text();
  let body: (T & {
    error?: string;
    detail?: string;
  }) | null = null;
  if (payload) {
    try {
      body = JSON.parse(payload) as T & { error?: string; detail?: string };
    } catch {
      if (!response.ok) {
        throw new Error(
          `${payload.trim() || "The server returned an invalid response."} (${response.status})`,
        );
      }
      throw new Error("The server returned an invalid JSON response.");
    }
  }
  if (!response.ok)
    throw new Error(
      body?.error ?? body?.detail ?? `Request failed (${response.status})`,
    );
  if (body === null) throw new Error("The server returned an empty response.");
  return body;
}

function label(value: string | null | undefined) {
  if (!value) return "Unresolved";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function aiDraftStatusLabel(status: AIDraftStatus) {
  switch (status) {
    case "queued":
      return "AI queued";
    case "running":
      return "AI reviewing";
    case "succeeded":
      return "AI draft ready";
    case "needs_review":
      return "AI needs attention";
  }
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
        {listing.observed_location_count !== undefined ? (
          <span>
            {listing.observed_location_count.toLocaleString()} observed {" "}
            {listing.retailer_id === "amazon_us_same_day"
              ? "ZIPs"
              : "stores/locations"}
          </span>
        ) : null}
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
    verdict: "",
    tier: reviewCase.engine_proposal.tier ?? "equivalent_product",
    rationale: "",
  };
}

export function MatchingV2ReviewAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [password, setPassword] = useState("");
  const [queues, setQueues] = useState<QueueSummary[]>([]);
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const [queueRefresh, setQueueRefresh] = useState(0);
  const [view, setView] = useState<QueueView | null>(null);
  const [reviewerId, setReviewerId] = useState("");
  const [competitorFilter, setCompetitorFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [offset, setOffset] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [batchConfirmOpen, setBatchConfirmOpen] = useState(false);
  const [refreshingAI, setRefreshingAI] = useState(false);
  const reviewerInputRef = useRef<HTMLInputElement>(null);

  const loadQueues = useCallback(async () => {
    const response = await jsonRequest<{
      queues: QueueSummary[];
    }>("/api/admin/matching-v2/review-queues?limit=100");
    const latestQueues = response.queues.filter(
      (queue, index, allQueues) =>
        allQueues.findIndex(
          (candidate) => candidate.queue_id === queue.queue_id,
        ) === index,
    );
    setQueues(latestQueues);
    setSelectedQueueId(
      (current) => current ?? latestQueues[0]?.queue_id ?? null,
    );
  }, []);

  const loadQueue = useCallback(async () => {
    if (!selectedQueueId) return;
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (competitorFilter !== "all") {
      query.set("competitor_retailer_id", competitorFilter);
    }
    if (statusFilter !== "all") query.set("review_status", statusFilter);
    const response = await jsonRequest<QueueView>(
      `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId)}?${query}`,
    );
    setView(response);
    setActiveCaseId((current) =>
      current &&
      response.cases.some((reviewCase) => reviewCase.case_id === current)
        ? current
        : null,
    );
    setDrafts((current) => {
      const next = { ...current };
      for (const reviewCase of response.cases) {
        next[reviewCase.case_id] ??= defaultDraft(reviewCase);
      }
      return next;
    });
    setSelectedCaseIds((current) =>
      current.filter((caseId) =>
        response.cases.some(
          (reviewCase) =>
            reviewCase.case_id === caseId &&
            !reviewCase.adjudication &&
            !reviewCase.ai_draft,
        ),
      ),
    );
  }, [competitorFilter, offset, selectedQueueId, statusFilter]);

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
  }, [loadQueue, queueRefresh, session?.authenticated]);

  useEffect(() => {
    if (!activeCaseId) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActiveCaseId(null);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [activeCaseId]);

  const progress = useMemo(() => {
    if (!view) return 0;
    return view.total_cases
      ? ((view.status_counts.adjudicated ?? 0) / view.total_cases) * 100
      : 0;
  }, [view]);
  const activeCase = useMemo(
    () =>
      view?.cases.find((reviewCase) => reviewCase.case_id === activeCaseId) ??
      null,
    [activeCaseId, view],
  );
  const eligibleCases = useMemo(
    () =>
      (view?.cases ?? []).filter(
        (reviewCase) => !reviewCase.adjudication && !reviewCase.ai_draft,
      ),
    [view],
  );
  const aiPolicy = view?.ai_review_policy ?? DISABLED_AI_POLICY;
  const selectedMaximumCost = useMemo(
    () => selectedCaseIds.length * aiPolicy.max_request_cost_usd,
    [aiPolicy.max_request_cost_usd, selectedCaseIds.length],
  );
  const hasRunningAIDrafts = useMemo(
    () =>
      (view?.cases ?? []).some((reviewCase) =>
        ["queued", "running"].includes(reviewCase.ai_draft?.status ?? ""),
      ),
    [view],
  );
  const aiDraftStatusCounts = useMemo(() => {
    const counts: Record<AIDraftStatus, number> = {
      queued: 0,
      running: 0,
      succeeded: 0,
      needs_review: 0,
    };
    for (const reviewCase of view?.cases ?? []) {
      if (reviewCase.ai_draft) counts[reviewCase.ai_draft.status] += 1;
    }
    return counts;
  }, [view]);
  const visibleAIDraftCount = Object.values(aiDraftStatusCounts).reduce(
    (total, count) => total + count,
    0,
  );

  useEffect(() => {
    if (!hasRunningAIDrafts) return;
    const timer = window.setTimeout(
      () => void loadQueue().catch(handleError),
      2000,
    );
    return () => window.clearTimeout(timer);
  }, [hasRunningAIDrafts, loadQueue]);

  function handleError(cause: unknown) {
    setNotice(null);
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
      setQueueRefresh((current) => current + 1);
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
    if (!draft.verdict) {
      setError("Choose an explicit review decision before submitting.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
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
      setNotice(
        "Independent review submitted. A second reviewer must submit separately before adjudication.",
      );
      setActiveCaseId(null);
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function requestAIReview(reviewCase: ReviewCase) {
    if (!reviewerId.trim()) {
      setError("Enter your reviewer identity before requesting an AI draft.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await jsonRequest(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/cases/${encodeURIComponent(reviewCase.case_id)}/ai-drafts`,
        {
          method: "POST",
          body: JSON.stringify({ requested_by: reviewerId.trim() }),
        },
      );
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function requestSelectedAIReviews() {
    if (!reviewerId.trim()) {
      setError("Enter your reviewer identity before requesting AI drafts.");
      return;
    }
    if (!selectedCaseIds.length) {
      setError("Select at least one eligible case for AI evidence review.");
      return;
    }
    if (selectedCaseIds.length > aiPolicy.max_batch_cases) {
      setError(
        `Select no more than ${aiPolicy.max_batch_cases} cases per batch.`,
      );
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const requestedCount = selectedCaseIds.length;
    try {
      await jsonRequest(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/ai-drafts`,
        {
          method: "POST",
          body: JSON.stringify({
            requested_by: reviewerId.trim(),
            case_ids: selectedCaseIds,
          }),
        },
      );
      setBatchConfirmOpen(false);
      setSelectedCaseIds([]);
      setNotice(
        `${requestedCount} AI review ${requestedCount === 1 ? "draft was" : "drafts were"} accepted. Status refreshes automatically while the work is queued or running.`,
      );
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  function openBatchConfirmation() {
    if (!reviewerId.trim()) {
      setError(
        "Enter your reviewer identity before reviewing selected cases with AI.",
      );
      reviewerInputRef.current?.focus();
      return;
    }
    setError(null);
    setNotice(null);
    setBatchConfirmOpen(true);
  }

  async function refreshAIStatus() {
    setRefreshingAI(true);
    setError(null);
    try {
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setRefreshingAI(false);
    }
  }

  function adoptAIProposal(reviewCase: ReviewCase) {
    const proposal = reviewCase.ai_draft?.output_document?.result;
    if (!proposal) return;
    updateDraft(reviewCase.case_id, {
      verdict: proposal.verdict_proposal,
      tier: proposal.tier_proposal ?? "equivalent_product",
      rationale: `AI draft considered; independently reviewed by ${reviewerId.trim() || "human reviewer"}. ${proposal.rationale}`,
    });
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
              setCompetitorFilter("all");
              setOffset(0);
              setSelectedCaseIds([]);
              setBatchConfirmOpen(false);
            }}
          >
            <option value="">Select a queue</option>
            {queues.map((queue) => (
              <option value={queue.queue_id} key={queue.queue_id}>
                {label(queue.product_pack.id)} · queue v{queue.version} ·{" "}
                {queue.case_count} cases
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Competitor retailer</span>
          <select
            value={competitorFilter}
            onChange={(event) => {
              setCompetitorFilter(event.target.value);
              setOffset(0);
              setSelectedCaseIds([]);
              setBatchConfirmOpen(false);
            }}
          >
            <option value="all">All competitor retailers</option>
            {(view?.competitor_retailers ?? []).map((retailer) => (
              <option value={retailer.retailer_id} key={retailer.retailer_id}>
                {label(retailer.retailer_id)} · {retailer.case_count} cases
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
              setSelectedCaseIds([]);
              setBatchConfirmOpen(false);
            }}
          >
            <option value="pending">Pending</option>
            <option value="in_review">One review</option>
            <option value="ready_for_adjudication">Two reviews</option>
            <option value="adjudicated">Adjudicated</option>
            <option value="all">All cases</option>
          </select>
        </label>
        <label className="cert-reviewer-field">
          <span>Current reviewer identity</span>
          <input
            ref={reviewerInputRef}
            value={reviewerId}
            onChange={(event) => {
              setReviewerId(event.target.value);
              if (event.target.value.trim()) setError(null);
            }}
            placeholder="name@company.com"
          />
          <small>Required for human reviews and AI-assisted drafts.</small>
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

      {error ? (
        <p className="form-error cert-error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="cert-notice" role="status">
          {notice}
        </p>
      ) : null}

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

          <section
            className="cert-ai-batch"
            aria-labelledby="cert-ai-batch-title"
          >
            <div>
              <small>Bounded evidence assistance</small>
              <h3 id="cert-ai-batch-title">
                AI review drafts for selected cases
              </h3>
              <p>
                Select up to {aiPolicy.max_batch_cases} cases from this filtered
                page. Drafts remain advisory, cannot certify a match, and use
                product images only when critical structured evidence is
                incomplete or conflicting.
              </p>
            </div>
            <label className="cert-ai-select-all">
              <input
                type="checkbox"
                checked={
                  eligibleCases.length > 0 &&
                  selectedCaseIds.length ===
                    Math.min(eligibleCases.length, aiPolicy.max_batch_cases)
                }
                disabled={!aiPolicy.enabled || !eligibleCases.length}
                onChange={(event) => {
                  setSelectedCaseIds(
                    event.target.checked
                      ? eligibleCases
                          .slice(0, aiPolicy.max_batch_cases)
                          .map((reviewCase) => reviewCase.case_id)
                      : [],
                  );
                  setBatchConfirmOpen(false);
                }}
              />
              <span>
                Select eligible cases on this page
                <small>
                  {eligibleCases.length.toLocaleString()} without an existing
                  draft or adjudication
                </small>
              </span>
            </label>
            <div className="cert-ai-batch-actions">
              <span>
                <strong>{selectedCaseIds.length}</strong> selected
                {selectedCaseIds.length ? (
                  <>
                    <small>
                      Maximum policy exposure: ${selectedMaximumCost.toFixed(2)}
                    </small>
                    {!reviewerId.trim() ? (
                      <small className="cert-ai-requirement" role="status">
                        Enter your reviewer identity above to continue.
                      </small>
                    ) : null}
                  </>
                ) : null}
              </span>
              <button
                className="button secondary"
                type="button"
                disabled={busy || !aiPolicy.enabled || !selectedCaseIds.length}
                aria-busy={busy}
                onClick={openBatchConfirmation}
              >
                {selectedCaseIds.length
                  ? `Review ${selectedCaseIds.length} selected with AI`
                  : "Review selected with AI"}
              </button>
            </div>
            <div className="cert-ai-status-summary" aria-live="polite">
              <div>
                <span className="queued">
                  <i aria-hidden="true" />
                  <strong>{aiDraftStatusCounts.queued}</strong> queued
                </span>
                <span className="running">
                  <i aria-hidden="true" />
                  <strong>{aiDraftStatusCounts.running}</strong> reviewing
                </span>
                <span className="succeeded">
                  <i aria-hidden="true" />
                  <strong>{aiDraftStatusCounts.succeeded}</strong> drafts ready
                </span>
                <span className="needs-review">
                  <i aria-hidden="true" />
                  <strong>{aiDraftStatusCounts.needs_review}</strong> needs
                  attention
                </span>
              </div>
              <p>
                {hasRunningAIDrafts
                  ? "Status refreshes automatically while AI work is queued or running."
                  : visibleAIDraftCount
                    ? "Open Review evidence on a ready case to inspect and independently decide the match."
                    : "No AI drafts are recorded on this filtered page yet."}
              </p>
              <button
                className="button secondary"
                type="button"
                disabled={refreshingAI}
                aria-busy={refreshingAI}
                onClick={() => void refreshAIStatus()}
              >
                {refreshingAI ? "Refreshing…" : "Refresh AI status"}
              </button>
            </div>
            {!aiPolicy.enabled ? (
              <p className="cert-ai-policy-note">
                The advisory worker is not enabled in this environment. Human
                certification remains available.
              </p>
            ) : null}
            {batchConfirmOpen ? (
              <div className="cert-ai-batch-confirm" role="alert">
                <div>
                  <strong>
                    Queue {selectedCaseIds.length} advisory drafts?
                  </strong>
                  <p>
                    Model: {aiPolicy.model_id}. The configured per-request
                    ceiling is ${aiPolicy.max_request_cost_usd.toFixed(2)};
                    actual usage is recorded per case. Human review is still
                    required for every decision.
                  </p>
                </div>
                <button
                  className="button secondary"
                  type="button"
                  disabled={busy}
                  onClick={() => setBatchConfirmOpen(false)}
                >
                  Cancel
                </button>
                <button
                  className="button primary"
                  type="button"
                  disabled={busy}
                  aria-busy={busy}
                  onClick={() => void requestSelectedAIReviews()}
                >
                  {busy ? "Queueing…" : "Confirm advisory review"}
                </button>
              </div>
            ) : null}
          </section>

          <div className="cert-case-list">
            {view.cases.map((reviewCase) => (
              <article
                className="cert-case cert-case-compact"
                key={reviewCase.case_id}
              >
                <label className="cert-case-select">
                  <input
                    type="checkbox"
                    aria-label={`Select ${reviewCase.benchmark_listing.title ?? reviewCase.benchmark_listing.retailer_product_id} versus ${reviewCase.competitor_listing.title ?? reviewCase.competitor_listing.retailer_product_id} for AI evidence review`}
                    checked={selectedCaseIds.includes(reviewCase.case_id)}
                    disabled={
                      !aiPolicy.enabled ||
                      Boolean(reviewCase.adjudication) ||
                      Boolean(reviewCase.ai_draft)
                    }
                    onChange={(event) => {
                      setSelectedCaseIds((current) =>
                        event.target.checked
                          ? current.length < aiPolicy.max_batch_cases
                            ? [...current, reviewCase.case_id]
                            : current
                          : current.filter(
                              (caseId) => caseId !== reviewCase.case_id,
                            ),
                      );
                      setBatchConfirmOpen(false);
                    }}
                  />
                  <span>
                    {reviewCase.ai_draft
                      ? aiDraftStatusLabel(reviewCase.ai_draft.status)
                      : reviewCase.adjudication
                        ? "Adjudicated"
                        : "Select for AI"}
                  </span>
                </label>
                <div className="cert-case-products">
                  <ProductIdentity listing={reviewCase.benchmark_listing} />
                  <span className="cert-pair-mark">versus</span>
                  <ProductIdentity listing={reviewCase.competitor_listing} />
                </div>
                <div className="cert-case-meta">
                  <span className={`cert-status ${reviewCase.review_status}`}>
                    {label(reviewCase.review_status)}
                  </span>
                  <strong>{label(reviewCase.engine_proposal.tier)}</strong>
                  <small>
                    {Math.round(
                      reviewCase.engine_proposal.evidence_coverage
                        .critical_coverage * 100,
                    )}
                    % critical evidence
                  </small>
                </div>
                <button
                  className="button secondary"
                  type="button"
                  onClick={() => setActiveCaseId(reviewCase.case_id)}
                >
                  Review evidence
                </button>
              </article>
            ))}
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
                onClick={() => {
                  setOffset((current) => Math.max(0, current - PAGE_SIZE));
                  setSelectedCaseIds([]);
                  setBatchConfirmOpen(false);
                }}
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
                onClick={() => {
                  setOffset((current) => current + PAGE_SIZE);
                  setSelectedCaseIds([]);
                  setBatchConfirmOpen(false);
                }}
              >
                Next cases
              </button>
            </nav>
          ) : null}
          {activeCase ? (
            <div
              className="cert-drawer-backdrop"
              role="presentation"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) setActiveCaseId(null);
              }}
            >
              <aside
                className="cert-drawer"
                role="dialog"
                aria-modal="true"
                aria-labelledby="cert-drawer-title"
              >
                <header className="cert-drawer-header">
                  <div>
                    <small>{label(activeCase.stratum)}</small>
                    <h2 id="cert-drawer-title">Match evidence review</h2>
                    <p>
                      Engine suggestion:{" "}
                      {label(activeCase.engine_proposal.tier)}. The reviewer
                      must make an independent decision.
                    </p>
                  </div>
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() => setActiveCaseId(null)}
                    aria-label="Close evidence drawer"
                  >
                    Close
                  </button>
                </header>
                <div className="cert-drawer-body">
                  <div className="cert-product-pair">
                    <ProductIdentity listing={activeCase.benchmark_listing} />
                    <span className="cert-pair-mark">compared with</span>
                    <ProductIdentity listing={activeCase.competitor_listing} />
                  </div>
                  <p className="cert-engine-reason">
                    <b>Why the engine surfaced this pair:</b>{" "}
                    {activeCase.engine_proposal.decision_reason}
                  </p>
                  <section className="cert-ai-draft">
                    <header>
                      <div>
                        <small>Advisory evidence assistant</small>
                        <h3>AI draft review</h3>
                        <p>
                          The draft can inspect incomplete label evidence, but
                          it cannot approve a relationship or alter reporting.
                        </p>
                      </div>
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy || Boolean(activeCase.ai_draft)}
                        onClick={() => void requestAIReview(activeCase)}
                      >
                        {activeCase.ai_draft
                          ? `AI ${label(activeCase.ai_draft.status)}`
                          : "Run AI evidence review"}
                      </button>
                    </header>
                    {activeCase.ai_draft ? (
                      <div className="cert-ai-result">
                        <span
                          className={`cert-status ${activeCase.ai_draft.status}`}
                        >
                          {label(activeCase.ai_draft.status)}
                        </span>
                        <small>{activeCase.ai_draft.model_id}</small>
                        {activeCase.ai_draft.output_document?.result ? (
                          <>
                            <strong>
                              Proposed:{" "}
                              {label(
                                activeCase.ai_draft.output_document.result
                                  .verdict_proposal,
                              )}
                              {activeCase.ai_draft.output_document.result
                                .tier_proposal
                                ? ` · ${label(activeCase.ai_draft.output_document.result.tier_proposal)}`
                                : ""}
                            </strong>
                            <p>
                              {
                                activeCase.ai_draft.output_document.result
                                  .rationale
                              }
                            </p>
                            {activeCase.ai_draft.output_document.result
                              .conflicts.length ? (
                              <ul>
                                {activeCase.ai_draft.output_document.result.conflicts.map(
                                  (conflict) => (
                                    <li key={conflict}>{conflict}</li>
                                  ),
                                )}
                              </ul>
                            ) : null}
                            {activeCase.ai_draft.output_document.result
                              .attribute_proposals.length ? (
                              <details>
                                <summary>Inspect proposed attributes</summary>
                                <dl>
                                  {activeCase.ai_draft.output_document.result.attribute_proposals.map(
                                    (proposal) => (
                                      <div
                                        key={`${proposal.attribute}-${proposal.value}`}
                                      >
                                        <dt>{label(proposal.attribute)}</dt>
                                        <dd>
                                          {proposal.value} ·{" "}
                                          {label(proposal.evidence_source)} ·{" "}
                                          {Math.round(
                                            proposal.confidence * 100,
                                          )}
                                          % confidence
                                          {proposal.visible_text ? (
                                            <small>
                                              Visible evidence: “
                                              {proposal.visible_text}”
                                            </small>
                                          ) : null}
                                          {proposal.source_image_url ? (
                                            <a
                                              href={proposal.source_image_url}
                                              target="_blank"
                                              rel="noreferrer"
                                            >
                                              Open cited product image
                                            </a>
                                          ) : null}
                                        </dd>
                                      </div>
                                    ),
                                  )}
                                </dl>
                              </details>
                            ) : null}
                            <button
                              className="button secondary"
                              type="button"
                              onClick={() => adoptAIProposal(activeCase)}
                            >
                              Copy proposal into my review
                            </button>
                            {activeCase.ai_draft.usage?.estimated_cost_usd !=
                            null ? (
                              <small>
                                Recorded estimated cost: $
                                {activeCase.ai_draft.usage.estimated_cost_usd.toFixed(
                                  4,
                                )}
                              </small>
                            ) : null}
                          </>
                        ) : activeCase.ai_draft.last_error_message ? (
                          <p>{activeCase.ai_draft.last_error_message}</p>
                        ) : (
                          <p>The worker is preparing this advisory draft.</p>
                        )}
                      </div>
                    ) : null}
                  </section>
                  <section className="cert-governance-grid">
                    {[
                      activeCase.benchmark_listing,
                      activeCase.competitor_listing,
                    ].map((listing) => (
                      <article key={listing.listing_id}>
                        <small>{label(listing.retailer_id)} governance</small>
                        <dl>
                          <div>
                            <dt>Brand</dt>
                            <dd>{listing.brand || "Unresolved"}</dd>
                          </div>
                          <div>
                            <dt>Brand status</dt>
                            <dd>
                              {label(
                                String(
                                  listing.brand_governance?.status ??
                                    "unresolved",
                                ),
                              )}
                            </dd>
                          </div>
                          <div>
                            <dt>PDP seller</dt>
                            <dd>
                              {evidenceValue(
                                listing.seller_governance?.observed_seller,
                              )}
                            </dd>
                          </div>
                          <div>
                            <dt>Seller eligibility</dt>
                            <dd>
                              {label(
                                String(
                                  listing.seller_governance?.status ??
                                    "not governed",
                                ),
                              )}
                            </dd>
                          </div>
                        </dl>
                      </article>
                    ))}
                  </section>
                  <section className="cert-evidence">
                    <h3>Attribute evidence</h3>
                    <div role="table">
                      <div role="row" className="cert-evidence-head">
                        <span>Attribute</span>
                        <span>Primary</span>
                        <span>Competitor</span>
                        <span>Outcome</span>
                      </div>
                      {activeCase.edge.attribute_evidence.map((evidence) => (
                        <div role="row" key={evidence.attribute}>
                          <span data-label="Attribute">
                            <b>{label(evidence.attribute)}</b>
                            <small>{label(evidence.role)}</small>
                          </span>
                          <span data-label="Primary">
                            {evidenceValue(evidence.benchmark_value)}
                          </span>
                          <span data-label="Competitor">
                            {evidenceValue(evidence.competitor_value)}
                          </span>
                          <span
                            className={`evidence-${evidence.outcome}`}
                            data-label="Outcome"
                          >
                            {label(evidence.outcome)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                  <details className="cert-pdp-evidence">
                    <summary>Product Details evidence</summary>
                    <div>
                      {[
                        activeCase.benchmark_listing,
                        activeCase.competitor_listing,
                      ].map((listing) => (
                        <article key={listing.listing_id}>
                          <strong>{label(listing.retailer_id)}</strong>
                          <pre>
                            {Object.keys(listing.pdp_evidence ?? {}).length
                              ? JSON.stringify(listing.pdp_evidence, null, 2)
                              : "No PDP evidence is attached to this queue version."}
                          </pre>
                        </article>
                      ))}
                    </div>
                  </details>
                  {activeCase.review_submissions.length ? (
                    <div className="cert-review-history">
                      {activeCase.review_submissions.map((review) => (
                        <span key={review.id}>
                          <b>{review.reviewer_id}</b>
                          {label(review.verdict)}
                          <small>{review.rationale}</small>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <footer className="cert-drawer-footer">
                  {activeCase.adjudication ? (
                    <p className="cert-final-decision">
                      <b>
                        Final decision: {label(activeCase.adjudication.verdict)}
                      </b>
                      {activeCase.adjudication.rationale}
                    </p>
                  ) : (
                    <div className="cert-review-form cert-review-form-drawer">
                      <fieldset>
                        <legend>Independent decision</legend>
                        {(
                          [
                            ["comparable", "Approve match"],
                            ["not_comparable", "Reject match"],
                            ["insufficient_evidence", "Needs evidence"],
                          ] as const
                        ).map(([verdict, text]) => (
                          <button
                            className={
                              drafts[activeCase.case_id]?.verdict === verdict
                                ? "selected"
                                : ""
                            }
                            type="button"
                            key={verdict}
                            onClick={() =>
                              updateDraft(activeCase.case_id, { verdict })
                            }
                          >
                            {text}
                          </button>
                        ))}
                      </fieldset>
                      <label>
                        <span>Approved tier</span>
                        <select
                          value={
                            drafts[activeCase.case_id]?.tier ??
                            defaultDraft(activeCase).tier
                          }
                          disabled={
                            drafts[activeCase.case_id]?.verdict !== "comparable"
                          }
                          onChange={(event) =>
                            updateDraft(activeCase.case_id, {
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
                          value={drafts[activeCase.case_id]?.rationale ?? ""}
                          onChange={(event) =>
                            updateDraft(activeCase.case_id, {
                              rationale: event.target.value,
                            })
                          }
                          placeholder="Explain the product identity, package, claims, and any conflicts."
                        />
                      </label>
                      <button
                        className="button primary"
                        type="button"
                        disabled={busy}
                        onClick={() => void submitReview(activeCase)}
                      >
                        Submit independent review
                      </button>
                      {activeCase.review_status === "ready_for_adjudication" ? (
                        <button
                          className="button secondary"
                          type="button"
                          disabled={busy}
                          onClick={() => void finalizeConsensus(activeCase)}
                        >
                          Finalize reviewer consensus
                        </button>
                      ) : null}
                    </div>
                  )}
                </footer>
              </aside>
            </div>
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
