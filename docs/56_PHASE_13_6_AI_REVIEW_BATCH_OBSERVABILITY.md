# Phase 13.6 — AI Review Batch Observability

Status: implemented; production verification pending

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

## Verification required

1. Migrate up, down, and up against the integration database.
2. Run API, agent, web type/build, and Match Certification browser tests.
3. Submit a multi-case production batch and verify queue-wide progress, two simultaneous worker
   starts, terminal totals, cost, and automatic polling.
4. Confirm OpenAI request spend remains inside the approved per-request and overall budget.
