# Phase 10.2 — Governed Admin Product Pack Builder

## Outcome

Phase 10.2 turns Product Packs from deploy-time files into governed, exact-version runtime
bundles without making business logic editable as arbitrary code. An authenticated administrator
can start from a certified pack or a safe generic template, work through typed category decisions,
attach immutable evidence manifests, run deterministic certification, and explicitly publish or
activate a version.

The builder does not call MetricsCart, enrich PDPs, search the web, or invoke OpenAI. Those are
separately budgeted workflows. The builder configures the deterministic admission, attribute,
normalization, matching, reporting, and regression questions that later workflows execute.

## Non-negotiable architecture rules

- Product-category behavior remains Product Pack configuration over registered generic
  capabilities. New category branches in the analytics, matching, worker, API, or renderer core
  are forbidden.
- Search observations remain authoritative for store-specific price and availability. PDP
  evidence may support identity and package semantics but cannot replace store price.
- Deterministic code owns scope, extraction, normalization, match eligibility, metrics, and
  certification. AI cannot author authoritative numbers or silently publish configuration.
- A collection and AnalysisResult resolve the exact requested Product Pack and report-blueprint
  version. The active version is only the default for a new collection.
- Published Product Pack and report-blueprint versions are immutable. Changes require a new
  semantic version.
- Drafts are mutable only through append-only revisions and optimistic revision checks.
- Certification is bound to the exact draft revision, configuration checksum, blueprint checksum,
  evidence checksums, suite, and engine version.

## Administrator workflow

1. **Create** — clone an active certified version or start from the generic package-weight
   template. Creating a draft performs no paid call.
2. **Overview** — set the human name, category family, and description while retaining stable ID
   and version identity.
3. **Scope** — configure target terms, supporting terms, exclusions, hard exclusions,
   availability policy, and positive-price admission.
4. **Attributes** — define typed attributes, roles, strict-match requirements, units, unknown
   handling, and registered extraction rules.
5. **Normalization** — choose display metrics, safe conversions, forbidden metrics, and package
   equivalence from the capability registry.
6. **Comparison lenses** — define exact comparison questions, dimensions, geography, brand and
   unknown policy, price selection, and comparison metric.
7. **Retailer catalog** — inspect deterministic per-product overrides without changing the
   generic unseen-product fallback.
8. **Reporting** — set leadership questions, headline segments, caveats, and evidence minimums;
   preview the paired report blueprint.
9. **Certification** — attach evidence manifests, run quick/compact/full/publication suites,
   inspect every gate, and publish only after the exact revision passes the publication suite.
10. **Activation** — optionally make the version selectable by default for new collections.
    Existing collection definitions stay pinned.

## Contracts and shared types

The normative JSON Schemas are:

- `schemas/product-pack-draft.schema.json`
- `schemas/product-pack-capabilities.schema.json`
- `schemas/product-pack-validation-result.schema.json`
- `schemas/product-pack-publication.schema.json`
- the existing `schemas/product-pack.schema.json`
- the existing `schemas/report-blueprint.schema.json`

`packages/typescript/contracts` generates TypeScript definitions from the same schemas used by
the Python validator. `config/product-pack-capabilities.json` is the server-owned registry of
available, unavailable, and deprecated generic capabilities. A publication gate rejects the
legacy `category_specific` policy so new packs cannot extend category branching.

## Runtime catalog

Migration `0022_product_pack_runtime_catalog` pairs each immutable Product Pack version with one
immutable report-blueprint version and adds an explicit active version. API, worker analytics,
and report rendering resolve the exact pair through `ProductPackCatalog`.

Repository files remain the bootstrap and local-test catalog. Production startup seeds missing
file-backed versions but compares checksums and refuses to mutate a version that already exists.
Administrator-published versions live in Postgres and do not require a code deployment.

## Authoring persistence and queue

Migration `0023_product_pack_authoring` adds:

- `product_pack_draft` for current state and optimistic revision;
- `product_pack_draft_revision` for immutable revision history;
- `product_pack_evidence_set` for private URI, checksum, byte size, row count, kind, and metadata;
- `product_pack_validation_run` for idempotent leased certification work;
- `product_pack_review_event` for authoring and publication audit; and
- a certification link on the immutable published Product Pack version.

