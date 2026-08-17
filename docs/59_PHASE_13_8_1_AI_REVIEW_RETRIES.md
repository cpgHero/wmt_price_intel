# Phase 13.8.1 — Governed AI Review Retries

Status: deployed and production-verified

## Outcome

Match Certification administrators can reanalyze terminal `needs_review` AI tasks without erasing
the failed work. A confirmed retry creates a new durable task and links it to the prior terminal
task. The prior task remains the audit record for its attempts, safe error, usage, and estimated
cost.

This workflow remains certification assistance. It does not approve a relationship, change a final
decision, or trigger report reanalysis.

## Data and queue contract

- `matching_v2_ai_review_task.retry_of_task_id` identifies the immediately preceding terminal task.
- `retry_sequence` starts at zero for original tasks and increments for every administrator retry.
- `retry_reason` records why the administrator crossed the paid-call boundary again.
- A terminal task can have only one direct child retry. A later retry links to the latest failed
  retry, producing an immutable chain.
- Every retry receives a new batch and task ID, resets only the new task's automatic-attempt counter,
  and retains the normal `FOR UPDATE SKIP LOCKED` claim, lease, and two-attempt worker behavior.
- Administrator retry rounds are normally a bounded recovery tool and are capped at four per case.
  The fourth round allows the request-bound image-citation remediation introduced in Phase 13.9 to
  recover legacy terminal failures without erasing the first three attempts. The migration enforces
  the lineage range and the API enforces the operating policy.

## Guardrails

The retry API accepts 1–25 unique case IDs and rechecks the current state inside one transaction.
It rejects:

1. a missing case or missing prior AI task;
2. a latest task that is not a terminal `needs_review` failure;
3. any case with queued or running AI work;
4. an already finalized comparable or not-comparable decision;
5. a known third-party marketplace seller;
6. a case at the four-round administrator retry ceiling; or
7. a governed prompt/input checksum failure, which requires engineering correction rather than
   another paid call.

Per-case transaction advisory locks serialize concurrent retry requests. The lineage uniqueness
constraint provides a second duplicate-work defense. The API has no OpenAI credential; the worker
retains the sealed key and the configured per-request cost ceiling.

## Administrator experience

- The queue status area offers a bounded bulk retry for retryable needs-attention cases on the
  current filtered page. Each confirmed batch remains capped at 25 paid calls.
- The evidence drawer offers an individual retry beside the exact terminal error.
- Both paths require a reviewer identity and a separate confirmation showing the model, number of
  new tasks, maximum policy exposure, and the fact that prior history remains preserved.
- The drawer shows the current manual retry round. Integrity failures explain why retry is blocked.
- After acceptance, normal durable queue status and automatic polling resume. The resulting AI draft
  still requires a human approval, rejection, or flag decision.

## Verification

The proportional automated gate covers request validation, advisory output, immutable-history
behavior, seller/finalization/integrity guards, retry policy classification, the protected API
route, TypeScript types, and Playwright individual/bulk confirmation paths. CI run `31979462641`
passed migration upgrade, downgrade-to-base, and upgrade-to-head; 480 Python tests; contracts;
formatting, lint, and typecheck; 57 web tests; 10 browser tests; the production build; and all four
container builds.

The protected production Match Certification page exposed the new retry policy and queue-wide
needs-attention state. Existing banana and strawberry failures were attached to finalized cases, so
the UI correctly withheld retry controls. The live Matching guide documented terminal retries and
history preservation. Verification did not submit a retry and incurred no paid OpenAI call.
