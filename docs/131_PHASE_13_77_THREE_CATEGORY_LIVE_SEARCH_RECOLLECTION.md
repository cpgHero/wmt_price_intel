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

The combined estimate is 77,663 credits ($155.326). Combined hard ceilings are 85,000 credits
($170), leaving $30 uncommitted for diagnosed Search-only recovery without allowing the approved
$200 ceiling to be exceeded.

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

Production collection uses three worker replicas. Replica IDs are unique and the database-backed
limiter prevents horizontal scaling from multiplying a retailer quota.

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

- Collection queue tests: 29 passed; three database-only integration tests skipped locally.
- Rolling-refill regression proves a third task begins while the first slow request is still active.
- Ruff passed for all changed files.
- Production exposes three healthy worker replicas with unique IDs and shared Postgres permits.
- Final run totals, failure manifests, spend, artifact completeness, and downstream readiness remain
  pending until all three runs reach terminal state.
