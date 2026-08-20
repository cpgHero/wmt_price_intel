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
- `GET /analyses/{id}/price-architecture-matrix` returns schema `1.1.0` at product × retailer
  footprint-median grain. Request dimensions are `mode`, `fixed_increment`, `brand_type`, exact
  `brand`, `state`, `city`, and `zipcode`. Known third-party sellers are excluded, seller-unknown
  products remain labeled, and every returned product includes its retailer product ID and distinct
  observed-location count. Parameter-scoped results are persisted by migration `0042`; default
  modes are pre-materialized by both API and worker publication paths.

### Matching Architecture v2 shadow contracts

Phase 13.1 introduces repository contracts before exposing any new public mutation route:

- `product-identity-evidence.schema.json` — retailer listing, optional verified trade item,
  identifiers, and provenance-preserving attribute facts.
- `product-match-edge-v2.schema.json` — tiered pairwise claim, brand relationship, eligible price
  bases, evidence coverage, attribute evidence, applicability, and decision origin.
- `local-comparison-observation-v2.schema.json` — Search-authoritative benchmark/competitor offer
  facts, semantic/availability/price coverage, explicit missing reason, selection policy, and
  result.

These contracts are consumed internally during shadow certification. Existing match-review routes
remain authoritative until category cutover. Phase 13.4 adds protected, queue-scoped human
certification routes; approvals, rejections, and flags create immutable evidence and never alter
report matches.

`GET /api/v1/analyses/{analysis_id}/matching-v2-shadow` exposes bounded, read-only shadow evidence
only when `MATCHING_V2_SHADOW_API_ENABLED=true`. It accepts competitor, tier, status, benchmark
product, competitor product, offset, and limit filters. Responses always declare
`authoritative=false` and `report_metrics_affected=false`; no v2 report-match mutation endpoint
exists.

Protected Matching v2 certification routes are documented in
`docs/54_PHASE_13_4_HUMAN_MATCH_CERTIFICATION.md`. They require the production feature flag and
administrator token; every queue response remains `authoritative=false`.

`GET /api/v1/matching-v2/review-queues/{queue_id}/ai-drafts/eligible-cases` returns only the
exposure-ranked case IDs and counts needed to prepare a queue-wide paid AI-review confirmation. It
may be scoped by `competitor_retailer_id`, excludes existing tasks and final decisions, reapplies
first-party seller policy, and fails closed when Search-derived observed-location evidence is
missing. `POST .../ai-drafts` accepts the confirmed unique IDs (1–1,500) and creates one durable,
idempotent, non-authoritative batch; it never certifies a relationship.

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

## Protected Platform Docs

The Next.js same-origin route `GET /api/admin/docs` returns the serializable owner/admin operating
manual only when the existing administrator session is valid. It returns `401` otherwise and uses
`Cache-Control: private, no-store`. The content contains no credentials or private evidence URIs.
The canonical user-facing document model is `apps/web/src/lib/platform-docs.ts`; the route keeps
the content behind the same access boundary as Product Packs, Study Discovery, and Match
Certification.