Validation claims use `FOR UPDATE SKIP LOCKED`. A claim records worker ownership, attempt count,
and lease expiry. Expired leases are reclaimable, failures retry up to the configured maximum,
and cancellation is durable for queued or running work. Completion is accepted only from the
current lease owner. Publication rechecks the exact revision and checksum in one transaction.

## Certification suites

- **Quick** — JSON contracts, semantic references, safe formulas, blueprint ownership, immutable
  identity, bounded extraction patterns, and the generic-capability boundary.
- **Compact** — quick gates plus a checksum-addressed compact golden evidence manifest.
- **Full** — compact gates plus a full-source golden manifest and explicit regression dataset IDs.
- **Publication** — full requirements, tied to the exact revision and used as the only valid
  certification source for publication.

Evidence manifests deliberately reference private bucket objects. Raw evidence is not copied into
Postgres or returned in Product Pack APIs. Upload/curation of source evidence remains a separate
private-data operation; attaching a manifest itself does not execute or spend against a provider.

## Security boundary

The browser never receives the internal API token. The Next.js server creates an eight-hour,
HttpOnly, `SameSite=Strict`, HMAC-signed administrator session and proxies only safe Product Pack
paths. Mutations require same-origin requests. Production API writes require the matching
`PRODUCT_PACK_ADMIN_TOKEN`; production web access requires both the admin password and an
independent session secret.

Railway variables:

- web: `PRODUCT_PACK_ADMIN_PASSWORD`, `PRODUCT_PACK_SESSION_SECRET`,
  `PRODUCT_PACK_ADMIN_TOKEN`;
- API: `PRODUCT_PACK_BUILDER_ENABLED=true`, `PRODUCT_PACK_ADMIN_TOKEN`;
- worker: `PRODUCT_PACK_VALIDATION_CLAIM_LIMIT=1`,
  `PRODUCT_PACK_VALIDATION_LEASE_SECONDS=900`.

Use unrelated random values. The API token must match on web and API; neither the password nor the
session secret belongs on API or worker.

## API and application routes

Runtime:

- `GET /api/v1/product-packs`
- `GET /api/v1/product-packs/{pack_id}/versions/{version}`

Administrator:

- `GET /api/v1/admin/product-packs/status`
- `GET /api/v1/admin/product-packs/capabilities`
- `GET|POST /api/v1/admin/product-packs/drafts`
- `GET|PATCH /api/v1/admin/product-packs/drafts/{draft_id}`
- `GET|POST /api/v1/admin/product-packs/drafts/{draft_id}/evidence`
- `GET|POST /api/v1/admin/product-packs/drafts/{draft_id}/validations`
- `POST /api/v1/admin/product-packs/drafts/{draft_id}/validations/{run_id}/cancel`
- `POST /api/v1/admin/product-packs/drafts/{draft_id}/publish`

Application:

- `/admin/product-packs` — active catalog, draft portfolio, and governed draft creation;
- `/admin/product-packs/drafts/{draft_id}` — eight-stage guided authoring and certification
  workspace.

## Acceptance criteria

- A new category starts with a schema-valid generic pack and report blueprint.
- Adding a new category needs configuration and evidence, not category checks in core code.
- Every active pack resolves from Postgres with its exact report blueprint.
- A historical collection can still load its non-active exact pack version.
- Duplicate IDs/versions cannot overwrite an existing published bundle.
- A stale browser revision cannot overwrite a newer draft revision.
- Repeating the same validation request is idempotent for the same inputs.
- Multiple worker replicas cannot claim the same validation run.
- Expired leases retry; queued/running validations can be cancelled durably.
- Compact/full/publication suites cannot pass without their required evidence manifests.
- Publication cannot use an older validation or a changed checksum.
- Creating, editing, validating, and publishing a pack makes no paid provider or AI call.
- Existing collection definitions and AnalysisResults remain reproducible after activation changes.

## Verification commands

```bash
uv sync --frozen --all-packages --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages/python
uv run alembic -c database/alembic.ini upgrade head
uv run pytest
uv run rci-contracts --root .
pnpm contracts:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

The CI Postgres service executes the complete migration upgrade, downgrade, and re-upgrade cycle
and the Postgres integration suite. Production acceptance additionally verifies authentication,
draft creation, save/reload, a no-charge quick validation, cancellation behavior, and the locked
publication gate before any administrator publication is attempted.
