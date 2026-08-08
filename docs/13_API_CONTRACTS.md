# Application API Contract Outline

Prefix: `/api/v1`.

## Locations
- `GET /retailers`
- `GET /retailers/{id}/locations`
- `POST /admin/location-imports`
- `GET /admin/location-imports/{id}`

## Product Packs
- `GET /product-packs`
- `GET /product-packs/{id}/versions/{version}`
- `POST /admin/product-packs/validate`
- `POST /admin/product-packs/publish`

## Collection Definitions
- `POST /collection-definitions`
- `GET /collection-definitions`
- `GET /collection-definitions/{id}`
- `POST /collection-estimates` validates and estimates an unpublished definition without persisting it.
- `POST /collection-definitions/{id}/estimate`
- `POST /collection-definitions/{id}/runs`

## Collection Runs
- `GET /collection-runs/{id}`
- `POST /collection-runs/{id}/cancel`
- `POST /collection-runs/{id}/retry-failed`
- `GET /collection-runs/{id}/tasks`
- `GET /collection-runs/{id}/usage`
- `GET /collection-runs/{id}/monitor` returns exact retailer/status aggregates,
  retry/failure counts, elapsed time, configured global provider limits, and shared
  Postgres cooldown state without exposing the credential budget key.

## Analyses
- `GET /analyses`
- `GET /analyses/{id}`
- `POST /collection-runs/{id}/analysis`
- `GET /collection-runs/{id}/analysis` returns the latest canonical result for a source run.
- `GET /analyses/{id}/matches`
- `GET /analyses/{id}/quality`
- `GET /analyses/{id}/history?baseline_id=` returns numeric metric changes with current and baseline
  JSON evidence references.
- `POST /analyses/{id}/evaluate-alerts` idempotently evaluates active alert versions.

## Automation

- `GET /collection-schedules`
- `POST /collection-schedules/sync`
- `POST /alert-definitions` validates and publishes an immutable alert-definition version.
- `GET /alert-definitions`
- `GET /alert-events?limit=` returns triggered/suppressed evaluations with evidence.
- `GET /email-deliveries?limit=` returns retry/delivery metadata and evidence; SMTP bodies and
  credentials are not exposed.

## Artifacts
- `GET /analyses/{id}/artifacts`
- `POST /analyses/{id}/artifacts/{type}` where type in html, xlsx,
  leadership_email, audit_zip
- `GET /artifacts/{id}/download` returns short-lived signed URL

## Internal worker endpoints
Prefer direct DB queue claims for workers rather than public worker HTTP routes. If internal endpoints are used, protect them with private networking/service credentials.
