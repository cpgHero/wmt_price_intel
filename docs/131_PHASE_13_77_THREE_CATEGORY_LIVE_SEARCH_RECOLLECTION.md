# Phase 13.77 — Three-category live Search recollection

## Owner decision

The platform owner approved a combined **$200 Search-only ceiling** for full national Banana,
Milk, and Egg recollection. The approval does not authorize Product Details or OpenAI spend.
Search remains authoritative for retailer-location price, positive-price observation, and
sponsorship. Product Details remains a separate cache-first workflow with a 30-day refresh policy.

## Immutable scope and budgets

All three runs use API Search contracts, one page per governed location, current frozen location
resolutions, retailer-isolated availability gates, durable tasks, immutable raw objects, and hard
credit ceilings.

| Category | Run ID | Estimated credits | Hard ceiling |
|---|---|---:|---:|
| Fresh Bananas | `f2e876dc-afb2-458c-9cbe-2cf02472b923` | 18,437 | 20,000 |
| Fresh Fluid Milk | `d0409065-cc9c-4326-a01d-42c335eef42d` | 18,437 | 20,000 |
| Fresh Shell Eggs | `10f96d03-0064-411a-a2d9-41eec6eec8f9` | 40,789 | 45,000 |
| Fresh Bananas — Walmart recovery | `b4dae462-a06a-4ea1-95ca-fc1260dff922` | 4,683 | 5,000 |
| Fresh Bananas — resilient Walmart recovery | `b11c9efa-c118-49b0-b6b6-a5045ba06940` | 4,683 | 4,683 |

The three primary runs estimate 77,663 credits ($155.326). One Walmart-only Banana recovery was
authorized after four successful preflight responses and one nonbillable provider HTTP 500 caused
the immutable primary run's Walmart gate to fail. The recovery reuses the frozen geography and has
a 5,000-credit ($10) hard ceiling; it does not rewrite or retry the failed primary task. The resilient
successor adds an exact 4,683-credit ceiling. At its launch, the conservative estimate across the
batch was 87,029 credits ($174.058), while actual credits plus open work plus the successor projected
62,638 credits ($125.276). The sum of per-run hard ceilings is 94,683 credits ($189.366), still below
the approved $200 Search ceiling.

## Throughput correction

MetricsCart Search quotas are independent by retailer and request type. Production therefore uses
the owner-confirmed ceiling of three Search starts per second and 180 per minute for each retailer.
The Postgres limiter scopes permits to the credential, Search request type, and retailer; all worker
replicas share that state and shared 429 cooldowns.

The collection worker now keeps a bounded rolling window of leased tasks. When one request
finishes, its slot is refilled immediately while slower requests remain leased and heartbeating.
Previously the worker waited for the slowest member of every claimed batch, so a single 60-second
timeout could idle otherwise-free retailer capacity. Rolling refill does not change task identity,
budgets, retailer gates, retry ceilings, cancellation, immutable raw evidence, or `FOR UPDATE SKIP
LOCKED` ownership. Graceful shutdown completes already-leased requests without claiming more.

Eligible claims are ranked by collection-run/retailer lane before row locking. Each claim window
takes one eligible task from every lane before taking a second from any lane. This prevents an
older category or a high-volume retailer from monopolizing rolling slots while preserving global
preflight priority and `SKIP LOCKED` safety across replicas.

The final claim update also rechecks pending/expired-lease eligibility after row locking. This
prevents a concurrently selected candidate from being reassigned after another replica has already
renewed its lease. The candidate set is explicitly materialized before the update. This is the
billable-call safety boundary for horizontal collection workers.

Production collection uses five worker replicas. Replica IDs are unique and the database-backed
limiter prevents horizontal scaling from multiplying a retailer quota.

Each replica also caps active work per retailer while retaining a larger total rolling window and
HTTP connection pool. Slow ALDI requests therefore cannot occupy every slot needed by Walmart,
Amazon, or another Egg retailer. The cap governs concurrency, not request starts; the shared
Postgres limiter remains the authoritative three-per-second and 180-per-minute boundary.

When a retailer returns HTTP 429, the shared state pauses only that retailer and records the event.
For 30 minutes after the last 429, that retailer is paced at one start per second and 54 starts per
minute initially, then ramps continuously back toward three starts per second and 180 per minute;
retailers without a recent 429 remain at the full ceiling. Repeated 429s reset only that retailer's
adaptive recovery window. This follows the fastest rate the live endpoint actually accepts instead of repeatedly
re-entering cooldown at an optimistic catalog ceiling.

