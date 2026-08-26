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
  quarantine?: QueueQuarantine | null;
}

interface QueueQuarantine {
  status: "quarantined";
  reason: string;
  carry_forward_allowed: false;
  reporting_release_allowed: false;
  successor_product_pack_version: string;
  quarantined_at: string;
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
  max_candidates_assessed?: number;
  allowed_verdicts?: Array<"comparable" | "not_comparable">;
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
  warning_codes: string[];
  warnings: string[];
  recommended_verdict?: "comparable" | "not_comparable";
  recommended_tier: string | null;
  recommended_comparison_bases?: string[];
  eligible_comparison_bases?: string[];
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
  warning_summary: Array<{
    warning_code: string;
    warning: string;
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
      queue_role?: string | null;
      role_source?: string | null;
      benchmark_value: unknown;
      competitor_value: unknown;
      outcome: string;
      benchmark_source: string | null;
      competitor_source: string | null;
      reliability: number;
    }>;
  };
  certification_blockers?: Array<{
    attribute: string;
    outcome: string;
    benchmark_value: unknown;
    competitor_value: unknown;
    reason: string;
  }>;
  certification_policy?: {
    product_pack_id: string;
    product_pack_version: string;
    queue_evidence_is_immutable: boolean;
    stricter_active_policy_wins: boolean;
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
  attribute_evidence_reconciliation?: {
    schema_version: string;
    advisory_proposal_count: number;
    eligible_proposal_count: number;
    verified_proposal_count: number;
    raw_evidence_mutated: false;
    human_verification_required: true;
    conflicts: Array<{
      listing_role: string;
      attribute: string;
      reason: string;
    }>;
    proposals: Array<{
      proposal_checksum: string;
      listing_role: "benchmark" | "competitor" | null;
      listing_id: string;
      attribute: string;
      raw_value: unknown;
      normalized_value: unknown;
      evidence_source: string;
      confidence: number;
      visible_text: string | null;
      source_image_url: string | null;
      eligible: boolean;
      ineligibility_reasons: string[];
      decision: null | {
        id: string;
        decision: "verified" | "rejected";
        reviewer_id: string;
        rationale: string;
        created_at: string;
      };
    }>;
  };
  ai_draft?: null | {
    id: string;
    batch_id: string;
    root_batch_id?: string;
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
        comparison_basis_proposal?: Array<
          "package_price" | "normalized_unit_price"
        >;
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
    queue_wide_selection?: boolean;
    queue_wide_scope?: string;
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
  quarantine?: QueueQuarantine | null;
}

interface AttributeEvidenceProduct {
  listing_id: string;
  retailer_id: string;
  retailer_product_id: string;
  title: string | null;
  brand: string | null;
  image_url: string | null;
  product_url?: string | null;
  observed_location_count?: number;
}

interface AttributeEvidenceProposal {
  proposal_checksum: string;
  case_id: string;
  case_review_status: string;
  competitor_retailer_id: string;
  listing_role: "benchmark" | "competitor" | null;
  listing_id: string;
  attribute: string;
  raw_value: unknown;
  normalized_value: unknown;
  current_value: unknown;
  current_source: string | null;
  evidence_relationship:
    | "fills_unknown"
    | "corroborates_existing"
    | "refines_existing"
    | "conflicts_with_existing"
    | "invalid";
  decision_effect:
    | "fill_missing_value"
    | "no_change"
    | "replace_with_verified_refinement"
    | "replace_with_verified_correction";
  confidence: number;
  visible_text: string | null;
  source_image_url: string | null;
  eligible: boolean;
  ineligibility_reasons: string[];
  decision_status: "undecided" | "verified" | "rejected";
  decision: null | {
    id: string;
    decision: "verified" | "rejected";
    reviewer_id: string;
    rationale: string;
    created_at: string;
    proposal_checksum?: string;
  };
  listing: AttributeEvidenceProduct;
  counterpart: AttributeEvidenceProduct;
  ai_draft: {
    id: string;
    batch_id: string;
    root_batch_id: string;
    model_id: string;
    completed_at: string | null;
  };
}

interface AttributeEvidenceLineage {
  root_batch_id: string;
  batch_ids: string[];
  model_ids: string[];
  case_count: number;
  proposal_count: number;
  eligible_proposal_count: number;
  ineligible_proposal_count: number;
  undecided_proposal_count: number;
  verified_proposal_count: number;
  rejected_proposal_count: number;
  latest_activity_at: string;
}

type AttributeEvidenceClaimStatus =
  "all" | "awaiting_review" | "conflict" | "verified" | "rejected";

interface AttributeEvidenceClaimVariant {
  value: unknown;
  value_checksum: string;
  proposal_count: number;
  case_count: number;
  minimum_confidence: number;
  maximum_confidence: number;
  evidence_relationships: AttributeEvidenceProposal["evidence_relationship"][];
  representative_case_id: string;
  representative_proposal_checksum: string;
  citations: Array<{
    source_image_url: string | null;
    visible_text: string | null;
    confidence: number;
    case_id: string;
    proposal_checksum: string;
    counterpart_retailer_id: string;
  }>;
}

interface AttributeEvidenceClaim {
  claim_checksum: string;
  listing_id: string;
  attribute: string;
  proposal_checksums: string[];
  status: Exclude<AttributeEvidenceClaimStatus, "all">;
  status_reason: string;
  listing: AttributeEvidenceProduct;
  current_evidence: Array<{ value: unknown; source: string | null }>;
  proposal_count: number;
  affected_case_count: number;
  counterpart_product_count: number;
  counterpart_retailers: string[];
  variants: AttributeEvidenceClaimVariant[];
  decision: null | {
    id: string;
    decision: "verified" | "rejected";
    reviewer_id: string;
    rationale: string;
    created_at: string;
    proposal_checksum?: string;
  };
  raw_evidence_mutated: false;
}

interface AttributeEvidenceClaimView {
  authoritative: false;
  human_verification_required: true;
  raw_evidence_mutated: false;
  selected_root_batch_id: string | null;
  batch_lineages: AttributeEvidenceLineage[];
  summary: {
    claim_count: number;
    proposal_count: number;
    awaiting_review_count: number;
    conflict_count: number;
    verified_count: number;
    rejected_count: number;
    affected_product_count: number;
  };
  attributes: Array<{ attribute: string; claim_count: number }>;
  selected_claim_count: number;
  offset: number;
  limit: number;
  claims: AttributeEvidenceClaim[];
}

interface GoldSetReplayResult {
  gold_set_release_id: string;
  gold_set_checksum: string;
  analysis_run_id: string;
  analysis_status: string;
  coverage: {
    candidate_count: number;
    certified_count: number;
    certified_comparable_count: number;
    certified_not_comparable_count: number;
    unresolved_count: number;
  };
}

interface ReviewDraft {
  verdict: "" | "comparable" | "not_comparable" | "insufficient_evidence";
  tier: string;
  rationale: string;
}

interface EligibleAIReviewScope {
  queue_id: string;
  competitor_retailer_id: string | null;
  selection_mode: "all_cases" | "product_evidence_coverage";
  eligible_case_count: number;
  selected_case_count: number;
  deferred_case_count: number;
  unresolved_product_evidence_count: number;
  selected_product_evidence_count: number;
  case_ids: string[];
  authoritative: false;
  human_review_required: true;
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
const BULK_DISCOVERY_PAGE_SIZE = 500;
const DISABLED_AI_POLICY: NonNullable<QueueView["ai_review_policy"]> = {
  enabled: false,
  model_id: null,
  max_batch_cases: 1500,
  queue_wide_selection: true,
  queue_wide_scope: "current_queue_and_competitor_filter",
  max_request_cost_usd: 0,
  max_retry_rounds: 4,
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

function evidenceRelationshipLabel(
  relationship: AttributeEvidenceProposal["evidence_relationship"],
) {
  return {
    fills_unknown: "Completes missing evidence",
    corroborates_existing: "Corroborates current evidence",
    refines_existing: "Adds material detail",
    conflicts_with_existing: "Conflicts with current evidence",
    invalid: "Invalid advisory claim",
  }[relationship];
}

function evidenceApplyLabel(
  relationship: AttributeEvidenceProposal["evidence_relationship"],
) {
  if (relationship === "conflicts_with_existing")
    return "Verify correction & apply";
  if (relationship === "refines_existing") return "Verify refinement & apply";
  return "Verify & apply";
}

function bulkCandidateVerdict(
  candidate: AIBulkCertificationCandidate,
): "comparable" | "not_comparable" {
  return (
    candidate.recommended_verdict ??
    (candidate.recommended_tier ? "comparable" : "not_comparable")
  );
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

interface MatchingReviewInitialContext {
  productPackId: string | null;
  competitorRetailerId: string | null;
  benchmarkProductId: string | null;
  competitorProductId: string | null;
}

export function MatchingV2ReviewAdmin({
  initialContext,
}: Readonly<{ initialContext?: MatchingReviewInitialContext }>) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [password, setPassword] = useState("");
  const [queues, setQueues] = useState<QueueSummary[]>([]);
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const [queueRefresh, setQueueRefresh] = useState(0);
  const [view, setView] = useState<QueueView | null>(null);
  const [workspaceView, setWorkspaceView] = useState<
    "certification" | "attribute-evidence"
  >("certification");
  const [attributeEvidenceView, setAttributeEvidenceView] =
    useState<AttributeEvidenceClaimView | null>(null);
  const [attributeBatchRoot, setAttributeBatchRoot] = useState("all");
  const [attributeClaimStatus, setAttributeClaimStatus] =
    useState<AttributeEvidenceClaimStatus>("all");
  const [attributeFilter, setAttributeFilter] = useState("all");
  const [selectedClaimVariants, setSelectedClaimVariants] = useState<
    Record<string, string>
  >({});
  const [attributeOffset, setAttributeOffset] = useState(0);
  const [attributeLoading, setAttributeLoading] = useState(false);
  const [reviewerId, setReviewerId] = useState("");
  const [replaySourceAnalysisId, setReplaySourceAnalysisId] = useState("");
  const [replayResult, setReplayResult] = useState<GoldSetReplayResult | null>(
    null,
  );
  const [competitorFilter, setCompetitorFilter] = useState(
    initialContext?.competitorRetailerId ?? "all",
  );
  const [statusFilter, setStatusFilter] = useState(
    initialContext?.benchmarkProductId ? "all" : "pending",
  );
  const [offset, setOffset] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [evidenceRationales, setEvidenceRationales] = useState<
    Record<string, string>
  >({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [selectionScope, setSelectionScope] = useState<
    "manual" | "queue-wide" | "product-evidence"
  >("manual");
  const [selectionDeferredCaseCount, setSelectionDeferredCaseCount] =
    useState(0);
  const [selectionProductEvidenceCount, setSelectionProductEvidenceCount] =
    useState(0);
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
  const initialEvidenceOpened = useRef(false);

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
      (current) =>
        current ??
        latestQueues.find(
          (queue) => queue.product_pack.id === initialContext?.productPackId,
        )?.queue_id ??
        latestQueues[0]?.queue_id ??
        null,
    );
  }, [initialContext?.productPackId]);

  const loadQueue = useCallback(async () => {
    if (!selectedQueueId) return;
    const requestSequence = ++queueRequestSequence.current;
    const query = new URLSearchParams({
      limit: String(
        initialContext?.benchmarkProductId ||
          initialContext?.competitorProductId
          ? BULK_DISCOVERY_PAGE_SIZE
          : PAGE_SIZE,
      ),
      offset: String(offset),
    });
    if (competitorFilter !== "all") {
      query.set("competitor_retailer_id", competitorFilter);
    }
    if (initialContext?.benchmarkProductId) {
      query.set("benchmark_product_id", initialContext.benchmarkProductId);
    }
    if (initialContext?.competitorProductId) {
      query.set("competitor_product_id", initialContext.competitorProductId);
    }
    if (statusFilter !== "all") query.set("review_status", statusFilter);
    const response = await jsonRequest<QueueView>(
      `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId)}?${query}`,
    );
    if (requestSequence !== queueRequestSequence.current) return;
    setView(response);
    if (!initialEvidenceOpened.current && initialContext?.benchmarkProductId) {
      const linkedCase = response.cases.find(
        (reviewCase) =>
          reviewCase.benchmark_listing.retailer_product_id ===
            initialContext.benchmarkProductId &&
          (!initialContext.competitorProductId ||
            reviewCase.competitor_listing.retailer_product_id ===
              initialContext.competitorProductId),
      );
      if (linkedCase) {
        initialEvidenceOpened.current = true;
        setActiveCaseId(linkedCase.case_id);
      }
    }
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
    setSelectedCaseIds((current) => {
      const visibleCases = new Map(
        response.cases.map((reviewCase) => [reviewCase.case_id, reviewCase]),
      );
      return current.filter((caseId) => {
        const reviewCase = visibleCases.get(caseId);
        return (
          !reviewCase ||
          (["pending", "flagged"].includes(reviewCase.review_status) &&
            !reviewCase.ai_draft)
        );
      });
    });
  }, [
    competitorFilter,
    initialContext?.benchmarkProductId,
    initialContext?.competitorProductId,
    offset,
    selectedQueueId,
    statusFilter,
  ]);

  const loadAttributeEvidence = useCallback(async () => {
    if (!selectedQueueId) return;
    setAttributeLoading(true);
    const query = new URLSearchParams({
      claim_status: attributeClaimStatus,
      offset: String(attributeOffset),
      limit: String(PAGE_SIZE),
      batch_scope:
        attributeBatchRoot === "all" ? "all_lineages" : "latest_lineage",
    });
    if (attributeBatchRoot !== "latest" && attributeBatchRoot !== "all") {
      query.set("root_batch_id", attributeBatchRoot);
    }
    if (competitorFilter !== "all") {
      query.set("competitor_retailer_id", competitorFilter);
    }
    if (attributeFilter !== "all") {
      query.set("attribute", attributeFilter);
    }
    try {
      const response = await jsonRequest<AttributeEvidenceClaimView>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId)}/attribute-evidence-claims?${query}`,
      );
      setAttributeEvidenceView(response);
      setSelectedClaimVariants((current) => {
        const next = { ...current };
        for (const claim of response.claims) {
          next[claim.claim_checksum] ??=
            claim.decision?.proposal_checksum ??
            claim.variants[0]?.representative_proposal_checksum ??
            "";
        }
        return next;
      });
    } finally {
      setAttributeLoading(false);
    }
  }, [
    attributeBatchRoot,
    attributeClaimStatus,
    attributeFilter,
    attributeOffset,
    competitorFilter,
    selectedQueueId,
  ]);

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
    if (session?.authenticated && workspaceView === "attribute-evidence") {
      // The state updates occur after the protected evidence-index request resolves.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadAttributeEvidence().catch(handleError);
    }
  }, [
    loadAttributeEvidence,
    queueRefresh,
    session?.authenticated,
    workspaceView,
  ]);

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
  const queueQuarantined = Boolean(view?.quarantine);
  const selectedPageCaseCount = eligibleCases.filter((reviewCase) =>
    selectedCaseIds.includes(reviewCase.case_id),
  ).length;
  const selectedOffPageCaseCount = Math.max(
    0,
    selectedCaseIds.length - selectedPageCaseCount,
  );
  const pageSelectionCapacity = Math.min(
    eligibleCases.length,
    Math.max(0, aiPolicy.max_batch_cases - selectedOffPageCaseCount),
  );
  const pageSelectionComplete =
    pageSelectionCapacity > 0 &&
    selectedPageCaseCount === pageSelectionCapacity;
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

  async function createGovernedReplay(event: FormEvent) {
    event.preventDefault();
    if (!view) return;
    const sourceAnalysisId = replaySourceAnalysisId.trim();
    const releasedBy = reviewerId.trim();
    if (!sourceAnalysisId) {
      setError("Enter the source analysis ID that supplied this review queue.");
      return;
    }
    if (!releasedBy) {
      setError(
        "Enter the current administrator identity before releasing a replay.",
      );
      reviewerInputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await jsonRequest<GoldSetReplayResult>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(view.queue.queue_id)}/gold-set/replays`,
        {
          method: "POST",
          body: JSON.stringify({
            source_analysis_id: sourceAnalysisId,
            released_by: releasedBy,
          }),
        },
      );
      setReplayResult(result);
      setNotice(
        `Governed replay ${result.analysis_run_id} is ${label(result.analysis_status).toLowerCase()}. The immutable release contains ${result.coverage.certified_count.toLocaleString()} certified cases and leaves ${result.coverage.unresolved_count.toLocaleString()} unresolved.`,
      );
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
    if (verdict === "comparable" && reviewCase.certification_blockers?.length) {
      setError(
        `This match cannot be approved because the current Product Pack has unresolved or conflicting hard requirements: ${reviewCase.certification_blockers
          .map((issue) => label(issue.attribute))
          .join(", ")}.`,
      );
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

  async function decideAttributeEvidence(
    caseId: string,
    proposal:
      | NonNullable<
          ReviewCase["attribute_evidence_reconciliation"]
        >["proposals"][number]
      | AttributeEvidenceProposal,
    decision: "verified" | "rejected",
  ) {
    if (!reviewerId.trim()) {
      setError(
        "Enter your reviewer identity before reconciling attribute evidence.",
      );
      return;
    }
    const rationale = evidenceRationales[proposal.proposal_checksum]?.trim();
    if (!rationale) {
      setError(
        "Record why the cited label evidence is valid or invalid before deciding.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await jsonRequest(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/cases/${encodeURIComponent(caseId)}/attribute-evidence-decisions`,
        {
          method: "POST",
          body: JSON.stringify({
            reviewer_id: reviewerId.trim(),
            proposal_checksum: proposal.proposal_checksum,
            decision,
            rationale,
            supersedes_decision_id: proposal.decision?.id ?? null,
          }),
        },
      );
      setNotice(
        decision === "verified"
          ? "The image evidence was verified and applied to the derived certification view. Raw PDP and queue evidence remain unchanged."
          : "The advisory image proposal was rejected and preserved in the audit history.",
      );
      await loadQueue();
      if (workspaceView === "attribute-evidence") {
        await loadAttributeEvidence();
      }
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function decideAttributeClaim(
    claim: AttributeEvidenceClaim,
    decision: "verified" | "rejected",
  ) {
    if (!reviewerId.trim()) {
      setError(
        "Enter your reviewer identity before reconciling product evidence.",
      );
      return;
    }
    const rationale = evidenceRationales[claim.claim_checksum]?.trim();
    if (!rationale) {
      setError(
        "Record why the complete product-level evidence is valid or invalid before deciding.",
      );
      return;
    }
    const selectedProposalChecksum =
      selectedClaimVariants[claim.claim_checksum] ??
      claim.variants[0]?.representative_proposal_checksum;
    if (decision === "verified" && !selectedProposalChecksum) {
      setError("Select the supported attribute value to verify.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await jsonRequest<{
        affected_case_count: number;
        selected_value: unknown;
      }>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/attribute-evidence-claims/${claim.claim_checksum}/decisions`,
        {
          method: "POST",
          body: JSON.stringify({
            reviewer_id: reviewerId.trim(),
            claim_checksum: claim.claim_checksum,
            decision,
            rationale,
            selected_proposal_checksum: selectedProposalChecksum ?? null,
            batch_scope:
              attributeBatchRoot === "all" ? "all_lineages" : "latest_lineage",
            root_batch_id:
              attributeBatchRoot === "all" || attributeBatchRoot === "latest"
                ? null
                : attributeBatchRoot,
          }),
        },
      );
      setNotice(
        decision === "verified"
          ? `Product evidence verified once and made available to ${result.affected_case_count.toLocaleString()} affected match cases. Match certification and reporting remain unchanged.`
          : `The complete current product-attribute claim was rejected and retained in audit history. Match certification and reporting remain unchanged.`,
      );
      await Promise.all([loadQueue(), loadAttributeEvidence()]);
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
      setSelectionScope("manual");
      setSelectionDeferredCaseCount(0);
      setSelectionProductEvidenceCount(0);
      setNotice(
        `${requestedCount} AI review ${requestedCount === 1 ? "draft was" : "drafts were"} accepted${selectionScope === "queue-wide" ? " from the queue-wide eligible scope" : selectionScope === "product-evidence" ? " from the distinct-product evidence scope" : ""}. Status refreshes automatically while the work is queued or running.`,
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
    setSelectionScope("manual");
    setSelectionDeferredCaseCount(0);
    setSelectionProductEvidenceCount(0);
    setBatchConfirmOpen(true);
  }

  async function openQueueWideAIReviewConfirmation(
    selectionMode: "all_cases" | "product_evidence_coverage" = "all_cases",
  ) {
    if (!reviewerId.trim()) {
      setError(
        "Enter your reviewer identity before reviewing the eligible queue with AI.",
      );
      reviewerInputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const query = new URLSearchParams();
      if (competitorFilter !== "all") {
        query.set("competitor_retailer_id", competitorFilter);
      }
      query.set("selection_mode", selectionMode);
      const scope = await jsonRequest<EligibleAIReviewScope>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/ai-drafts/eligible-cases${query.size ? `?${query}` : ""}`,
      );
      if (!scope.case_ids.length) {
        throw new Error(
          "No eligible cases remain without an AI draft or final decision in the current queue and competitor filter.",
        );
      }
      setSelectedCaseIds(scope.case_ids);
      setSelectionScope(
        selectionMode === "product_evidence_coverage"
          ? "product-evidence"
          : "queue-wide",
      );
      setSelectionDeferredCaseCount(scope.deferred_case_count);
      setSelectionProductEvidenceCount(scope.selected_product_evidence_count);
      setBatchConfirmOpen(true);
    } catch (cause) {
      handleError(cause);
    } finally {
      setBusy(false);
    }
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
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const maximumCandidates =
        view?.ai_bulk_certification_policy?.max_candidates_assessed ??
        BULK_DISCOVERY_PAGE_SIZE;
      const candidates: ReviewCase[] = [];
      let discoveryOffset = 0;
      let selectedCaseCount = 0;
      do {
        const query = new URLSearchParams({
          limit: String(BULK_DISCOVERY_PAGE_SIZE),
          offset: String(discoveryOffset),
          review_status: "pending",
        });
        if (competitorFilter !== "all") {
          query.set("competitor_retailer_id", competitorFilter);
        }
        const response = await jsonRequest<QueueView>(
          `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}?${query}`,
        );
        selectedCaseCount = response.selected_case_count;
        candidates.push(
          ...response.cases.filter(
            (reviewCase) =>
              reviewCase.review_status === "pending" &&
              reviewCase.ai_draft?.status === "succeeded" &&
              ["comparable", "not_comparable"].includes(
                reviewCase.ai_draft.output_document?.result.verdict_proposal ??
                  "",
              ),
          ),
        );
        discoveryOffset += response.cases.length;
      } while (
        candidates.length < maximumCandidates &&
        discoveryOffset < selectedCaseCount &&
        discoveryOffset > 0
      );
      const candidateIds = candidates
        .slice(0, maximumCandidates)
        .map((reviewCase) => reviewCase.case_id);
      if (!candidateIds.length) {
        throw new Error(
          "No pending comparable or not-comparable AI recommendations were found in the current queue and retailer filter.",
        );
      }
      const preview = await jsonRequest<AIBulkCertificationPreview>(
        `/api/admin/matching-v2/review-queues/${encodeURIComponent(selectedQueueId ?? "")}/ai-bulk-certification/preview`,
        {
          method: "POST",
          body: JSON.stringify({
            case_ids: candidateIds,
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
        certified_case_count?: number;
        comparable_case_count?: number;
        not_comparable_case_count?: number;
        approved_case_count?: number;
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
      const certifiedCount =
        response.certified_case_count ?? response.approved_case_count ?? 0;
      const comparableCount = response.comparable_case_count ?? certifiedCount;
      const notComparableCount = response.not_comparable_case_count ?? 0;
      setBulkCertificationPreview(null);
      setNotice(
        `${certifiedCount} AI ${certifiedCount === 1 ? "recommendation was" : "recommendations were"} accepted by ${reviewerId.trim()} and finalized (${comparableCount} comparable, ${notComparableCount} not comparable). Reporting is not recalculated automatically; each decision remains final until flagged.`,
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
              setSelectionScope("manual");
              setSelectionDeferredCaseCount(0);
              setBatchConfirmOpen(false);
              setBulkCertificationPreview(null);
              setAttributeEvidenceView(null);
              setAttributeBatchRoot("latest");
              setAttributeOffset(0);
            }}
          >
            <option value="">Select a queue</option>
            {queues.map((queue) => (
              <option value={queue.queue_id} key={queue.queue_id}>
                {label(queue.product_pack.id)} · queue v{queue.version} ·{" "}
                {queue.case_count} cases
                {queue.quarantine ? " · QUARANTINED" : ""}
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
              setSelectionScope("manual");
              setSelectionDeferredCaseCount(0);
              setBatchConfirmOpen(false);
              setBulkCertificationPreview(null);
              setAttributeOffset(0);
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
              setSelectionScope("manual");
              setSelectionDeferredCaseCount(0);
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
      {view?.quarantine ? (
        <section className="cert-error" role="alert">
          <strong>Queue quarantined — no decisions carry forward</strong>
          <p>{view.quarantine.reason}</p>
          <small>
            Search, PDP, AI, and human-review history remains available for
            audit only. A clean Product Pack v
            {view.quarantine.successor_product_pack_version} queue will begin
            with zero certified decisions.
          </small>
        </section>
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
            {queueQuarantined ? (
              <span className="button secondary cert-gold-link" aria-disabled>
                Gold set blocked
              </span>
            ) : (
              <a
                className="button secondary cert-gold-link"
                href={`/api/admin/matching-v2/review-queues/${encodeURIComponent(view.queue.queue_id)}/gold-set`}
                target="_blank"
                rel="noreferrer"
              >
                Open certified gold set
              </a>
            )}
          </section>

          <nav
            className="cert-workspace-switch"
            aria-label="Certification workspace view"
          >
            <button
              type="button"
              className={workspaceView === "certification" ? "active" : ""}
              aria-current={
                workspaceView === "certification" ? "page" : undefined
              }
              onClick={() => setWorkspaceView("certification")}
            >
              Match candidates
            </button>
            <button
              type="button"
              className={workspaceView === "attribute-evidence" ? "active" : ""}
              aria-current={
                workspaceView === "attribute-evidence" ? "page" : undefined
              }
              onClick={() => setWorkspaceView("attribute-evidence")}
            >
              Product evidence claims
            </button>
          </nav>

          {workspaceView === "attribute-evidence" ? (
            <section
              className="cert-attribute-index"
              aria-labelledby="cert-attribute-index-title"
            >
              <header className="cert-attribute-index-header">
                <div>
                  <small>Product-level source reconciliation</small>
                  <h3 id="cert-attribute-index-title">
                    Product Evidence Claims
                  </h3>
                  <p>
                    Review each product attribute once across every affected
                    pair. Repeated AI observations are supporting context, not
                    independent proof. Conflicting values remain fail-closed
                    until you select the value proven by the cited images.
                  </p>
                </div>
                <button
                  className="button secondary"
                  type="button"
                  disabled={attributeLoading}
                  aria-busy={attributeLoading}
                  onClick={() =>
                    void loadAttributeEvidence().catch(handleError)
                  }
                >
                  {attributeLoading ? "Refreshing…" : "Refresh claims"}
                </button>
              </header>

              <div className="cert-attribute-filters">
                <label>
                  <span>AI batch lineage</span>
                  <select
                    value={attributeBatchRoot}
                    onChange={(event) => {
                      setAttributeBatchRoot(event.target.value);
                      setAttributeOffset(0);
                    }}
                  >
                    <option value="all">All current AI review batches</option>
                    <option value="latest">Latest retry lineage only</option>
                    {(attributeEvidenceView?.batch_lineages ?? []).map(
                      (lineage) => (
                        <option
                          value={lineage.root_batch_id}
                          key={lineage.root_batch_id}
                        >
                          {formatTimestamp(lineage.latest_activity_at)} ·{" "}
                          {lineage.case_count} cases ·{" "}
                          {lineage.eligible_proposal_count} eligible
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <label>
                  <span>Claim status</span>
                  <select
                    value={attributeClaimStatus}
                    onChange={(event) => {
                      setAttributeClaimStatus(
                        event.target.value as AttributeEvidenceClaimStatus,
                      );
                      setAttributeOffset(0);
                    }}
                  >
                    <option value="awaiting_review">Awaiting review</option>
                    <option value="conflict">Conflicting values</option>
                    <option value="verified">Verified</option>
                    <option value="rejected">Rejected</option>
                    <option value="all">All claims</option>
                  </select>
                </label>
                <label>
                  <span>Product attribute</span>
                  <select
                    value={attributeFilter}
                    onChange={(event) => {
                      setAttributeFilter(event.target.value);
                      setAttributeOffset(0);
                    }}
                  >
                    <option value="all">All attributes</option>
                    {(attributeEvidenceView?.attributes ?? []).map((entry) => (
                      <option value={entry.attribute} key={entry.attribute}>
                        {label(entry.attribute)} · {entry.claim_count}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {attributeEvidenceView ? (
                <>
                  <div className="cert-attribute-metrics">
                    <article>
                      <span>Product attributes</span>
                      <strong>
                        {attributeEvidenceView.summary.claim_count.toLocaleString()}
                      </strong>
                      <small>
                        {attributeEvidenceView.summary.affected_product_count.toLocaleString()}{" "}
                        distinct products
                      </small>
                    </article>
                    <article className="eligible">
                      <span>Awaiting review</span>
                      <strong>
                        {attributeEvidenceView.summary.awaiting_review_count.toLocaleString()}
                      </strong>
                      <small>One consistent value proposed</small>
                    </article>
                    <article className="ineligible">
                      <span>Conflicting claims</span>
                      <strong>
                        {attributeEvidenceView.summary.conflict_count.toLocaleString()}
                      </strong>
                      <small>Multiple values; fail-closed</small>
                    </article>
                    <article>
                      <span>Verified</span>
                      <strong>
                        {attributeEvidenceView.summary.verified_count.toLocaleString()}
                      </strong>
                    </article>
                    <article>
                      <span>Rejected</span>
                      <strong>
                        {attributeEvidenceView.summary.rejected_count.toLocaleString()}
                      </strong>
                    </article>
                    <article>
                      <span>Pair-level observations</span>
                      <strong>
                        {attributeEvidenceView.summary.proposal_count.toLocaleString()}
                      </strong>
                      <small>Collapsed; not counted as independent proof</small>
                    </article>
                  </div>

                  <div className="cert-attribute-boundary">
                    <span>
                      Retry lineage{" "}
                      <code>
                        {attributeEvidenceView.selected_root_batch_id ??
                          "all lineages"}
                      </code>
                    </span>
                    <span>
                      Showing{" "}
                      {attributeEvidenceView.selected_claim_count.toLocaleString()}{" "}
                      product-level claims
                    </span>
                    <span>Decisions update derived evidence only</span>
                  </div>

                  {attributeLoading ? (
                    <div className="builder-loading" role="status">
                      Consolidating product-level evidence claims…
                    </div>
                  ) : attributeEvidenceView.claims.length ? (
                    <div className="cert-attribute-list">
                      {attributeEvidenceView.claims.map((claim) => (
                        <article
                          className="cert-attribute-card"
                          key={claim.claim_checksum}
                        >
                          <div className="cert-attribute-image">
                            {claim.listing.image_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={claim.listing.image_url}
                                alt={claim.listing.title ?? "Product image"}
                              />
                            ) : (
                              <b>No product image</b>
                            )}
                          </div>
                          <div className="cert-attribute-content">
                            <header>
                              <div>
                                <small>
                                  {label(claim.listing.retailer_id)} ·{" "}
                                  {label(claim.attribute)}
                                </small>
                                <h4>{claim.listing.title}</h4>
                                <span>
                                  {claim.listing.brand || "Brand unresolved"} ·
                                  ID {claim.listing.retailer_product_id}
                                  {claim.listing.observed_location_count !==
                                  undefined
                                    ? ` · ${claim.listing.observed_location_count.toLocaleString()} observed`
                                    : ""}
                                </span>
                              </div>
                              <span
                                className={`cert-evidence-decision ${claim.status === "awaiting_review" ? "pending" : claim.status}`}
                              >
                                {label(claim.status)}
                              </span>
                            </header>
                            <div className="cert-attribute-claim">
                              <div>
                                <span>Current governed evidence</span>
                                <strong>
                                  {claim.current_evidence.map((evidence) => (
                                    <small
                                      key={`${evidenceValue(evidence.value)}:${evidence.source ?? "unknown"}`}
                                    >
                                      {evidenceValue(evidence.value)} ·{" "}
                                      {evidence.source
                                        ? label(evidence.source)
                                        : "source unresolved"}
                                    </small>
                                  ))}
                                </strong>
                              </div>
                              <div>
                                <span>Affected match cases</span>
                                <strong>
                                  {claim.affected_case_count.toLocaleString()}
                                  <small>
                                    {claim.counterpart_product_count.toLocaleString()}{" "}
                                    distinct counterpart products
                                  </small>
                                </strong>
                              </div>
                              <div>
                                <span>Retailer context</span>
                                <strong>
                                  {claim.counterpart_retailers
                                    .map(label)
                                    .join(", ") || "No retailer context"}
                                </strong>
                              </div>
                              <div>
                                <span>Proposed values</span>
                                <strong>
                                  {claim.variants.length}
                                  <small>
                                    {claim.proposal_count.toLocaleString()}{" "}
                                    pair-level observations
                                  </small>
                                </strong>
                              </div>
                            </div>
                            <p
                              className={`cert-attribute-relationship ${claim.status}`}
                            >
                              <b>{label(claim.status)}</b>
                              {claim.status_reason}
                            </p>
                            <div className="cert-claim-variants">
                              {claim.variants.map((variant) => (
                                <label
                                  className={`cert-claim-variant ${selectedClaimVariants[claim.claim_checksum] === variant.representative_proposal_checksum ? "selected" : ""}`}
                                  key={variant.value_checksum}
                                >
                                  <span className="cert-claim-variant-title">
                                    <input
                                      type="radio"
                                      name={`claim-${claim.claim_checksum}`}
                                      value={
                                        variant.representative_proposal_checksum
                                      }
                                      checked={
                                        selectedClaimVariants[
                                          claim.claim_checksum
                                        ] ===
                                        variant.representative_proposal_checksum
                                      }
                                      disabled={
                                        claim.status === "verified" ||
                                        claim.status === "rejected"
                                      }
                                      onChange={() =>
                                        setSelectedClaimVariants((current) => ({
                                          ...current,
                                          [claim.claim_checksum]:
                                            variant.representative_proposal_checksum,
                                        }))
                                      }
                                    />
                                    <strong>
                                      {evidenceValue(variant.value)}
                                    </strong>
                                    <small>
                                      {variant.case_count.toLocaleString()}{" "}
                                      affected pairs ·{" "}
                                      {variant.citations.length.toLocaleString()}{" "}
                                      distinct citations ·{" "}
                                      {Math.round(
                                        variant.minimum_confidence * 100,
                                      )}
                                      –
                                      {Math.round(
                                        variant.maximum_confidence * 100,
                                      )}
                                      % confidence
                                    </small>
                                  </span>
                                  <span className="cert-claim-citations">
                                    {variant.citations.map((citation) => (
                                      <a
                                        href={
                                          citation.source_image_url ?? undefined
                                        }
                                        target="_blank"
                                        rel="noreferrer"
                                        key={`${citation.proposal_checksum}:${citation.source_image_url ?? "none"}`}
                                      >
                                        <span>
                                          {citation.source_image_url ? (
                                            // eslint-disable-next-line @next/next/no-img-element
                                            <img
                                              src={citation.source_image_url}
                                              alt="Cited product label"
                                            />
                                          ) : (
                                            <b>No image</b>
                                          )}
                                        </span>
                                        <small>
                                          “
                                          {citation.visible_text ||
                                            "No visible text"}
                                          ”
                                          <em>
                                            {Math.round(
                                              citation.confidence * 100,
                                            )}
                                            % ·{" "}
                                            {label(
                                              citation.counterpart_retailer_id,
                                            )}
                                          </em>
                                        </small>
                                      </a>
                                    ))}
                                  </span>
                                </label>
                              ))}
                            </div>
                            <div className="cert-attribute-links">
                              {claim.listing.product_url ? (
                                <a
                                  href={claim.listing.product_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Open retailer product
                                </a>
                              ) : null}
                              <button
                                type="button"
                                onClick={() => {
                                  setWorkspaceView("certification");
                                  setStatusFilter("all");
                                  setOffset(0);
                                  initialEvidenceOpened.current = false;
                                  const parameters = new URLSearchParams(
                                    window.location.search,
                                  );
                                  parameters.delete("benchmark_product");
                                  parameters.delete("competitor_product");
                                  parameters.set(
                                    claim.listing.retailer_id === "walmart_us"
                                      ? "benchmark_product"
                                      : "competitor_product",
                                    claim.listing.retailer_product_id,
                                  );
                                  window.location.search =
                                    parameters.toString();
                                }}
                              >
                                Open affected match cases
                              </button>
                            </div>
                            {claim.status === "verified" ||
                            claim.status === "rejected" ? (
                              <div className="cert-attribute-decision-form">
                                <p>
                                  <b>
                                    {label(claim.status)} by{" "}
                                    {claim.decision?.reviewer_id ||
                                      "identified administrator"}
                                  </b>
                                  {claim.decision?.rationale ||
                                    "The immutable product-level decision is retained in audit history."}
                                </p>
                              </div>
                            ) : (
                              <div className="cert-attribute-decision-form">
                                <label>
                                  <span>
                                    Product-level evidence decision note
                                  </span>
                                  <textarea
                                    value={
                                      evidenceRationales[
                                        claim.claim_checksum
                                      ] ??
                                      claim.decision?.rationale ??
                                      ""
                                    }
                                    onChange={(event) =>
                                      setEvidenceRationales((current) => ({
                                        ...current,
                                        [claim.claim_checksum]:
                                          event.target.value,
                                      }))
                                    }
                                    placeholder="Explain what the complete cited evidence proves, or why the product-level claim is unreliable."
                                  />
                                </label>
                                <div>
                                  <button
                                    className="button secondary"
                                    type="button"
                                    disabled={busy}
                                    onClick={() =>
                                      void decideAttributeClaim(
                                        claim,
                                        "rejected",
                                      )
                                    }
                                  >
                                    Reject complete claim
                                  </button>
                                  <button
                                    className="button"
                                    type="button"
                                    disabled={busy}
                                    onClick={() =>
                                      void decideAttributeClaim(
                                        claim,
                                        "verified",
                                      )
                                    }
                                  >
                                    Verify selected value
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="cert-empty">
                      <h4>No product evidence claims match these filters</h4>
                      <p>
                        Change the claim status, attribute, retailer, or batch
                        scope. No evidence has been deleted.
                      </p>
                    </div>
                  )}

                  {attributeEvidenceView.selected_claim_count > PAGE_SIZE ? (
                    <nav
                      className="cert-pagination"
                      aria-label="Product evidence claim pages"
                    >
                      <button
                        className="button secondary"
                        type="button"
                        disabled={attributeOffset === 0 || attributeLoading}
                        onClick={() =>
                          setAttributeOffset((current) =>
                            Math.max(0, current - PAGE_SIZE),
                          )
                        }
                      >
                        Previous claims
                      </button>
                      <span>
                        {attributeOffset + 1}–
                        {Math.min(
                          attributeOffset + PAGE_SIZE,
                          attributeEvidenceView.selected_claim_count,
                        )}{" "}
                        of{" "}
                        {attributeEvidenceView.selected_claim_count.toLocaleString()}
                      </span>
                      <button
                        className="button secondary"
                        type="button"
                        disabled={
                          attributeLoading ||
                          attributeOffset + PAGE_SIZE >=
                            attributeEvidenceView.selected_claim_count
                        }
                        onClick={() =>
                          setAttributeOffset((current) => current + PAGE_SIZE)
                        }
                      >
                        Next claims
                      </button>
                    </nav>
                  ) : null}
                </>
              ) : (
                <div className="builder-loading" role="status">
                  Loading product-level evidence claims…
                </div>
              )}
            </section>
          ) : (
            <>
              <form className="cert-replay" onSubmit={createGovernedReplay}>
                <div>
                  <small>Immutable reporting release</small>
                  <h3>Create governed replay</h3>
                  <p>
                    Bind the current certified gold set to its source analysis
                    and queue a new report. The existing publication remains
                    unchanged for audit, unresolved cases stay excluded, and
                    this action does not collect data or call AI.
                  </p>
                </div>
                <label>
                  <span>Source analysis ID</span>
                  <input
                    value={replaySourceAnalysisId}
                    onChange={(event) => {
                      setReplaySourceAnalysisId(event.target.value);
                      setReplayResult(null);
                      if (event.target.value.trim()) setError(null);
                    }}
                    placeholder="source-analysis-id"
                    autoComplete="off"
                  />
                  <small>
                    Use the analysis ID before any -match-v2 suffix.
                  </small>
                </label>
                <button
                  className="button primary"
                  type="submit"
                  disabled={
                    busy || queueQuarantined || !replaySourceAnalysisId.trim()
                  }
                >
                  {busy ? "Creating replay…" : "Create governed replay"}
                </button>
                {replayResult ? (
                  <dl className="cert-replay-result">
                    <div>
                      <dt>Analysis run</dt>
                      <dd>{replayResult.analysis_run_id}</dd>
                    </div>
                    <div>
                      <dt>Certified</dt>
                      <dd>
                        {replayResult.coverage.certified_count.toLocaleString()}
                      </dd>
                    </div>
                    <div>
                      <dt>Unresolved</dt>
                      <dd>
                        {replayResult.coverage.unresolved_count.toLocaleString()}
                      </dd>
                    </div>
                  </dl>
                ) : null}
              </form>

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
                    Select cases on this page or prepare every eligible
                    candidate in the current queue and competitor filter, up to
                    the governed {aiPolicy.max_batch_cases.toLocaleString()}
                    -case run limit. Drafts remain advisory, cannot certify a
                    match, and use product images only when critical structured
                    evidence is incomplete or conflicting.
                  </p>
                </div>
                <label className="cert-ai-select-all">
                  <input
                    type="checkbox"
                    checked={pageSelectionComplete}
                    disabled={
                      queueQuarantined ||
                      !aiPolicy.enabled ||
                      !eligibleCases.length ||
                      pageSelectionCapacity === 0
                    }
                    onChange={(event) => {
                      const pageCaseIds = eligibleCases.map(
                        (reviewCase) => reviewCase.case_id,
                      );
                      setSelectedCaseIds((current) =>
                        event.target.checked
                          ? [...new Set([...current, ...pageCaseIds])].slice(
                              0,
                              aiPolicy.max_batch_cases,
                            )
                          : current.filter(
                              (caseId) => !pageCaseIds.includes(caseId),
                            ),
                      );
                      setSelectionScope("manual");
                      setSelectionDeferredCaseCount(0);
                      setBatchConfirmOpen(false);
                    }}
                  />
                  <span>
                    Select eligible cases on this page
                    <small>
                      {eligibleCases.length.toLocaleString()} without an
                      existing draft or final decision; up to{" "}
                      {pageSelectionCapacity.toLocaleString()} fit in the
                      current batch
                    </small>
                  </span>
                </label>
                <div className="cert-ai-batch-actions">
                  <span>
                    <strong>{selectedCaseIds.length}</strong> selected
                    {selectedCaseIds.length ? (
                      <>
                        <small>
                          Maximum policy exposure: $
                          {selectedMaximumCost.toFixed(2)}
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
                    disabled={
                      busy ||
                      queueQuarantined ||
                      !aiPolicy.enabled ||
                      !selectedCaseIds.length
                    }
                    aria-busy={busy}
                    onClick={openBatchConfirmation}
                  >
                    {selectedCaseIds.length
                      ? `Review ${selectedCaseIds.length} selected with AI`
                      : "Review selected with AI"}
                  </button>
                  <button
                    className="button secondary"
                    type="button"
                    disabled={
                      busy ||
                      queueQuarantined ||
                      !aiPolicy.enabled ||
                      aiPolicy.queue_wide_selection !== true
                    }
                    aria-busy={busy}
                    onClick={() =>
                      void openQueueWideAIReviewConfirmation(
                        "product_evidence_coverage",
                      )
                    }
                  >
                    {aiPolicy.queue_wide_selection !== true
                      ? "Product-evidence review unavailable"
                      : busy
                        ? "Assessing product evidence…"
                        : "Review distinct product evidence"}
                  </button>
                  <button
                    className="button primary"
                    type="button"
                    disabled={
                      busy ||
                      queueQuarantined ||
                      !aiPolicy.enabled ||
                      aiPolicy.queue_wide_selection !== true
                    }
                    aria-busy={busy}
                    onClick={() =>
                      void openQueueWideAIReviewConfirmation("all_cases")
                    }
                  >
                    {aiPolicy.queue_wide_selection !== true
                      ? "Queue-wide review unavailable"
                      : busy
                        ? "Assessing eligible queue…"
                        : competitorFilter === "all"
                          ? "Review all eligible with AI"
                          : `Review all eligible ${label(competitorFilter)} cases`}
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
                      <strong>{aiDraftStatusCounts.succeeded}</strong> drafts
                      ready
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
                          {latestAIBatch.task_count} reached a terminal state
                        </strong>
                        <span>
                          Submitted{" "}
                          {formatTimestamp(latestAIBatch.submitted_at)} by{" "}
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
                          style={{
                            width: `${latestAIBatch.progress_percent}%`,
                          }}
                        />
                      </div>
                      <div className="cert-ai-batch-meta">
                        <span>
                          {latestAIBatch.succeeded} drafts ready ·{" "}
                          {latestAIBatch.needs_review} failed
                        </span>
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
                      disabled={
                        busy ||
                        queueQuarantined ||
                        !aiPolicy.enabled ||
                        !retryableCases.length
                      }
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
                        Bulk accept AI certification recommendations
                      </h3>
                      <p>
                        The app finds completed comparable and not-comparable AI
                        recommendations across the pending queue and current
                        retailer filter, then the server prepares up to 50 at a
                        time. Insufficient-evidence proposals and true
                        eligibility failures stay blocked; evidence and
                        confidence concerns are shown as warnings for your
                        explicit decision.
                      </p>
                    </div>
                    <button
                      className="button secondary"
                      type="button"
                      disabled={
                        busy ||
                        queueQuarantined ||
                        !aiDraftStatusCounts.succeeded
                      }
                      aria-busy={busy}
                      onClick={() => void assessBulkAIRecommendations()}
                    >
                      {busy
                        ? "Assessing…"
                        : "Assess queue-wide recommendations"}
                    </button>
                  </header>
                  <div
                    className="cert-bulk-guardrails"
                    aria-label="Bulk acceptance guardrails"
                  >
                    <span>Comparable or not comparable</span>
                    <span>Valid governed draft</span>
                    <span>No known third-party seller</span>
                    <span>Immutable source evidence</span>
                    <span>Administrator confirmation</span>
                  </div>
                  <p className="cert-bulk-boundary">
                    Engine disagreement, incomplete deterministic evidence, AI
                    conflicts, and confidence limits remain visible as advisory
                    warnings. Your explicit bulk approval accepts each displayed
                    AI recommendation, is recorded under your reviewer identity,
                    is final until flagged, and does not trigger reanalysis
                    automatically.
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
                            {bulkCertificationPreview.eligible_case_count}{" "}
                            eligible
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
                                  <span>
                                    {bulkCandidateVerdict(candidate) ===
                                    "comparable"
                                      ? "matches"
                                      : "is not comparable with"}
                                  </span>
                                  <BulkProductIdentity
                                    product={candidate.competitor_product}
                                  />
                                </div>
                                <div className="cert-bulk-evidence-summary">
                                  <strong>
                                    {bulkCandidateVerdict(candidate) ===
                                    "comparable"
                                      ? label(candidate.recommended_tier)
                                      : "Not comparable"}
                                  </strong>
                                  <span>
                                    {Math.round(
                                      candidate.critical_coverage * 100,
                                    )}
                                    % critical evidence ·{" "}
                                    {label(candidate.engine_status)}
                                  </span>
                                  {bulkCandidateVerdict(candidate) ===
                                  "comparable" ? (
                                    <span>
                                      Price comparison:{" "}
                                      {(
                                        candidate.recommended_comparison_bases ??
                                        []
                                      )
                                        .map(label)
                                        .join(" + ")}
                                    </span>
                                  ) : null}
                                  <p>{candidate.ai_rationale}</p>
                                  {candidate.warnings.length ? (
                                    <ul className="cert-bulk-warnings">
                                      {candidate.warnings.map((warning) => (
                                        <li key={warning}>{warning}</li>
                                      ))}
                                    </ul>
                                  ) : null}
                                </div>
                              </article>
                            ),
                          )}
                        </div>
                      ) : (
                        <p className="cert-bulk-empty">
                          No AI recommendation passed the required certification
                          gates. Review the blocking exclusions before
                          proceeding.
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
                      {bulkCertificationPreview.warning_summary.length ? (
                        <details className="cert-bulk-exclusions" open>
                          <summary>
                            Advisory warnings on accepted recommendations
                          </summary>
                          <ul>
                            {bulkCertificationPreview.warning_summary.map(
                              (warning) => (
                                <li key={warning.warning_code}>
                                  <b>{warning.case_count}</b> {warning.warning}
                                </li>
                              ),
                            )}
                          </ul>
                        </details>
                      ) : null}
                      <footer>
                        <p>
                          <b>Human confirmation required.</b> You are accepting
                          each displayed comparable or not-comparable
                          outcome—not delegating the decision to AI. The
                          complete AI evidence rationale is copied into each
                          final reviewer comment for auditability.
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
                            : `Finalize ${bulkCertificationPreview.eligible_case_count} ${bulkCertificationPreview.eligible_case_count === 1 ? "recommendation" : "recommendations"}`}
                        </button>
                      </footer>
                    </div>
                  ) : null}
                </section>
                {!aiPolicy.enabled ? (
                  <p className="cert-ai-policy-note">
                    The advisory worker is not enabled in this environment.
                    Human certification remains available.
                  </p>
                ) : null}
                {batchConfirmOpen ? (
                  <div className="cert-ai-batch-confirm" role="alert">
                    <div>
                      <strong>
                        Queue {selectedCaseIds.length.toLocaleString()} advisory
                        drafts?
                      </strong>
                      <p>
                        {selectionScope === "queue-wide"
                          ? `This is the complete currently eligible ${competitorFilter === "all" ? "queue" : label(competitorFilter) + " scope"}${selectionDeferredCaseCount ? ` within the ${aiPolicy.max_batch_cases.toLocaleString()}-case governed run limit; ${selectionDeferredCaseCount.toLocaleString()} additional eligible cases will remain for a subsequent run` : ""}. `
                          : selectionScope === "product-evidence"
                            ? `This is a deterministic minimum-coverage scope: ${selectedCaseIds.length.toLocaleString()} pair cases cover ${selectionProductEvidenceCount.toLocaleString()} distinct products that currently lack governed hard-attribute evidence. Verified product evidence will be reused across every applicable case in this immutable queue; ${selectionDeferredCaseCount.toLocaleString()} other pair cases are intentionally deferred. `
                            : "This is the explicitly selected page scope. "}
                        Model: {aiPolicy.model_id}. The configured per-request
                        ceiling is ${aiPolicy.max_request_cost_usd.toFixed(2)}{" "}
                        per case, so the worst-case policy exposure for this run
                        is ${selectedMaximumCost.toFixed(2)}. Actual usage is
                        recorded per case. Human review is still required for
                        every decision.
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
                        This creates new linked tasks; it does not reset or
                        erase prior attempts. Model: {aiPolicy.model_id}.
                        Maximum new policy exposure: $
                        {retryMaximumCost.toFixed(2)}. Each new task still
                        requires a human decision.
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
                          setSelectionScope("manual");
                          setSelectionDeferredCaseCount(0);
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
                      <ProductIdentity
                        listing={reviewCase.competitor_listing}
                      />
                    </div>
                    <div className="cert-case-meta">
                      <span
                        className={`cert-status ${reviewCase.review_status}`}
                      >
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
                      {reviewCase.certification_blockers?.length ? (
                        <span className="cert-package-blocked">
                          {reviewCase.certification_blockers.some(
                            (issue) => issue.attribute === "volume_oz",
                          )
                            ? "Package size blocked"
                            : "Compatibility blocked"}
                        </span>
                      ) : null}
                    </div>
                    <button
                      className="button secondary"
                      type="button"
                      onClick={() => setActiveCaseId(reviewCase.case_id)}
                    >
                      {["approved", "rejected"].includes(
                        reviewCase.review_status,
                      )
                        ? "View decision"
                        : "Review evidence"}
                    </button>
                  </article>
                ))}
                {view.cases.length === 0 ? (
                  <section className="cert-empty">
                    <h2>No cases match this status</h2>
                    <p>
                      Select another queue status or import a new review queue.
                    </p>
                  </section>
                ) : null}
              </div>
              {view.selected_case_count > PAGE_SIZE ? (
                <nav
                  className="cert-pagination"
                  aria-label="Review queue pages"
                >
                  <button
                    className="button secondary"
                    type="button"
                    disabled={busy || offset === 0}
                    onClick={() => {
                      setOffset((current) => Math.max(0, current - PAGE_SIZE));
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
                    if (event.target === event.currentTarget)
                      closeEvidenceDrawer();
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
                        <ProductIdentity
                          listing={activeCase.benchmark_listing}
                        />
                        <span className="cert-pair-mark">compared with</span>
                        <ProductIdentity
                          listing={activeCase.competitor_listing}
                        />
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
                              The draft can inspect incomplete label evidence,
                              but it cannot approve a relationship or alter
                              reporting.
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
                                {aiPolicy.max_retry_rounds} · Prior task
                                preserved
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
                                {activeCase.ai_draft.output_document.result
                                  .comparison_basis_proposal?.length ? (
                                  <small>
                                    Price comparison:{" "}
                                    {activeCase.ai_draft.output_document.result.comparison_basis_proposal
                                      .map(label)
                                      .join(" + ")}
                                  </small>
                                ) : null}
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
                                {activeCase.attribute_evidence_reconciliation
                                  ?.proposals.length ? (
                                  <details className="cert-reconciliation" open>
                                    <summary>
                                      Reconcile cited label attributes before
                                      certification
                                    </summary>
                                    <p>
                                      AI proposals are advisory. Only eligible
                                      image evidence that you explicitly verify
                                      is applied to the derived certification
                                      view; source PDP and queue records remain
                                      immutable.
                                    </p>
                                    <div className="cert-reconciliation-list">
                                      {activeCase.attribute_evidence_reconciliation.proposals.map(
                                        (proposal) => (
                                          <article
                                            key={proposal.proposal_checksum}
                                          >
                                            <header>
                                              <div>
                                                <strong>
                                                  {label(proposal.attribute)}
                                                </strong>
                                                <small>
                                                  {proposal.listing_role
                                                    ? `${label(proposal.listing_role)} product`
                                                    : "Listing unresolved"}
                                                  {" · "}
                                                  {Math.round(
                                                    proposal.confidence * 100,
                                                  )}
                                                  % confidence
                                                </small>
                                              </div>
                                              <span
                                                className={`cert-evidence-decision ${proposal.decision?.decision ?? (proposal.eligible ? "pending" : "ineligible")}`}
                                              >
                                                {proposal.decision
                                                  ? label(
                                                      proposal.decision
                                                        .decision,
                                                    )
                                                  : proposal.eligible
                                                    ? "Awaiting verification"
                                                    : "Not eligible"}
                                              </span>
                                            </header>
                                            <dl>
                                              <div>
                                                <dt>Proposed value</dt>
                                                <dd>
                                                  {evidenceValue(
                                                    proposal.normalized_value,
                                                  )}
                                                </dd>
                                              </div>
                                              <div>
                                                <dt>Visible label text</dt>
                                                <dd>
                                                  {proposal.visible_text ??
                                                    "Not supplied"}
                                                </dd>
                                              </div>
                                            </dl>
                                            {proposal.source_image_url ? (
                                              <a
                                                href={proposal.source_image_url}
                                                target="_blank"
                                                rel="noreferrer"
                                              >
                                                Open the exact cited product
                                                image
                                              </a>
                                            ) : null}
                                            {!proposal.eligible ? (
                                              <small>
                                                Not eligible:{" "}
                                                {proposal.ineligibility_reasons
                                                  .map(label)
                                                  .join("; ")}
                                              </small>
                                            ) : (
                                              <>
                                                <label>
                                                  <span>Verification note</span>
                                                  <textarea
                                                    value={
                                                      evidenceRationales[
                                                        proposal
                                                          .proposal_checksum
                                                      ] ??
                                                      proposal.decision
                                                        ?.rationale ??
                                                      ""
                                                    }
                                                    onChange={(event) =>
                                                      setEvidenceRationales(
                                                        (current) => ({
                                                          ...current,
                                                          [proposal.proposal_checksum]:
                                                            event.target.value,
                                                        }),
                                                      )
                                                    }
                                                    placeholder="State what the cited label visibly proves or why it is unreliable."
                                                  />
                                                </label>
                                                <div className="cert-reconciliation-actions">
                                                  <button
                                                    className="button secondary"
                                                    type="button"
                                                    disabled={busy}
                                                    onClick={() =>
                                                      void decideAttributeEvidence(
                                                        activeCase.case_id,
                                                        proposal,
                                                        "rejected",
                                                      )
                                                    }
                                                  >
                                                    Reject evidence
                                                  </button>
                                                  <button
                                                    className="button"
                                                    type="button"
                                                    disabled={busy}
                                                    onClick={() =>
                                                      void decideAttributeEvidence(
                                                        activeCase.case_id,
                                                        proposal,
                                                        "verified",
                                                      )
                                                    }
                                                  >
                                                    Verify & apply
                                                  </button>
                                                </div>
                                              </>
                                            )}
                                          </article>
                                        ),
                                      )}
                                    </div>
                                  </details>
                                ) : null}
                                <button
                                  className="button secondary"
                                  type="button"
                                  onClick={() => adoptAIProposal(activeCase)}
                                >
                                  Copy proposal into my review
                                </button>
                                {activeCase.ai_draft.usage
                                  ?.estimated_cost_usd != null ? (
                                  <small>
                                    Recorded estimated cost: $
                                    {activeCase.ai_draft.usage.estimated_cost_usd.toFixed(
                                      4,
                                    )}
                                  </small>
                                ) : null}
                              </>
                            ) : activeCase.ai_draft.last_error_message ? (
                              <div
                                className="cert-ai-error-detail"
                                role="status"
                              >
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
                                  {activeCase.ai_draft.max_attempts} · Last
                                  activity{" "}
                                  {formatTimestamp(
                                    activeCase.ai_draft.updated_at,
                                  )}
                                </small>
                                {activeCase.ai_draft.status ===
                                "needs_review" ? (
                                  (activeCase.ai_draft.retry_sequence ?? 0) <
                                    aiPolicy.max_retry_rounds &&
                                  !_isRetryIntegrityFailure(
                                    activeCase.ai_draft.last_error_message ??
                                      "",
                                  ) ? (
                                    <button
                                      className="button secondary"
                                      type="button"
                                      disabled={
                                        busy ||
                                        queueQuarantined ||
                                        !aiPolicy.enabled
                                      }
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
                                retryConfirmCaseIds.includes(
                                  activeCase.case_id,
                                ) ? (
                                  <div className="cert-ai-drawer-retry-confirm">
                                    <strong>
                                      Confirm a new linked retry task?
                                    </strong>
                                    <p>
                                      Prior attempts, this exact error, and any
                                      recorded cost remain preserved. The
                                      maximum new policy exposure is $
                                      {aiPolicy.max_request_cost_usd.toFixed(2)}
                                      .
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
                                The worker is preparing this advisory draft.
                                Attempt {activeCase.ai_draft.attempt_count} of{" "}
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
                            <small>
                              {label(listing.retailer_id)} governance
                            </small>
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
                      {activeCase.certification_blockers?.length ? (
                        <section
                          className="cert-certification-blocker"
                          role="alert"
                        >
                          <div>
                            <small>Current Product Pack guardrail</small>
                            <h3>This pair cannot be approved as comparable</h3>
                            <p>
                              Package and compatibility rules use the current
                              Product Pack even when this queue was created
                              under an older version. Choose Reject match when
                              the values conflict, or Needs evidence when a
                              required value is unresolved.
                            </p>
                          </div>
                          <ul>
                            {activeCase.certification_blockers.map((issue) => (
                              <li key={issue.attribute}>
                                <b>{label(issue.attribute)}</b>
                                <span>
                                  {evidenceValue(issue.benchmark_value)} versus{" "}
                                  {evidenceValue(issue.competitor_value)} ·{" "}
                                  {label(issue.outcome)}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </section>
                      ) : null}
                      <section className="cert-evidence">
                        <h3>Attribute evidence</h3>
                        <div role="table">
                          <div role="row" className="cert-evidence-head">
                            <span>Attribute</span>
                            <span>Primary</span>
                            <span>Competitor</span>
                            <span>Outcome</span>
                          </div>
                          {activeCase.edge.attribute_evidence.map(
                            (evidence) => (
                              <div role="row" key={evidence.attribute}>
                                <span data-label="Attribute">
                                  <b>{label(evidence.attribute)}</b>
                                  <small>{label(evidence.role)}</small>
                                  {evidence.queue_role &&
                                  evidence.queue_role !== evidence.role ? (
                                    <small>
                                      Queue role: {label(evidence.queue_role)} ·
                                      current policy applies
                                    </small>
                                  ) : null}
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
                            ),
                          )}
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
                                  ? JSON.stringify(
                                      listing.pdp_evidence,
                                      null,
                                      2,
                                    )
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
                            <b>
                              Final decision: {label(activeCase.review_status)}
                            </b>
                            {activeCase.final_decision.rationale}
                            <small>
                              Decided by {activeCase.final_decision.reviewer_id}
                            </small>
                          </p>
                          <label className="cert-rationale">
                            <span>Reason to flag this decision</span>
                            <textarea
                              value={
                                drafts[activeCase.case_id]?.rationale ?? ""
                              }
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
                            disabled={busy || queueQuarantined}
                            onClick={() =>
                              void submitReview(
                                activeCase,
                                "insufficient_evidence",
                              )
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
                                  drafts[activeCase.case_id]?.verdict ===
                                  verdict
                                    ? "selected"
                                    : ""
                                }
                                type="button"
                                key={verdict}
                                disabled={
                                  queueQuarantined ||
                                  (verdict === "comparable" &&
                                    Boolean(
                                      activeCase.certification_blockers?.length,
                                    ))
                                }
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
                                queueQuarantined ||
                                drafts[activeCase.case_id]?.verdict !==
                                  "comparable"
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
                              value={
                                drafts[activeCase.case_id]?.rationale ?? ""
                              }
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
                            disabled={
                              busy ||
                              queueQuarantined ||
                              (drafts[activeCase.case_id]?.verdict ===
                                "comparable" &&
                                Boolean(
                                  activeCase.certification_blockers?.length,
                                ))
                            }
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
          )}
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
