# Phase 13.39 — Retailer-Isolated Collection Gates

## Objective

Allow a multi-retailer Search-by-ZIP collection to continue for every retailer whose bounded
preflight passes, while stopping only retailers whose preflight fails. Walmart, ZIP-only Amazon
Same Day, and every selected physical competitor receive the same independent safeguard.

This phase changes collection control-plane behavior only. It does not authorize or initiate a
paid MetricsCart, PDP, or AI call.

## Durable decision model

`collection_retailer_gate` stores one immutable-run-scoped decision per retailer: pending, passed,
or failed; sample size; maximum permitted 404 rate; resolution time; and a human-readable failure
reason. Existing preflight evidence is backfilled per retailer during migration rather than copying
the former run-wide result.

The run-level status is now a summary:

- `pending`: at least one retailer is unresolved;
- `passed`: every retailer passed;
- `partial`: at least one retailer passed and at least one failed;
- `failed`: every gated retailer failed; or
- `skipped`: no availability gate was configured.

## Claim, release, and early-stop rules

- A retailer may have at most one preflight request in flight at a time. Different retailers can
  preflight concurrently.
- A non-preflight task can be claimed only when that task's retailer gate passed.
- A failure is certain once a terminal non-404 error appears or the observed 404 count exceeds
  `floor(maximum_404_rate × sample_size)`. Pending work for only that retailer is cancelled at once.
- Passing requires every sample to finish without crossing either failure condition.
- A failed retailer never blocks a passed retailer. Mixed runs finish with warnings and preserve
  complete retailer-level evidence.
- Retrying a failed preflight resets only that retailer gate and only that retailer's gate-cancelled
  remainder. Other retailer decisions remain intact.

## Operator experience

The collection monitor replaces the obsolete ALDI-only message with retailer-specific cards that
show pass/fail/pending status, sample completion, 404 count, and failure reason. Failed request
inputs can be downloaded as CSV, including retailer, ZIP, store, scope key, page, HTTP status,
failure class, attempts, billable credits, and the exact request payload.

## Verification contract

- Mixed pass/fail tests prove healthy retailer tasks release while the unhealthy remainder stops.
- A five-sample, 50%-maximum test proves the gate stops immediately after the third 404 and avoids
  the remaining two preflight calls.
- Planner/UI tests prove primary Walmart and ZIP-only Amazon are included.
- Retry tests prove only the failed retailer is reopened.
- Migration upgrade SQL is generated through head and the migration is reversible.
- API, web types, and monitor presentation share the same retailer-gate contract.

## Paid-work boundary

No live collection is launched by this phase. After production verification, the next proposed Milk
and Egg collections require fresh exact task, credit, and dollar estimates. The owner approves that
paid scope separately.

## Release acceptance

Phase 13.39 was deployed and production-verified on August 22, 2026 at commit `34dc2cc`.
GitHub Actions run `32600392203` passed the real-Postgres migration and queue suite, Python
formatting/linting/types/contracts/tests, TypeScript formatting/linting/types/unit/build checks, all
14 browser tests, migration upgrade/downgrade/upgrade, and all four service-container builds.

The production monitor for the prior fourteen-retailer Egg preflight displayed twelve durable
retailer decisions with the expected eight passes and four failures, accurate per-retailer sample
counts, 404 evidence, and terminal-failure reasons. The historical run predates Walmart and Amazon
Same Day preflights, so neither retailer was backfilled with invented evidence. The failed-input CSV
download started successfully from the live monitor. This acceptance made no MetricsCart Search,
MetricsCart PDP, or OpenAI call.
