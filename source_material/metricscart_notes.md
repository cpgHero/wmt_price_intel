## Common Pattern

Base URL:

- `https://api.metricscart.com`

Authentication:

- Pass the MetricsCart key as a query parameter: `x-api-key=YOUR_METRICSCART_API_KEY`
- Do not expose production keys in client-side code.

Pagination:

- Search/SERP endpoints use `page`.
- Search Monitor clamps `max_pages` to `1..10`.

Rate limits:

- MetricsCart caps in code: `3 RPS`, `180 RPM`.
- Search Monitor worker defaults: `2 RPS`, `108 RPM`.

Billing:

- Search Monitor charges catalog credits only on successful `2xx` pages.
- Current Amazon Search Monitor catalog fixture shows `2` credits/page.
- Other retailer credit values should be confirmed from the MetricsCart/API catalog.

Store/location universe:

- Existing complete store sync uses MetricsCart geography:
  - `POST https://app.metricscart.com/api/v0.1/accounts/user-login/`
  - `GET https://app.metricscart.com/api/v0.1/products/geography/retailers/`
  - `GET https://app.metricscart.com/api/v0.1/products/geography/locations/?retailers={retailer_id}`
- Location rows include `retailer_store_id`, address, ZIP, city/state, lat/lng.

Example successful response shape:

{

  "query": {

    "keyword": "eggs",

    "retailer": "walmart",

    "retailer\_store\_id": "2464"

  },

  "results": [

    {

      "result\_position": 1,

      "name": "Large White Eggs, 12 Count",

      "brand": "Great Value",

      "price": "$2.48",

      "retailer\_product\_id": "123456",

      "url": "https\://www\.example.com/ip/123456",

      "stock\_availability": true,

      "pickup\_available": true

    }

  ]

}

## Retailer APIs

**Walmart SERP by store/ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/walmart/search/zipcode/v2`
- Purpose: Walmart product SERP by keyword or URL, ZIP, and store.
- Params: `keyword` or `url`, `zipcode`, `store`, `page`, `sort`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/walmart/search/zipcode/v2?keyword=choco%20chips&zipcode=90020&store=2464&page=1&sort=Best%20Match&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP plus Walmart store number.
- Quirk: Walmart has a legacy `/zipcode/v2` path; store selection matters for pricing and availability.

**Amazon Same Day SERP by ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/amazon/search/zipcode/`
- Purpose: Amazon Same Day SERP by ZIP, using a Same Day URL context.
- Search Monitor params: `url`, `zipcode`, `page`, `sort`, `x-api-key`
- Generic keyword params: `keyword`, `zipcode`, `page`, `x-api-key`
- Search Monitor example: `GET https://api.metricscart.com/mc/amazon/search/zipcode/?url=https%3A%2F%2Fwww.amazon.com%2Fs%3Fk%3Deggs%26i%3Damazonfresh&zipcode=10001&page=1&sort=Featured&x-api-key=YOUR_METRICSCART_API_KEY`
- Generic example: `GET https://api.metricscart.com/mc/amazon/search/zipcode/?keyword=eggs&zipcode=10001&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP only, no store number.
- Quirk: the `url` input is what preserves Amazon Same Day context; a plain keyword search can return regular Amazon results.

**Aldi SERP by store/ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/new_aldi/serp/zipcode`
- Purpose: Aldi product SERP by keyword, ZIP, and store.
- Params: `keyword`, `zipcode`, `store`, `page`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/new_aldi/serp/zipcode?keyword=beef&zipcode=10001&store=473-103&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP plus Aldi store id.
- Quirk: provider slug is `new_aldi`/“Aldi New”, not simply `aldi`.

**Target Search**

- Endpoint: `GET https://api.metricscart.com/mc/target/search`
- Purpose: Target generic search.
- Params: `keyword`, `page`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/target/search?keyword=mobiles&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: no ZIP/store in the snapshot found.
- Quirk: no ZIP-scoped Target SERP entry was found in the local expected-params snapshot.

**Kroger SERP by store/ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/kroger/search/zipcode`
- Purpose: Kroger product SERP by keyword, ZIP, and store.
- Params: `keyword`, `zipcode`, `store`, `page`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/kroger/search/zipcode?keyword=soap&zipcode=23322&store=02900578&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP plus Kroger store id.
- Quirk: store IDs may include leading zeros, so treat them as strings.

**H-E-B SERP by store/ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/heb/serp/zipcode`
- Purpose: H-E-B product SERP by keyword, ZIP, and store.
- Params: `keyword`, `zipcode`, `store`, `page`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/heb/serp/zipcode?keyword=Bread&zipcode=77084&store=497&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP plus H-E-B store id.
- Quirk: display name may be `H-E-B`, but API path slug is `heb`.

**Albertsons SERP by store/ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/albertsons/serp/zipcode`
- Purpose: Albertsons product SERP by keyword, ZIP, and store.
- Params: `keyword`, `zipcode`, `store`, `page`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/albertsons/serp/zipcode?keyword=mobile&zipcode=90027&store=387&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP plus Albertsons store id.
- Quirk: uses `serp/zipcode`, not `search/zipcode`.

**Safeway SERP by store/ZIP**

- Endpoint: `GET https://api.metricscart.com/mc/safeway/serp/zipcode`
- Purpose: Safeway product SERP by keyword, ZIP, and store.
- Params: `keyword`, `zipcode`, `store`, `page`, `x-api-key`
- Example: `GET https://api.metricscart.com/mc/safeway/serp/zipcode?keyword=snacks&zipcode=94610&store=1119&page=1&x-api-key=YOUR_METRICSCART_API_KEY`
- Location: ZIP plus Safeway store id.
- Quirk: uses `serp/zipcode`; availability may appear in retailer-specific raw fields plus normalized fields like `stock_availability` and `pickup_available`.




