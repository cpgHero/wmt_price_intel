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

The three primary runs estimate 77,663 credits ($155.326). One Walmart-only Banana recovery was
authorized after four successful preflight responses and one nonbillable provider HTTP 500 caused
the immutable primary run's Walmart gate to fail. The recovery reuses the frozen geography and has
a 5,000-credit ($10) hard ceiling; it does not rewrite or retry the failed primary task. Combined
hard ceilings are now 90,000 credits ($180), leaving $20 uncommitted without allowing the approved
$200 Search ceiling to be exceeded.

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

Production collection uses three worker replicas. Replica IDs are unique and the database-backed
limiter prevents horizontal scaling from multiplying a retailer quota.

Each replica also caps active work per retailer while retaining a larger total rolling window and
HTTP connection pool. Slow ALDI requests therefore cannot occupy every slot needed by Walmart,
Amazon, or another Egg retailer. The cap governs concurrency, not request starts; the shared
Postgres limiter remains the authoritative three-per-second and 180-per-minute boundary.

When a retailer returns HTTP 429, the shared state pauses only that retailer and records the event.
For 30 minutes after the last 429, that retailer is paced at one start per second and 54 starts per
minute; retailers without a recent 429 remain at three and 180. Repeated 429s extend the adaptive
window. This follows the fastest rate the live endpoint actually accepts instead of repeatedly
re-entering cooldown at an optimistic catalog ceiling.

## Execution and reconciliation gates

1. Each retailer must pass its own five-call availability gate before its bulk tasks are released.
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

- Collection queue tests: 15 passed; four database-only integration tests skipped locally.
- Rolling-refill regression proves a third task begins while the first slow request is still active.
- Ruff passed for all changed files.
- Production exposes three healthy worker replicas with unique IDs and shared Postgres permits.
- Final run totals, failure manifests, spend, artifact completeness, and downstream readiness remain
  pending until all three runs reach terminal state.
