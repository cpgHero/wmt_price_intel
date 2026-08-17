# Phase 13.11 — Governed Large and Queue-Wide AI Review

Status: implemented; deployment validation pending

## Outcome

Match Certification can prepare more than 25 candidates at once and can select every currently
eligible candidate in the active review queue and competitor-retailer filter. The operation remains
bounded, paid, advisory, auditable, and explicitly confirmed by an identified administrator.

## Scope and cost governance

- One durable AI-review batch accepts 1–1,500 unique case IDs. The ceiling covers the largest
  current release queue (1,217 Fresh Shell Eggs cases) without becoming unbounded.
- `GET .../ai-drafts/eligible-cases` performs a lightweight server-side discovery and ranks cases by
  benchmark observed-location count, competitor observed-location count, criticality, stratum, and
  stable case ID.
- The queue-wide scope follows the active competitor-retailer filter. It does not depend on the 50
  rows visible on the current UI page.
- Before task creation, the confirmation names the exact case count, model, per-case policy ceiling,
  and worst-case aggregate exposure. Canceling creates no task and incurs no model cost.
- Batch idempotency continues to bind the queue, sorted case IDs, model, and prompt checksum.

## Eligibility and trust gates

The server excludes or rejects:

- an existing AI task for the case;
- a final `comparable` or `not_comparable` human decision;
- a known third-party marketplace listing; and
- a candidate whose benchmark or competitor product lacks a positive Search-derived observed
  store/location count after the versioned reconciliation sidecar is applied.

The last rule prevents incorrect zero-footprint candidates from entering paid AI review or being
mis-prioritized. It does not make the model authoritative: every result still requires human
certification.

## Durable processing

Migration `0038_large_ai_batches` raises only the batch membership constraint from 25 to 1,500.
Tasks retain PostgreSQL `FOR UPDATE SKIP LOCKED` claims, leases, automatic retries, terminal
needs-attention state, per-task usage/cost evidence, and worker concurrency limits. A large batch
therefore increases queued work without increasing simultaneous model calls.

## Milk observed-location validation

The release reconciliation catalog contains positive Search-derived counts for all Milk listing
identities. A read-only production API audit on August 16, 2026 returned all 311 Milk candidates
with no zero counts: Walmart products ranged from 1 to 4,525 observed locations and competitor
products ranged from 1 to 2,595. The phase adds a fail-closed eligibility gate and UI coverage so a
zero-footprint regression cannot silently enter queue-wide AI review.

## Verification gates

- API model coverage at 1,217 cases and rejection above 1,500;
- lightweight queue-wide/retailer-scoped discovery coverage;
- seller, final-decision, existing-task, observed-footprint, exposure ordering, and idempotency
  guard coverage;
- browser coverage for queue-wide discovery, exact cost disclosure, explicit confirmation, and a
  payload larger than 25;
- reversible migration, full Python/web tests, typecheck, lint, build, containers, and read-only
  production verification;
- no paid AI request during deployment validation.