Ask

-

# Scale Search Monitor Workers

## Current Findings

- Search Monitor already stores queue rows and products by `job_id` in `api/src/db/schema.ts`, and ingest rejects rows whose `queue.jobId` does not match the posted `job_id` in `api/src/routes/searchMonitorWorker.ts`.
- The worker can see multiple running jobs via `/search_monitor/worker/running_jobs`, but `search-monitor-worker/src/index.js` currently processes jobs sequentially inside one replica.
- Current rate limiting in `search-monitor-worker/src/limiter.js` is process-local, so adding replicas would multiply MetricsCart RPS/RPM.
- The default `WORKER_ID` is `railway-worker-1`; multiple replicas using the same ID weakens queue lock ownership checks.

## Implementation Plan

1. Add replica-safe worker identity.

- Update `search-monitor-worker/src/config.js` so `workerId` defaults to a unique value using Railway/container metadata when available, falling back to hostname and pid.
- Keep explicit `WORKER_ID` support, but document that it must be unique per replica if manually set.

2. Add a shared MetricsCart permit endpoint in the API.

- Add a small Postgres-backed global rate limiter under `api/src/routes/searchMonitorWorker.ts`, exposed as something like `POST /search_monitor/worker/mc_permit`.
- Use a transaction plus `pg_advisory_xact_lock` or a dedicated limiter table to serialize permit allocation across API requests.
- Enforce global defaults below MetricsCart’s caps, for example total `2 RPS` and `108 RPM`, configurable via API env vars.
- Track separate budgets by MetricsCart API key or a normalized budget key so a per-job override key does not accidentally share the wrong quota.

3. Move worker scheduling from local-only to shared plus local smoothing.

- Update `search-monitor-worker/src/apiClient.js` with `acquireMcPermit` and optional `reportMcBackoff` methods.
- Update `search-monitor-worker/src/index.js` so every MetricsCart call waits for the shared permit before calling `search-monitor-worker/src/metricscart.js`.
- Keep a small local limiter as a burst smoother, but treat the API permit as the source of truth for cross-replica limits.

4. Add global 429 cooldown behavior.

- When a worker receives a MetricsCart `429`, report it to the API or include enough status in ingest for the API to set a shared `paused_until` value for the same budget key.
- Have `mc_permit` return `wait_ms` while the budget is paused, so all replicas cool down together.
- Use conservative exponential backoff with a max cap, matching the existing Review Radar worker pattern where helpful.

5. Parallelize across jobs without mixing datasets.

- Change the worker loop from fully sequential `for (const job of jobs)` processing to bounded job-level concurrency, for example `WORKER_JOB_CONCURRENCY=2` per replica.
- Continue claiming rows per `job_id`; do not merge queue rows across jobs.
- Keep product writes using the claimed job config and queue zipcode, so rows continue landing in `search_monitor_product.job_id`.
- Keep ingest’s existing checks that `queue.jobId === job_id` and `queue.lockedBy === worker_id`; add tests around these checks.

6. Improve claim safety for multiple replicas.

- Review the current select-then-update claim loop in `api/src/routes/searchMonitorWorker.ts`. It is mostly safe because updates require `status = 'pending'`, but a single SQL claim using `FOR UPDATE SKIP LOCKED` would reduce contention and wasted round trips under multiple replicas.
- If Drizzle makes that awkward, use a small `sql` query for claim selection/update while preserving the existing response shape.

7. Add focused tests and operational checks.

- Add API tests for two workers claiming the same job concurrently: no duplicate queue ids, correct `locked_by`, and ingest rejection from the wrong worker.
- Add API tests for two running jobs: claimed rows and products remain under the correct `job_id`.
- Add rate limiter tests for the shared permit logic: total permits across simulated replicas never exceed RPS/RPM, and a `429` pauses all replicas for that budget key.
- Add worker unit tests around unique worker ID fallback and job-level concurrency respecting the shared permit calls.

8. Deployment rollout.

- Deploy with one replica and shared limiter enabled first.
- Set conservative env defaults: low `WORKER_JOB_CONCURRENCY`, low per-replica `WORKER_CONCURRENCY`, and global API caps below MetricsCart limits.
- Scale Railway `search-monitor-worker` replicas gradually while watching job throughput, `429` counts, failed queue rows, and MetricsCart latency.

## Target Flow

429Worker replica AGET running jobsWorker replica BClaim rows by job\_idAPI shared MetricsCart permitMetricsCart APIIngest queue resultProducts stored by job\_idShared cooldown

## Acceptance Criteria

- Multiple worker replicas can run at the same time without duplicate processing of the same queue row.
- Multiple Search Monitor jobs progress at the same time, while queue rows and products remain isolated by `job_id`.
- Total MetricsCart traffic stays within a single global RPS/RPM budget across all replicas.
- A MetricsCart `429` causes coordinated cooldown across replicas instead of each replica continuing independently.
- Tests cover concurrent claims, wrong-worker ingest rejection, per-job separation, and shared rate limit behavior.



-
-
-
-

*

-
-

49 x 7

Local History will track recent changes as you save them unless the file has been excluded or is too large.