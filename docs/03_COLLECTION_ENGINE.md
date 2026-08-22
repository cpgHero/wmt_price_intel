# Collection Engine Specification

## MetricsCart facts supplied by product owner

- Base URL: `https://api.metricscart.com`.
- API key is query parameter `x-api-key`; never expose client-side.
- Search endpoints use `page`.
- Existing Search Monitor caps `max_pages` to 1..10.
- Provider cap observed/documented: 3 RPS / 180 RPM.
- Conservative application defaults: 2 RPS / 108 RPM globally per credential.
- Catalog credits are charged on every 2xx or 404 response page. A 404 remains a failed/unavailable
  retailer page for task status and result counts, but its configured retailer credits are recorded.
- MetricsCart Search by ZIP API responses are the only source for all new collections. Historical
  CSV imports remain reproducible retained evidence, but they are not an API-response contract and
  do not define future field mappings.

## Cost estimate

For each retailer:
`eligible_location_units * max_pages * credits_per_successful_page`

The estimate is a maximum if pagination may stop early. Actual credits are recorded for billable 2xx
and 404 response pages; successful-page counts remain limited to 2xx responses.

The browser wizard estimates an unpublished definition directly, invalidates the estimate whenever
scope changes, enforces the configured hard cap, and requires an explicit approval before publishing
the definition and creating its run.

## Availability gate

An optional definition-level gate marks a deterministic sample of first-page tasks per configured
retailer. While the gate is pending, `FOR UPDATE SKIP LOCKED` claims only those sample tasks. The
remaining tasks are released only when the billable-404 rate is at or below the configured threshold
and no other terminal provider failure occurred. A failed gate cancels every still-pending non-sample
task without issuing provider requests; already incurred 2xx/404 credits remain in actual usage.

## Location expansion

- Store+ZIP retailers: one first-page task per eligible location row.
- ZIP-only retailers: deduplicate normalized ZIPs from the selected geography universe.
- Amazon Same Day defaults to benchmark Walmart ZIP universe unless the definition explicitly chooses another ZIP universe.

## Pagination

1. Queue page 1 for each location unit.
2. On success, persist the raw page before downstream normalization.
3. If `stop_on_empty` and result array is empty, stop.
4. Otherwise queue next page until retailer/definition `max_pages`.
5. Do not infer a short-page stop unless the adapter knows the provider page-size contract.

Every successful response page is audited before pagination continues. A recognized empty result
array is a valid terminal page. An unknown result-array path, a non-object array member, a missing
required canonical field, or an incompatible field type is `schema_drift`, not an empty result.
The raw billable response remains immutable evidence and the task fails closed so a payload change
cannot silently truncate a collection.

The response contract is catalog-driven and pins the owner-supplied MetricsCart endpoint-catalog
hashes. Aliases may absorb explicitly mapped provider renames, but a new shape must be audited and
versioned before collection resumes. The canonical artifact records the contract version, selected
result path, row count, observed field inventory, and source-authority rules.

The 2026-08-22 production Strawberry acceptance collected one live page from Walmart, ALDI, and
Amazon Same Day: 75 total rows for five credits, with no retry, 404, or schema drift. Every raw,
normalized, and classified artifact reconciled by checksum and row count. The provider's `query`
echo is diagnostic; the immutable collection task remains authoritative for requested retailer,
store, ZIP, page, and sort context. See `docs/87_PHASE_13_33_LIVE_SEARCH_API_ACCEPTANCE.md`.

## Failure taxonomy

- `rate_limit`: retry; shared cooldown.
- `network` / `timeout`: retry with jittered exponential backoff.
- `provider_5xx`: retry with cap.
- `authentication`: fail run and surface configuration error.
- `invalid_request`: fail task; usually nonretryable.
- `parse_error`: retain raw page/excerpt; retry once if safe, otherwise QA issue.
- `schema_drift`: retain raw page and billable accounting; fail closed without retry until an
  administrator audits and versions the mapping.

## Run cancellation

Cancellation prevents new task claims but does not delete raw pages already collected. Claimed tasks finish or release safely.

## Idempotency

Raw object key includes run/task/attempt/page identity. Successful task completion records canonical artifact checksum. Replaying a completed task must not double-count credits or overwrite evidence silently.

After a run succeeds (including a partial result with billable-404 warnings), a separate durable
`analysis_run` queue loads the configured Product Pack, normalizes provider pages, writes immutable
partitioned Parquet datasets, computes comparisons, publishes one canonical `AnalysisResult`, and
generates requested delivery artifacts. It uses the same lease/retry/`SKIP LOCKED` pattern as the
collection queue and has no product-category branches.

## Historical replay

Historical source files bypass provider collection but do not bypass provenance or orchestration.
A historical import is supported only to reproduce or audit retained studies; it is not an allowed
mechanism for a new production collection.
A portable manifest pins every original CSV by source filename, retailer, source format, exact row
count, and SHA-256. Validation completes before any object or database record is written.

The importer stores the original bytes at a content-addressed immutable object key, creates a
zero-credit `historical_import` workflow run, registers one `analysis_input_set`, and enqueues the
same leased `analysis_run` used for live collections. Retrying the same realized manifest returns
the existing input set and job. Local filesystem paths are never persisted.

Historical format handling is source-oriented, never product-category-oriented. Both MetricsCart
Search Monitor exports and consolidated SERP exports feed the canonical offer normalizer while
retailer, store, ZIP, product, and ASIN identifiers remain strings.
