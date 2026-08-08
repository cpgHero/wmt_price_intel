# Collection Engine Specification

## MetricsCart facts supplied by product owner

- Base URL: `https://api.metricscart.com`.
- API key is query parameter `x-api-key`; never expose client-side.
- Search endpoints use `page`.
- Existing Search Monitor caps `max_pages` to 1..10.
- Provider cap observed/documented: 3 RPS / 180 RPM.
- Conservative application defaults: 2 RPS / 108 RPM globally per credential.
- Catalog credits are charged on successful 2xx pages.

## Cost estimate

For each retailer:
`eligible_location_units * max_pages * credits_per_successful_page`

The estimate is a maximum if pagination may stop early. Actual credits are recorded only for successful billable pages.

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

## Failure taxonomy

- `rate_limit`: retry; shared cooldown.
- `network` / `timeout`: retry with jittered exponential backoff.
- `provider_5xx`: retry with cap.
- `authentication`: fail run and surface configuration error.
- `invalid_request`: fail task; usually nonretryable.
- `parse_error`: retain raw page/excerpt; retry once if safe, otherwise QA issue.

## Run cancellation

Cancellation prevents new task claims but does not delete raw pages already collected. Claimed tasks finish or release safely.

## Idempotency

Raw object key includes run/task/attempt/page identity. Successful task completion records canonical artifact checksum. Replaying a completed task must not double-count credits or overwrite evidence silently.
