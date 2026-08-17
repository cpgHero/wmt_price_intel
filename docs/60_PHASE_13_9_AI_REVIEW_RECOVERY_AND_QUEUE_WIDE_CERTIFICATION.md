# Phase 13.9 — AI Review Recovery and Queue-Wide Certification

Status: implemented; production verification pending

## Why this change exists

Production Ground Beef evidence showed that AI review work was neither stuck nor silent. The worker
completed each paid request, but 51 latest tasks ended in `needs_review` because an otherwise usable
structured response included an image-derived attribute without both exact visible evidence and the
URL of an image sent in that request. Replaying the same sealed input and static schema reproduced
the same deterministic validation failure.

The bulk-certification audit showed a separate presentation defect: the Ground Beef bulk action
successfully committed one case, but the browser had discovered candidates only among the 50 rows
visible on the current page. The control was therefore not queue-wide even though its language
suggested a broader scope.

## AI response-contract repair

The matching-review provider now builds a request-specific strict response schema:

- when no image is sent, `evidence_source=image` is impossible and both image citation fields must
  be null;
- when images are sent, an image proposal must include non-empty visible evidence and must select
  an exact URL from the request's allowlist;
- structured proposals must keep the image citation fields null; and
- the existing post-response validator remains in place as defense in depth.

The governed prompt is version `1.0.2`. The model input includes an explicit image-evidence policy
and exact allowed image URLs. Search/PDP/brand/seller/Product Pack evidence remains sealed,
non-authoritative AI output remains human-gated, and images still enter only when critical
structured evidence is missing or conflicting.

Existing terminal tasks are immutable. Administrators create new lineage-linked retries under the
new prompt/schema. The manual ceiling is four rounds so the one Ground Beef lineage already at the
prior three-round ceiling can receive the remediation without deleting its history. No retry is
submitted automatically and every paid call retains the configured per-request ceiling.

Migration `0036_ai_review_recovery` replaces the retry-lineage check constraint with the same
immutable-lineage rule and a maximum sequence of four. Its downgrade restores the three-round
constraint; downgrade is valid only before a fourth-round task exists, as expected for a data-bearing
operational migration.

## Queue-wide bulk discovery

The Match Certification UI now discovers pending, successfully completed, affirmative AI
recommendations across the full queue and active competitor-retailer filter, not merely the current
page. It scans paginated queue views and sends up to 500 exact case IDs to the existing protected
preview endpoint. The server evaluates the entire submitted set, binds at most the first 50 eligible
relationships into one confirmation, and marks additional passing relationships as deferred to the
next bounded batch. This prevents 50 ineligible relationships from hiding eligible work later in the
queue.

The server-owned v1.0.0 guardrails are unchanged. The administrator still reviews a checksum-bound
eligible set and explicit exclusion reasons before committing. Every committed relationship:

- creates the normal final human review submission;
- records the administrator identity;
- copies the complete AI evidence rationale into the final rationale/comment;
- links to the immutable bulk action and AI output checksum; and
- remains final until flagged without automatically rerunning reporting.

If more than 50 recommendations are pending, the administrator confirms successive bounded batches.

## Production evidence collected before the fix

Read-only production queries and Railway logs established:

- 210 Ground Beef cases had a latest AI task;
- 159 latest tasks succeeded and 51 latest tasks needed attention;
- every observed needs-attention task had the same safe validation error: `image evidence must cite
  visible evidence and an input image`;
- linked retries had rescued 10 cases, proving the queue and worker were functioning, while identical
  invalid outputs continued to fail; and
- Ground Beef had one recorded bulk action with one linked final submission. Railway recorded HTTP
  200 for its preview and HTTP 201 for its commit, confirming that the prior “no updates” symptom
  was page-scoped candidate discovery rather than a failed database transaction.

No live match was approved, rejected, flagged, or reopened during this investigation.

## Verification gate

- Python provider tests cover image allowlisting, no-image schema restrictions, human gating, and
  rejection of uncited image claims.
- API tests cover retry and bulk-certification policy behavior.
- TypeScript typecheck and lint cover the queue-wide discovery path.
- Playwright covers an affirmative recommendation located beyond a visible page of terminal
  failures, previewing exclusions, explicit commit, rationale visibility, and plain-text failures.
- Production verification must confirm the new prompt/schema deployment, one bounded AI retry, and
  the protected queue-wide preview without accepting a live match.