## Availability-gate resilience and recovery rotation

The historical gate remains immutable and the default behavior remains strict. A new definition may
explicitly require a successful-sample quorum and allow a bounded number of retry-exhausted,
zero-credit transient samples. Only `provider_5xx`, `timeout`, `network`, and `rate_limit` are
tolerable. Authentication, invalid-request, schema, parse, storage, billable, and unknown failures
remain hard blockers; the billable-404 ceiling remains independent. All selected samples must
terminate before the retailer can pass.

An immutable recovery may exclude exact location-scope keys from preflight designation. The planner
rotates in the next deterministic fingerprints and fails planning if too few samples remain. The
excluded location is still collected in the full frozen geography; this control cannot hide a store,
rewrite a failed task, or suppress its final evidence.

The Banana Walmart replacement policy is five samples, a quorum of four successful samples, and at
most one tolerated transient nonbillable failure. It rotates ZIP `60430` / store `5404` out of the
preflight sample because that exact scope exhausted five zero-credit provider-500 attempts. The four
previous HTTP-200 controls remain samples and ZIP `32224` / store `1172` is the deterministic
replacement. Migration `0049_collection_gate_resilience`, the compatible API, and all five workers
were deployed before run `b11c9efa-c118-49b0-b6b6-a5045ba06940` launched. Its intended five-sample
gate included replacement ZIP `32224` / store `1172`, passed, and released all bulk tasks. The known
bad ZIP `60430` / store `5404` remained a non-preflight task in the full collection.

The terminal bulk-run rule uses the same narrow boundary. If useful work succeeded, a
retry-exhausted non-preflight failure may produce `completed_with_warnings` only when it is
zero-credit and in the explicit transient whitelist. Hard and billable non-404 failures remain
fatal; billable 404s retain their separate threshold and warning behavior. This preserves nearly
complete useful evidence without relabeling an authentication, contract, storage, or paid failure
as harmless.

## Execution and reconciliation gates

1. Each retailer must pass its own five-call availability gate before its bulk tasks are released.
   Legacy definitions require every sample to avoid a terminal non-404 failure. An explicitly
   configured resilient definition must satisfy its successful-sample quorum, transient-failure
   ceiling, independent 404 ceiling, and zero-hard-failure rule.
2. A failed retailer is isolated; healthy retailers continue concurrently.
3. HTTP 200 and 404 responses are billable. Billable 404s are not retried blindly.
4. Actual credits are reconciled from durable task evidence against each run ceiling and the
   combined owner ceiling.
5. Terminal failures are classified by retailer, request input, HTTP status, and billability before
   any recovery call is considered.
6. Search completion does not publish a report. Normalization, admission/noise controls, selective
   cache-first PDP planning, matching/certification, semantic publication gates, and successor
   acceptance remain separate governed stages.
7. Predecessor reports are archived only after a successful replacement is validated. Source data,
   raw objects, PDP evidence, certification history, and audit lineage are never deleted.

## Verification

- Targeted collection, contract, API, and gate tests: 85 passed; five database-only tests skipped
  locally because `RCI_TEST_DATABASE_URL` was unavailable.
- Rolling-refill regression proves a third task begins while the first slow request is still active.
- Ruff, mypy across 152 files, web TypeScript type checking, 91 normative JSON-document validation,
  and offline Alembic upgrade SQL through `0049_gate_resilience` passed.
- Commit `c6af7b6139738dc65e2ea2328a3d039c863f0406` passed GitHub Actions run `33326968373`,
  including 17 Playwright tests, real-Postgres upgrade/downgrade/upgrade, and all four containers.
- Railway deployed API `9e60276c-8b65-4785-b418-5038c23b468d`, worker
  `4284e6a8-6f88-4139-8faa-cdb005f5b79b`, web `5a27fa39-3cf9-483d-95af-4a12534145f3`,
  and scheduler `ffecd07a-25cf-49c3-95f8-bc53a038c9da`. Migration `0049_gate_resilience` is current,
  health/readiness passed, and logs prove five of five unique worker replicas run the new deployment.
- Resilient recovery run `b11c9efa-c118-49b0-b6b6-a5045ba06940` launched with exactly 4,683
  approved credits. Its five-sample gate passed and released the Walmart bulk collection.
- Final run totals, failure manifests, spend, artifact completeness, and downstream readiness remain
  pending until all three runs reach terminal state.
