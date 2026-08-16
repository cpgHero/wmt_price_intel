# Phase 13.7 — Guarded Bulk AI Match Certification

## Outcome

Match Certification can turn a bounded set of corroborated AI match recommendations into final
human decisions without requiring an administrator to submit each case separately. The workflow is
not automatic approval: the server owns the eligibility policy, presents a checksum-bound preview,
and requires one explicit administrator confirmation.

## Trust boundary

- AI remains advisory and cannot write a certification decision by itself.
- The administrator is the final actor recorded on every resulting submission.
- The deterministic engine must independently agree with the AI-recommended tier.
- Bulk acceptance never recalculates reports. Reanalysis remains an explicit later action.
- An approved decision is final until someone explicitly flags it for re-review.
- Comparable-substitute and custom-approved tiers are excluded from bulk acceptance.

## Eligibility policy v1.0.0

A case is bulk eligible only when all of the following are true:

1. The case is pending and has no final human decision.
2. The latest AI task succeeded and recommends `comparable`.
3. The recommended tier is `exact_item`, `exact_specification`, or `equivalent_product`.
4. The deterministic engine proposes the same tier and has not rejected, blocked, or marked the
   case ineligible.
5. Deterministic critical-evidence coverage equals 100%.
6. The AI draft reports no unresolved conflict.
7. Every Product Pack `hard_blocker` attribute resolves to a match.
8. Every AI-proposed attribute has confidence of at least 0.85.
9. Neither listing is known to be an excluded third-party marketplace offer.
10. The case retains immutable evidence references.

Policy failures are not hidden. The preview groups exclusion reasons and keeps those cases in the
individual review workflow.

## Preview and commit protocol

1. The administrator filters the queue and requests an assessment of the completed affirmative AI
   recommendations visible on the page, up to 50 cases.
2. The API reloads each current case, final decision, and latest AI task from Postgres and evaluates
   the server-owned policy.
3. For the eligible set, the API hashes the queue ID/version, policy checksum, case checksums, AI
   task IDs, AI output checksums, and recommended tiers into a confirmation checksum.
4. The UI displays the eligible product pairs, recommended tiers, critical coverage, AI rationale,
   and grouped exclusion reasons.
5. The administrator explicitly confirms the exact eligible set.
6. The API obtains the same per-case advisory locks used by individual certification, reloads and
   re-evaluates every case, and rejects the whole action if a case changed or the checksum is stale.
7. One immutable `matching_v2_bulk_certification_action` audit record and one normal
   `matching_v2_review_submission` per case are committed atomically.
8. A retry with the same reviewer and checksum returns the original action instead of duplicating
   decisions.

## Database changes

Migration `0034_bulk_ai_certification` adds:

- `matching_v2_bulk_certification_action`, an immutable action/audit record;
- `matching_v2_review_submission.bulk_action_id`, linking each final human decision to its bulk
  confirmation; and
- queue/action and submission/action indexes.

The migration is reversible and leaves existing individual submissions unchanged with a null bulk
action reference.

## API

- `POST /api/v1/matching-v2/review-queues/{queue_id}/ai-bulk-certification/preview`
- `POST /api/v1/matching-v2/review-queues/{queue_id}/ai-bulk-certification/commit`

Both routes require the existing protected administrator surface. The Next.js administrator proxy
continues to enforce its signed administrator session and same-origin mutation checks.

## Verification gates

- Policy unit tests cover eligible, conflict, tier disagreement, seller exclusion, and immutable
  checksum behavior.
- Service tests cover unique bounded case IDs and reviewer-attributed commit requests.
- Browser tests cover preview, visible exclusion reasons, explicit confirmation, request payload,
  success wording, and the no-automatic-reanalysis boundary.
- Migration upgrade/downgrade, full API tests, web typecheck/lint/unit/e2e, production builds, and
  Railway health checks are required before this phase is marked deployed.

## Production verification

- Commit `d322836` passed the complete GitHub Actions pipeline, including Postgres migration
  upgrade/downgrade/re-upgrade checks, API tests, browser tests, and all service container builds.
- Railway deployed the web and API services successfully; the API pre-deploy migration advanced the
  production database to the new migration head.
- The protected Match Certification page rendered the guarded bulk-certification panel, its policy
  guardrails, and its safe no-eligible-recommendations state against the current banana queue.
- Production verification was read-only: no live match decision was approved, rejected, or reopened.
