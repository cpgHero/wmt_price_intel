# Phase 10.1 — Dynamic Collection Builder and Approved Geography Snapshots

## Outcome

Phase 10.1 replaces the fixed collection form with a guided, auditable builder. A user can
choose a Product Pack, name the primary retailer and competitors, construct a location
footprint, inspect the exact resolved stores or ZIP scopes, set collection controls, and
approve a maximum Search credit estimate before a paid task is queued.

The design keeps collection scope independent from category logic. Product Packs continue to
define category admission, attributes, comparison profiles, and reporting semantics; the
builder only selects a pack and supplies generic collection inputs.

## User workflow

1. **Purpose and retailers** — name the collection, select a Product Pack and keyword, choose a
   primary retailer, and choose one or more enabled competitors.
2. **Primary geography** — choose all primary locations, all locations in selected states, a
   deterministic dispersed sample of X locations per state, selected state/city pairs, custom
   ZIPs, or canonical location IDs.
3. **Competitor correspondence** — resolve store-level competitors in the same ZIP, across the
   primary states, or within an exact 1-, 3-, or 5-mile radius. ZIP-only retailers receive the
   deduplicated primary ZIP universe without fabricated stores.
4. **Geography review** — inspect counts, a national map with Alaska/Hawaii/Puerto Rico insets,
   searchable location evidence, proximity edges, exclusions, and a complete CSV download.
5. **Controls** — set page depth by retailer, a hard Search credit cap, the ALDI preflight gate,
   schedule, timezone, delivery outputs, and the intended PDP refresh cadence.
6. **Estimate and approve** — review a stored, expiring estimate bound to both configuration and
   geography checksums. A separate checkbox is required before launch.

Editing an existing definition uses the same builder. Launching an edit publishes a new
immutable definition version; existing runs remain linked to their original definition and
geography.

## Contracts

The normative JSON Schemas are:

- `schemas/collection-geography-request.schema.json`
- `schemas/collection-geography-resolution.schema.json`
- `schemas/collection-scope-estimate.schema.json`
- the extended `schemas/collection-definition.schema.json`

TypeScript types are generated from those schemas. The Python validator registers every
repository schema by file URI and `$id`, so cross-schema references are validated in both
languages. The TypeScript handoff validator also pre-registers the complete schema registry and
exercises the three Phase 10.1 contracts.

Approved collection definitions use:

```json
{
  "geography": {
    "strategy": "approved_resolution",
    "resolution_id": "uuid",
    "resolution_checksum": "sha256",
    "refresh_policy": "frozen"
  }
}
```

The schema requires a non-null UUID and checksum whenever `strategy` is
`approved_resolution`.

## Deterministic geography resolution

The resolver is generic across enabled retailers and uses retailer capabilities from
`config/retailer-catalog.json`.

- Country and ZIP values pass through the canonical normalization utilities; leading-zero US
  ZIPs remain strings.
- X-per-state selection starts with the location nearest the state centroid and then uses
  deterministic farthest-point sampling. Store number and canonical location ID break ties.
- Radius selection uses an in-memory degree grid for candidate reduction and exact Haversine
  distance for the final 1-, 3-, or 5-mile decision.
- A competitor store is stored once even when it corresponds to several primary stores; every
  qualifying primary-to-competitor edge is retained with its calculated distance.
- ZIP-only retailers receive explicit ZIP snapshot rows and never receive fake store IDs,
  coordinates, or markers.
- User exclusions are part of the request and checksum. They can be restored in the review UI
  before a refreshed snapshot is approved.
- The snapshot checksum is deterministic and excludes generated database identifiers. Resolving
  the same request against the same location source returns the existing organization-scoped
  snapshot.

Population, county, and demographic selection are deliberately deferred. Those controls remain
unavailable until a governed demographic source, metric definitions, freshness policy, and
validation contract exist.

## Persistence and migration

Migration `0021_collection_geography_resolution` adds:

- `collection_geography_resolution` for the canonical request, checksum, status, counts, and
  creation time;
- `collection_geography_location` for immutable location facts copied from the location master;
- `collection_geography_edge` for audited proximity relationships;
- `collection_scope_estimate` for the configuration/geography approval envelope and expiration;
- `collection_definition_version.geography_resolution_id` to bind a definition version to its
  frozen geography; and
- `collection_run.scope_estimate_id`, with a uniqueness constraint, to make an approved launch
  idempotent.

Snapshot location rows intentionally do not foreign-key their source `retailer_location_id`.
The source identifier is retained as evidence, while later location-master corrections or
retirement cannot mutate or delete historical collection scope.

## Approval and launch integrity

Creating a geography preview or estimate performs no MetricsCart call. A stored estimate expires
after 30 minutes and contains:

