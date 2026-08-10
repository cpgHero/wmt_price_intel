# Phase 9.5.4 — Product Identity and PDP Enrichment

## Status

Complete. Railway production is migrated through `0012_product_details`, and the deployed worker
passed the replica-safe Product Details queue/cache/budget/identity test together with the shared
Postgres rate-limiter test on 2026-08-08. Live Product Details collection remains disabled by
default pending owner acceptance.

## Runtime boundary

`rci-products` owns canonical retailer product identity, MetricsCart PDP request/response adapters,
immutable raw-object storage, the cached snapshot contract, and the durable enrichment queue. The
generic analytics engine has no retailer or category dependency on this package. It consumes only
linked identity documents when enrichment is available.

SERP evidence remains authoritative for observed price and availability. PDP evidence is
authoritative for product identity and may validate package semantics. The enrichment join copies
SERP observations before attaching identity and never mutates price, stock, rank, location, or
collection time.

## Durable queue and cost controls

- Enrichment eligibility starts from the explicit set of offer IDs admitted to the analysis. Raw
  search-result rows that classification or matching excludes are never candidates for PDP work.
- Within that admitted set, the planner requests one PDP snapshot for each retailer product ID
  from one deterministic representative location. Repeated sightings of the same product do not
  create location-by-location PDP calls.
- The only automatic fan-out is a verified package-price difference for the same retailer product
  ID. In that case, the planner requests one representative PDP snapshot for each distinct
  observed price state so location-specific variants can be investigated. It does not request
  every location that shares that price.
- SERP prices drive the exception. PDP responses remain identity evidence and cannot overwrite
  the authoritative observed search price.
- A run row is locked while reserving credits, making `planned_credits <= max_credits` atomic.
- A successful unexpired cache lookup occurs before a reservation and creates no provider job.
- Request identity hashes retailer, product ID, URL, ZIP, store, fulfillment, endpoint ID, and
  endpoint contract version.
- Jobs are claimed with `FOR UPDATE SKIP LOCKED`, lease heartbeats, bounded attempts, reclaim of
  expired leases, durable cancellation, and a per-run/request unique key.
- Actual credits increase only for HTTP 200 or 404 using the endpoint catalog's retailer cost.
- Raw gzip payloads are written before normalization or failure interpretation.

## Shared rate and cooldown controls

Every worker replica uses `provider_rate_limit_state` under a Postgres row lock. The provider key is
`metricscart:pdp:<retailer_id>` and the budget key is a one-way hash of the API credential. Defaults
are 3 requests/second and 180 requests/minute per PDP retailer/type. HTTP 429 writes a shared
cooldown visible to every replica. Search uses separate keys, so its contract remains independent.

## Fixture acceptance

The owner-supplied fixtures cover:

- Walmart product `677669806`, ZIP `90020`, store `2464`, pickup;
- ALDI product `0000000000008696`, ZIP `90001`, store `479-149`, pickup;
- Amazon product `B0DN1ZTN12`, ZIP `90001`.

Tests preserve IDs and ZIPs as strings, validate all three normalized snapshots against the shared
JSON Schema, prove 200/404 billing, retain raw evidence, and prove one cached snapshot enriches two
SERP observations without changing their differing prices or availability. Planner tests also prove
that excluded search noise creates no request, identical product/location sightings collapse to one
request, and price-variant products create one request per distinct observed price state.

## Acceptance commands

```bash
uv run pytest packages/python/rci-products/tests
uv run pytest packages/python/rci-products/tests/test_postgres.py
uv run pytest packages/python/rci-providers/tests/test_postgres_limiter.py
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages/python
uv run alembic -c database/alembic.ini upgrade head --sql
```

The Postgres tests require `RCI_TEST_DATABASE_URL`. No acceptance command performs a live
MetricsCart call, and no billable development credit was consumed by this subphase.

## Railway acceptance evidence

- Commit `01a52c2` deployed successfully to `api`, `worker`, and `scheduler`; the unaffected `web`
  service remained healthy on the prior compatible build.
- Alembic reports `0012_product_details (head)` in production.
- The two production-backed Postgres suites completed with `2 passed`.
- Public `/health` returned `ok`; `/health/ready` returned `ready` with the API dependency `ok`.
- The temporary Railway SSH credential was removed immediately after the acceptance run.
- Product Details remained disabled, so the run made no MetricsCart request and spent zero credits.
