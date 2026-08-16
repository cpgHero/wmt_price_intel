# Phase 13.6 — AI Review Batch Observability

Status: deployed and production-verified

## Outcome

Match Certification treats every user-submitted AI review request as one durable batch. Progress is
derived from Postgres across the complete certification queue, not from the cases visible on the
current page.

## Control-plane changes

- `matching_v2_ai_review_batch` records the queue, requesting administrator, governed prompt/model,
  requested case count, and creation time.
- Every `matching_v2_ai_review_task` belongs to exactly one batch. Existing tasks are backfilled into
  one-case legacy batches during migration.
- Batch idempotency binds queue, selected case IDs, model, and prompt checksum. The first requesting
  administrator remains the recorded requester; an exact network retry reuses that batch.
- Queue reads return latest-task counts across every case plus the latest batch's task counts,
  timestamps, progress percentage, cost, and deterministic ETA estimate.

## Worker behavior

- Tasks retain `FOR UPDATE SKIP LOCKED` claims, leases, two-attempt retry policy, and terminal
  `needs_review` state.
- `MATCHING_V2_AI_REVIEW_CONCURRENCY` defaults to `2` and is clamped to `1–4` per worker process.
- Each task logs start, success, retry, or needs-attention using task/batch/model/attempt metadata;
  product evidence and secrets are excluded from logs.

## Administrator experience

- Queue-wide queued, reviewing, ready, and needs-attention counts continue refreshing while any
  task is active—even if the task is outside the current page or retailer filter.
- The latest batch displays completed/total, a progress bar, submission and completion timestamps,
  estimated time remaining after the first completion, and recorded model cost.
- A failed draft's evidence drawer shows the safe error type/message, attempt count, and last
  activity time. It never converts an AI draft into a certification decision.
- Stale network responses cannot overwrite a newer filtered queue response.

## Verification evidence

1. GitHub Actions run `31967540651` passed migration upgrade, 471 Python tests, contract checks,
   migration downgrade-to-base and upgrade-to-head, 58 TypeScript tests, eight browser tests, and
   all four container builds.
2. Railway API pre-deploy migration reached `0033_ai_review_batches`; API and web readiness passed.
3. The production banana queue returned queue-wide totals of 65 ready drafts and three
   needs-attention drafts. The latest historical one-case batch showed its completion time and
   recorded cost.
4. A production needs-attention drawer showed the governed error type, safe message, attempt two of
   two, and last activity timestamp. No additional paid OpenAI request was required for deployment
   verification.
5. Newly submitted multi-case batches will retain their complete batch membership. Pre-migration
   tasks are intentionally represented as one-case legacy batches because the former schema did not
   preserve reliable original batch membership.
