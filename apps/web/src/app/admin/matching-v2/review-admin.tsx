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
  created_at?: string;
}

interface FinalDecision extends ReviewSubmission {
  source: "review_submission" | "legacy_adjudication";
}

type AIDraftStatus = "queued" | "running" | "succeeded" | "needs_review";

interface AIReviewBatchSummary {
  id: string;
  requested_by: string;
  model_id: string;
  requested_case_count: number;
  task_count: number;
  queued: number;
  running: number;
  succeeded: number;
  needs_review: number;
  completed_count: number;
  progress_percent: number;
  estimated_seconds_remaining: number | null;
  estimated_cost_usd: number;
  submitted_at: string;
  started_at: string | null;
  last_activity_at: string | null;
  completed_at: string | null;
}

interface AIReviewSummary {
  active_task_count: number;
  status_counts: Record<AIDraftStatus, number>;
  latest_batch: AIReviewBatchSummary | null;
}

interface AIBulkCertificationPolicy {
  id: string;
  version: string;
  max_cases: number;
  allowed_tiers: string[];
  minimum_critical_coverage: number;
  minimum_ai_attribute_confidence: number;
  checksum: string;
  human_confirmation_required: true;
  automatically_changes_reporting: false;
}

interface AIBulkCertificationCandidate {
  case_id: string;
  eligible: boolean;
  reason_codes: string[];
  reasons: string[];
  recommended_tier: string | null;
  critical_coverage: number;
  engine_status: string | null;
  ai_task_id: string | null;
  ai_rationale: string | null;
  benchmark_product: {
    retailer_id: string;
    retailer_product_id: string;
    title: string | null;
    brand: string | null;
    image_url: string | null;
    observed_location_count: number;
  };
  competitor_product: {
    retailer_id: string;
    retailer_product_id: string;
    title: string | null;
    brand: string | null;
    image_url: string | null;
    observed_location_count: number;
  };
}