- the exact definition ID;
- configuration and geography SHA-256 checksums;
- location units, page depth, per-page credits, maximum pages, and maximum credits by retailer;
- total maximum pages and Search credits; and
- creation and expiration timestamps.

Launch revalidates the schema and schedule, verifies the estimate is current, verifies both
checksums and the resolution ID, and replans before publishing the definition version. If the
plan has changed, the launch is rejected without publishing a new version. Repeating an
identical approved launch returns the existing run because one scope estimate can create at most
one run.

The worker retains the durable Postgres queue, availability gate, retry policy, cancellation,
shared MetricsCart limiter, and hard credit-cap enforcement implemented in earlier phases.

## PDP enrichment boundary

The builder records one of these generic policies:

- disabled;
- new or changed products;
- refresh after 7 days;
- refresh after 30 days; or
- manual only.

Every policy is constrained to products admitted to the analysis. Search price and availability
remain store-authoritative. The normal PDP plan uses one representative, observed store/ZIP per
distinct retailer product; additional store samples are eligible only when the same product ID
has store-level price variation.

PDP credits are not included in the Search estimate and are not released by the Phase 10.1
launch approval. The collection definition records `separate_after_search`, preserving a hard
approval boundary for the later eligible-product PDP plan.

## API surface

- `GET /api/v1/collection-builder/options`
- `GET /api/v1/collection-builder/location-facets`
- `POST /api/v1/collection-geography-resolutions`
- `GET /api/v1/collection-geography-resolutions/{id}`
- `GET /api/v1/collection-geography-resolutions/{id}/locations`
- `GET /api/v1/collection-geography-resolutions/{id}/download`
- `POST /api/v1/collection-scope-estimates`
- `POST /api/v1/collection-launches`

The Next.js application exposes same-origin BFF routes for these operations. Provider secrets and
private Railway service URLs never enter client code.

## Application routes

- `/collections` — definitions and run monitor entry point;
- `/collections/new` — the six-step collection builder; and
- `/collections/definitions/{stableKey}/edit` — new-version workflow for an existing definition.

## Acceptance criteria

- No paid provider call occurs during option loading, geography resolution, review, CSV download,
  or estimation.
- Enabled retailer choices and costs come from the server retailer catalog, not client constants.
- Leading-zero ZIPs survive contract validation, snapshot persistence, planning, and task creation.
- Primary and competitor selection stays category-neutral.
- Same input and location source produce the same snapshot checksum and dispersed sample.
- Radius stores are deduplicated while all valid proximity edges remain auditable.
- ZIP-only retailer tasks use only that retailer's stored ZIP scopes.
- Planning a frozen snapshot does not query the live location master.
- Configuration or geography changes invalidate the estimate.
- A changed/expired estimate cannot publish or launch.
- Repeating the same approved launch cannot create duplicate paid work.
- PDP enrichment remains analysis-admitted, cadence-aware, and separately approved.
- Existing legacy definitions and scheduler-driven launches remain supported.

## Verification commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check apps packages/python database
.venv/bin/mypy apps packages/python
.venv/bin/python scripts/validate_handoff.py
node packages/typescript/contracts/scripts/validate-handoff.mjs
node node_modules/typescript/bin/tsc --noEmit -p packages/typescript/contracts/tsconfig.json
node node_modules/typescript/bin/tsc --noEmit -p apps/web/tsconfig.json
node node_modules/eslint/bin/eslint.js apps/web/src apps/web/e2e
node node_modules/vitest/vitest.mjs run
node node_modules/next/dist/bin/next build apps/web
```

The Postgres-backed migration, snapshot, estimate, and idempotent-launch integration continues to
run in CI where `RCI_TEST_DATABASE_URL` is available.

## Production acceptance — 2026-08-11

Commit `62b92d9d3a4b4b75ab83717744e19ed3eb760d4b` passed GitHub Actions run
`31488556979`, including the Postgres migration cycle and all four container builds. Railway
reported successful deployments for web, API, worker, and scheduler.

The production walkthrough at `/collections/new` completed these no-charge actions:

- loaded the five certified Product Packs and the three enabled retailer capabilities from the
  API;
- resolved ZIP `44906` to one Walmart store, one ALDI store, and one Amazon Same Day ZIP scope;
- displayed the map and all three immutable location evidence rows;
- stored geography resolution `757900ce-e932-4447-a679-b3caf67250bf`;
- produced a five-credit maximum Search estimate: Walmart 1, ALDI 2, and Amazon Same Day 2; and
- verified that the paid launch remained disabled without explicit approval.

The production readiness endpoint returned `ready` with API dependency `ok`. No MetricsCart
Search, MetricsCart PDP, or OpenAI call was made during implementation or production acceptance.