interface AIBulkCertificationPreview {
  queue_id: string;
  queue_version: string;
  policy: AIBulkCertificationPolicy;
  requested_case_count: number;
  eligible_case_count: number;
  excluded_case_count: number;
  eligible_cases: AIBulkCertificationCandidate[];
  excluded_cases: AIBulkCertificationCandidate[];
  exclusion_summary: Array<{
    reason_code: string;
    reason: string;
    case_count: number;
  }>;
  confirmation_checksum: string | null;
  human_confirmation_required: true;
  final_until_flagged: true;
  automatically_changes_reporting: false;
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
  final_decision: FinalDecision | null;
  adjudication: null | {
    verdict: string;
    allowed_tiers: string[];
    rationale: string;
  };
  ai_draft?: null | {
    id: string;
    batch_id: string;
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
    attempt_count: number;
    max_attempts: number;
    retry_of_task_id?: string | null;
    retry_sequence?: number;
    retry_reason?: string | null;
    last_error_type?: string | null;
    last_error_message?: string | null;
    created_at: string;
    updated_at: string;
    completed_at?: string | null;
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
    max_retry_rounds: number;
    retryable_statuses: AIDraftStatus[];
    retry_preserves_history: boolean;
    retry_blocks_integrity_failures: boolean;
    vision_policy: string;
    authoritative: false;
    human_review_required: true;
  };
  ai_review_summary?: AIReviewSummary;
  ai_bulk_certification_policy?: AIBulkCertificationPolicy;
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
  max_retry_rounds: 3,
  retryable_statuses: ["needs_review"],
  retry_preserves_history: true,
  retry_blocks_integrity_failures: true,
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
  let body:
    | (T & {
        error?: string;
        detail?: string;
      })
    | null = null;
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

function _isRetryIntegrityFailure(message: string | null | undefined) {
  return String(message ?? "")
    .toLowerCase()
    .includes("does not match governed input or prompt");
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Not started";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return "Calculating after the first draft finishes";
  if (seconds < 60) return "Less than a minute";
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `About ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `About ${hours} hr${hours === 1 ? "" : "s"}${remainder ? ` ${remainder} min` : ""}`;
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
            {listing.observed_location_count.toLocaleString()} observed{" "}
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

function BulkProductIdentity({
  product,
}: Readonly<{
  product: AIBulkCertificationCandidate["benchmark_product"];
}>) {
  return (
    <span className="cert-bulk-product">
      <span className="cert-bulk-product-image">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt="" />
        ) : (
          <b>
            {String(product.retailer_id || "?")
              .slice(0, 1)
              .toUpperCase()}
          </b>
        )}
      </span>
      <span>
        <small>{label(product.retailer_id)}</small>
        <strong>{product.title || product.retailer_product_id}</strong>
        <small>
          {product.brand || "Brand unresolved"} ·{" "}
          {product.observed_location_count.toLocaleString()} observed
        </small>
      </span>
    </span>
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
  const [retryConfirmCaseIds, setRetryConfirmCaseIds] = useState<string[]>([]);
  const [retryConfirmationPlacement, setRetryConfirmationPlacement] = useState<
    "batch" | "drawer" | null
  >(null);
  const [bulkCertificationPreview, setBulkCertificationPreview] =
    useState<AIBulkCertificationPreview | null>(null);
  const [refreshingAI, setRefreshingAI] = useState(false);
  const reviewerInputRef = useRef<HTMLInputElement>(null);
  const queueRequestSequence = useRef(0);

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
    const requestSequence = ++queueRequestSequence.current;
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
    if (requestSequence !== queueRequestSequence.current) return;
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
            ["pending", "flagged"].includes(reviewCase.review_status) &&
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
    if (session?.authenticated) void loadQueue().catch(handleError);
  }, [loadQueue, queueRefresh, session?.authenticated]);

  const closeEvidenceDrawer = useCallback(() => {
    setActiveCaseId(null);
    if (retryConfirmationPlacement === "drawer") {
      setRetryConfirmCaseIds([]);
      setRetryConfirmationPlacement(null);
    }
  }, [retryConfirmationPlacement]);

  useEffect(() => {
    if (!activeCaseId) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeEvidenceDrawer();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [activeCaseId, closeEvidenceDrawer]);

  const progress = useMemo(() => {
    if (!view) return 0;
    return view.total_cases
      ? (((view.status_counts.approved ?? 0) +
          (view.status_counts.rejected ?? 0)) /
          view.total_cases) *
          100
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
        (reviewCase) =>
          ["pending", "flagged"].includes(reviewCase.review_status) &&
          !reviewCase.ai_draft,
      ),
    [view],
  );
  const aiPolicy = view?.ai_review_policy ?? DISABLED_AI_POLICY;
  const retryableCases = useMemo(
    () =>
      (view?.cases ?? []).filter((reviewCase) => {
        const draft = reviewCase.ai_draft;
        return (
          ["pending", "flagged"].includes(reviewCase.review_status) &&
          draft?.status === "needs_review" &&
          (draft.retry_sequence ?? 0) < aiPolicy.max_retry_rounds &&
          !_isRetryIntegrityFailure(draft.last_error_message)
        );
      }),
    [aiPolicy.max_retry_rounds, view],
  );
  const selectedMaximumCost = useMemo(
    () => selectedCaseIds.length * aiPolicy.max_request_cost_usd,
    [aiPolicy.max_request_cost_usd, selectedCaseIds.length],
  );
  const retryMaximumCost =
    retryConfirmCaseIds.length * aiPolicy.max_request_cost_usd;
  const hasRunningAIDrafts = useMemo(
    () =>
      (view?.ai_review_summary?.active_task_count ??
        (view?.cases ?? []).filter((reviewCase) =>
          ["queued", "running"].includes(reviewCase.ai_draft?.status ?? ""),
        ).length) > 0,
    [view],
  );
  const aiDraftStatusCounts = useMemo(() => {
    if (view?.ai_review_summary) return view.ai_review_summary.status_counts;
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
  const latestAIBatch = view?.ai_review_summary?.latest_batch ?? null;
  const visibleBulkRecommendationCases = useMemo(
    () =>
      (view?.cases ?? [])
        .filter(
          (reviewCase) =>
            reviewCase.review_status === "pending" &&
            reviewCase.ai_draft?.status === "succeeded" &&
            reviewCase.ai_draft.output_document?.result.verdict_proposal ===
              "comparable",
        )
        .slice(0, view?.ai_bulk_certification_policy?.max_cases ?? PAGE_SIZE),
    [view],
  );

  useEffect(() => {
    if (!hasRunningAIDrafts) return;
    const timer = window.setTimeout(
      () => void loadQueue().catch(handleError),
      2500,
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

  async function submitReview(
    reviewCase: ReviewCase,
    verdictOverride?: "insufficient_evidence",
  ) {
    const draft = drafts[reviewCase.case_id];
    const verdict = verdictOverride ?? draft?.verdict;
    if (!reviewerId.trim()) {
      setError("Enter a stable reviewer identity before submitting a review.");
      return;
    }
    if (!draft?.rationale.trim()) {
      setError("Explain the evidence behind the review decision.");
      return;
    }
    if (!verdict) {
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
            verdict,
            allowed_tiers: verdict === "comparable" ? [draft.tier] : [],
            rationale: draft.rationale,
            evidence_refs: reviewCase.evidence_refs,
          }),
        },
      );
      setNotice(
        verdict === "comparable"
          ? "Match approved and finalized. It remains final unless someone flags it."
          : verdict === "not_comparable"
            ? "Match rejected and finalized. It remains final unless someone flags it."
            : "Case flagged and returned to the review queue.",
      );
      setDrafts((current) => ({
        ...current,
        [reviewCase.case_id]: defaultDraft(reviewCase),
      }));
      closeEvidenceDrawer();
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

  function openRetryConfirmation(
    caseIds: string[],
    placement: "batch" | "drawer",
  ) {
    if (!reviewerId.trim()) {
      setError("Enter your reviewer identity before retrying AI review.");
      reviewerInputRef.current?.focus();
      return;
    }
    const uniqueCaseIds = [...new Set(caseIds)].slice(
      0,
      aiPolicy.max_batch_cases,
    );
    if (!uniqueCaseIds.length) {
      setError("No retryable terminal AI failures are visible in this view.");
      return;
    }
    setError(null);
    setNotice(null);
    setRetryConfirmCaseIds(uniqueCaseIds);
    setRetryConfirmationPlacement(placement);
  }

  async function requestAIRetries() {
    if (!reviewerId.trim() || !retryConfirmCaseIds.length) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const requestedCount = retryConfirmCaseIds.length;
    try {
      await jsonRequest(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/ai-drafts/retry`,
        {
          method: "POST",
          body: JSON.stringify({
            requested_by: reviewerId.trim(),
            case_ids: retryConfirmCaseIds,
            retry_reason:
              "Administrator requested another governed AI evidence review after inspecting the terminal failure.",
          }),
        },
      );
      setRetryConfirmCaseIds([]);
      setRetryConfirmationPlacement(null);
      setNotice(
        `${requestedCount} terminal AI ${requestedCount === 1 ? "failure was" : "failures were"} requeued as new, linked tasks. Prior attempts, errors, and recorded costs remain preserved.`,
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

  async function assessBulkAIRecommendations() {
    if (!reviewerId.trim()) {
      setError(
        "Enter your reviewer identity before assessing AI recommendations for bulk certification.",
      );
      reviewerInputRef.current?.focus();
      return;
    }
    if (!visibleBulkRecommendationCases.length) {
      setError(
        "No completed affirmative AI match recommendations are visible in this filtered page.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const preview = await jsonRequest<AIBulkCertificationPreview>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/ai-bulk-certification/preview`,
        {
          method: "POST",
          body: JSON.stringify({
            case_ids: visibleBulkRecommendationCases.map(
              (reviewCase) => reviewCase.case_id,
            ),
          }),
        },
      );
      setBulkCertificationPreview(preview);
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function commitBulkAIRecommendations() {
    const preview = bulkCertificationPreview;
    if (!preview?.confirmation_checksum || !preview.eligible_case_count) {
      setError("Assess the current AI recommendations before confirming them.");
      return;
    }
    if (!reviewerId.trim()) {
      setError("Enter your reviewer identity before confirming these matches.");
      reviewerInputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await jsonRequest<{
        approved_case_count: number;
        idempotent_replay: boolean;
      }>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/ai-bulk-certification/commit`,
        {
          method: "POST",
          body: JSON.stringify({
            reviewer_id: reviewerId.trim(),
            case_ids: preview.eligible_cases.map(
              (candidate) => candidate.case_id,
            ),
            confirmation_checksum: preview.confirmation_checksum,
          }),
        },
      );
      setBulkCertificationPreview(null);
      setNotice(
        `${response.approved_case_count} AI-recommended ${response.approved_case_count === 1 ? "match was" : "matches were"} approved by ${reviewerId.trim()} and finalized. Reporting is not recalculated automatically; each decision remains final until flagged.`,
      );
      await loadQueue();
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
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
              setBulkCertificationPreview(null);
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
              setBulkCertificationPreview(null);
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
              setBulkCertificationPreview(null);
            }}
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="flagged">Flagged</option>
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
              <strong>
                {(view.status_counts.approved ?? 0) +
                  (view.status_counts.rejected ?? 0)}
              </strong>
              <span>Finalized</span>
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
              Open certified gold set
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
                  draft or final decision
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
              <div className="cert-ai-status-counts">
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
              {latestAIBatch ? (
                <div className="cert-ai-progress-panel">
                  <div>
                    <strong>
                      Latest batch · {latestAIBatch.completed_count} of{" "}
                      {latestAIBatch.task_count} complete
                    </strong>
                    <span>
                      Submitted {formatTimestamp(latestAIBatch.submitted_at)} by{" "}
                      {latestAIBatch.requested_by}
                    </span>
                  </div>
                  <div
                    className="cert-ai-progress-track"
                    role="progressbar"
                    aria-label="Latest AI review batch progress"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={latestAIBatch.progress_percent}
                  >
                    <span
                      style={{ width: `${latestAIBatch.progress_percent}%` }}
                    />
                  </div>
                  <div className="cert-ai-batch-meta">
                    <span>
                      {latestAIBatch.completed_at
                        ? `Finished ${formatTimestamp(latestAIBatch.completed_at)}`
                        : `Estimated remaining: ${formatDuration(latestAIBatch.estimated_seconds_remaining)}`}
                    </span>
                    <span>
                      Recorded cost $
                      {latestAIBatch.estimated_cost_usd.toFixed(4)}
                    </span>
                  </div>
                </div>
              ) : (
                <p>No AI review batches are recorded for this queue yet.</p>
              )}
              <p>
                {hasRunningAIDrafts
                  ? "Queue-wide status refreshes automatically while AI work is queued or running."
                  : visibleAIDraftCount
                    ? "Queue-wide status is current. Open Review evidence on a ready case to make the final human decision."
                    : "No AI drafts are recorded for this queue yet."}
              </p>
              <div className="cert-ai-status-actions">
                <button
                  className="button secondary"
                  type="button"
                  disabled={busy || !aiPolicy.enabled || !retryableCases.length}
                  onClick={() =>
                    openRetryConfirmation(
                      retryableCases
                        .slice(0, aiPolicy.max_batch_cases)
                        .map((reviewCase) => reviewCase.case_id),
                      "batch",
                    )
                  }
                >
                  {retryableCases.length
                    ? `Retry ${Math.min(retryableCases.length, aiPolicy.max_batch_cases)} needs-attention ${retryableCases.length === 1 ? "item" : "items"}`
                    : "No retryable failures"}
                </button>
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
            </div>
            <section
              className="cert-bulk-certification"
              aria-labelledby="cert-bulk-certification-title"
            >
              <header>
                <div>
                  <small>Guarded human certification</small>
                  <h3 id="cert-bulk-certification-title">
                    Bulk accept corroborated AI match recommendations
                  </h3>
                  <p>
                    The server screens the completed AI recommendations on this
                    page. Only affirmative matches that agree with the
                    deterministic engine and pass every evidence guardrail can
                    reach the confirmation step.
                  </p>
                </div>
                <button
                  className="button secondary"
                  type="button"
                  disabled={busy || !visibleBulkRecommendationCases.length}
                  aria-busy={busy}
                  onClick={() => void assessBulkAIRecommendations()}
                >
                  {busy
                    ? "Assessing…"
                    : visibleBulkRecommendationCases.length
                      ? `Assess ${visibleBulkRecommendationCases.length} recommendations`
                      : "No affirmative AI drafts on this page"}
                </button>
              </header>
              <div
                className="cert-bulk-guardrails"
                aria-label="Bulk acceptance guardrails"
              >
                <span>AI + engine tier agreement</span>
                <span>100% critical evidence</span>
                <span>No unresolved conflicts</span>
                <span>No known third-party seller</span>
                <span>Exact or equivalent tiers only</span>
              </div>
              <p className="cert-bulk-boundary">
                Comparable-substitute and custom matches always remain
                individual-review decisions. A bulk approval is recorded under
                your reviewer identity, is final until flagged, and does not
                trigger reanalysis automatically.
              </p>
              {bulkCertificationPreview ? (
                <div
                  className="cert-bulk-preview"
                  role="region"
                  aria-label="Bulk certification preview"
                >
                  <header>
                    <div>
                      <small>Checksum-bound preview</small>
                      <h4>
                        {bulkCertificationPreview.eligible_case_count} eligible
                        {bulkCertificationPreview.excluded_case_count
                          ? ` · ${bulkCertificationPreview.excluded_case_count} excluded`
                          : " · no exclusions"}
                      </h4>
                    </div>
                    <code>
                      Policy {bulkCertificationPreview.policy.id} v
                      {bulkCertificationPreview.policy.version}
                    </code>
                  </header>
                  {bulkCertificationPreview.eligible_cases.length ? (
                    <div className="cert-bulk-candidate-list">
                      {bulkCertificationPreview.eligible_cases.map(
                        (candidate) => (
                          <article key={candidate.case_id}>
                            <div className="cert-bulk-pair">
                              <BulkProductIdentity
                                product={candidate.benchmark_product}
                              />
                              <span>matches</span>
                              <BulkProductIdentity
                                product={candidate.competitor_product}
                              />
                            </div>
                            <div className="cert-bulk-evidence-summary">
                              <strong>
                                {label(candidate.recommended_tier)}
                              </strong>
                              <span>
                                {Math.round(candidate.critical_coverage * 100)}%
                                critical evidence ·{" "}
                                {label(candidate.engine_status)}
                              </span>
                              <p>{candidate.ai_rationale}</p>
                            </div>
                          </article>
                        ),
                      )}
                    </div>
                  ) : (
                    <p className="cert-bulk-empty">
                      No recommendation passed every bulk-certification
                      guardrail. Review these cases individually.
                    </p>
                  )}
                  {bulkCertificationPreview.exclusion_summary.length ? (
                    <details className="cert-bulk-exclusions">
                      <summary>
                        Why {bulkCertificationPreview.excluded_case_count}{" "}
                        {bulkCertificationPreview.excluded_case_count === 1
                          ? "case was"
                          : "cases were"}{" "}
                        excluded
                      </summary>
                      <ul>
                        {bulkCertificationPreview.exclusion_summary.map(
                          (reason) => (
                            <li key={reason.reason_code}>
                              <b>{reason.case_count}</b> {reason.reason}
                            </li>
                          ),
                        )}
                      </ul>
                    </details>
                  ) : null}
                  <footer>
                    <p>
                      <b>Human confirmation required.</b> You are approving
                      these exact product relationships—not delegating the
                      decision to AI.
                    </p>
                    <button
                      className="button secondary"
                      type="button"
                      disabled={busy}
                      onClick={() => setBulkCertificationPreview(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="button primary"
                      type="button"
                      disabled={
                        busy ||
                        !bulkCertificationPreview.eligible_case_count ||
                        !bulkCertificationPreview.confirmation_checksum
                      }
                      aria-busy={busy}
                      onClick={() => void commitBulkAIRecommendations()}
                    >
                      {busy
                        ? "Finalizing…"
                        : `Approve ${bulkCertificationPreview.eligible_case_count} ${bulkCertificationPreview.eligible_case_count === 1 ? "match" : "matches"}`}
                    </button>
                  </footer>
                </div>
              ) : null}
            </section>
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
            {retryConfirmationPlacement === "batch" &&
            retryConfirmCaseIds.length ? (
              <div
                className="cert-ai-batch-confirm cert-ai-retry-confirm"
                role="alert"
              >
                <div>
                  <strong>
                    Retry {retryConfirmCaseIds.length} terminal AI failure
                    {retryConfirmCaseIds.length === 1 ? "" : "s"}?
                  </strong>
                  <p>
                    This creates new linked tasks; it does not reset or erase
                    prior attempts. Model: {aiPolicy.model_id}. Maximum new
                    policy exposure: ${retryMaximumCost.toFixed(2)}. Each new
                    task still requires a human decision.
                  </p>
                </div>
                <button
                  className="button secondary"
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setRetryConfirmCaseIds([]);
                    setRetryConfirmationPlacement(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  className="button primary"
                  type="button"
                  disabled={busy}
                  aria-busy={busy}
                  onClick={() => void requestAIRetries()}
                >
                  {busy ? "Queueing…" : "Confirm governed retry"}
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
                      !["pending", "flagged"].includes(
                        reviewCase.review_status,
                      ) ||
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
                      : ["approved", "rejected"].includes(
                            reviewCase.review_status,
                          )
                        ? "Finalized"
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
                  {["approved", "rejected"].includes(reviewCase.review_status)
                    ? "View decision"
                    : "Review evidence"}
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
                if (event.target === event.currentTarget) closeEvidenceDrawer();
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
                      makes the final human decision.
                    </p>
                  </div>
                  <button
                    className="button secondary"
                    type="button"
                    onClick={closeEvidenceDrawer}
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
                        disabled={
                          busy ||
                          ["approved", "rejected"].includes(
                            activeCase.review_status,
                          ) ||
                          Boolean(activeCase.ai_draft)
                        }
                        onClick={() => void requestAIReview(activeCase)}
                      >
                        {activeCase.ai_draft
                          ? `AI ${label(activeCase.ai_draft.status)}`
                          : ["approved", "rejected"].includes(
                                activeCase.review_status,
                              )
                            ? "Decision finalized"
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
                        {(activeCase.ai_draft.retry_sequence ?? 0) > 0 ? (
                          <small>
                            Manual retry round{" "}
                            {activeCase.ai_draft.retry_sequence}
                            {" of "}
                            {aiPolicy.max_retry_rounds} · Prior task preserved
                          </small>
                        ) : null}
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
                          <div className="cert-ai-error-detail" role="status">
                            <strong>
                              {activeCase.ai_draft.status === "needs_review"
                                ? "The AI draft could not be completed"
                                : "The worker will retry this draft"}
                            </strong>
                            <p>{activeCase.ai_draft.last_error_message}</p>
                            <small>
                              {activeCase.ai_draft.last_error_type
                                ? `${activeCase.ai_draft.last_error_type} · `
                                : ""}
                              Attempt {activeCase.ai_draft.attempt_count} of{" "}
                              {activeCase.ai_draft.max_attempts} · Last activity{" "}
                              {formatTimestamp(activeCase.ai_draft.updated_at)}
                            </small>
                            {activeCase.ai_draft.status === "needs_review" ? (
                              (activeCase.ai_draft.retry_sequence ?? 0) <
                                aiPolicy.max_retry_rounds &&
                              !_isRetryIntegrityFailure(
                                activeCase.ai_draft.last_error_message ?? "",
                              ) ? (
                                <button
                                  className="button secondary"
                                  type="button"
                                  disabled={busy || !aiPolicy.enabled}
                                  onClick={() =>
                                    openRetryConfirmation(
                                      [activeCase.case_id],
                                      "drawer",
                                    )
                                  }
                                >
                                  Retry AI evidence review
                                </button>
                              ) : (
                                <small>
                                  {_isRetryIntegrityFailure(
                                    activeCase.ai_draft.last_error_message,
                                  )
                                    ? "An evidence-integrity failure requires engineering review and cannot trigger another paid call."
                                    : `The governed limit of ${aiPolicy.max_retry_rounds} manual retry rounds has been reached.`}
                                </small>
                              )
                            ) : null}
                            {retryConfirmationPlacement === "drawer" &&
                            retryConfirmCaseIds.includes(activeCase.case_id) ? (
                              <div className="cert-ai-drawer-retry-confirm">
                                <strong>
                                  Confirm a new linked retry task?
                                </strong>
                                <p>
                                  Prior attempts, this exact error, and any
                                  recorded cost remain preserved. The maximum
                                  new policy exposure is $
                                  {aiPolicy.max_request_cost_usd.toFixed(2)}.
                                </p>
                                <div>
                                  <button
                                    className="button secondary"
                                    type="button"
                                    disabled={busy}
                                    onClick={() => {
                                      setRetryConfirmCaseIds([]);
                                      setRetryConfirmationPlacement(null);
                                    }}
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    className="button primary"
                                    type="button"
                                    disabled={busy}
                                    aria-busy={busy}
                                    onClick={() => void requestAIRetries()}
                                  >
                                    {busy
                                      ? "Queueing…"
                                      : "Confirm governed retry"}
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          <p>
                            The worker is preparing this advisory draft. Attempt{" "}
                            {activeCase.ai_draft.attempt_count} of{" "}
                            {activeCase.ai_draft.max_attempts}.
                          </p>
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
                  {activeCase.final_decision &&
                  ["approved", "rejected"].includes(
                    activeCase.review_status,
                  ) ? (
                    <div className="cert-final-decision">
                      <p>
                        <b>Final decision: {label(activeCase.review_status)}</b>
                        {activeCase.final_decision.rationale}
                        <small>
                          Decided by {activeCase.final_decision.reviewer_id}
                        </small>
                      </p>
                      <label className="cert-rationale">
                        <span>Reason to flag this decision</span>
                        <textarea
                          value={drafts[activeCase.case_id]?.rationale ?? ""}
                          onChange={(event) =>
                            updateDraft(activeCase.case_id, {
                              rationale: event.target.value,
                            })
                          }
                          placeholder="Explain what evidence or product detail should be reconsidered."
                        />
                      </label>
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void submitReview(activeCase, "insufficient_evidence")
                        }
                      >
                        Flag for re-review
                      </button>
                    </div>
                  ) : (
                    <div className="cert-review-form cert-review-form-drawer">
                      <fieldset>
                        <legend>Final decision</legend>
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
                        Save final decision
                      </button>
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
