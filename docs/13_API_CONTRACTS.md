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
- `GET /collection-runs/{id}/scope-projection-preview` is an administrator-only, read-only
  projection over one terminal base run and enabled non-benchmark retailer. Query parameters are
  `retailer_id`, `projection_kind`, optional `source_audit_id`, and bounded item pagination. The
  checksum always covers the complete inventory. Phase 13.81 adds
  `audited_alias_reconciliation` under policy `audited-alias-reconciliation-v1`; its response
  explicitly includes raw/retained/excluded task and distinct-location counts,
  `denominator_gap_location_count`, coverage numerator and denominator location counts,
  `coverage_semantics`, raw-task retention, governed physical coverage, disposition, source
  evidence checksum, ordered inventory checksum, and bounded item detail. Existing 0053
  `canonical_alias_collapse` and `limited_provider_footprint` responses remain compatible.
- `POST /collection-runs/{id}/scope-projections` is administrator-only and idempotently approves
  the exact recomputed preview. The request supplies `retailer_id`, `projection_kind`, complete
  `projection_checksum`, `base_snapshot_checksum`, an identified review reason, and the audit ID
  when required. It never edits the base run, task, frozen geography, audit, or artifact. An audited
  unpaired gap is valid only when the completed retailer audit has exact reason
  `store_number_not_provider_safe` and no exact retained request twin; proximity, address, and
  shared ZIP cannot supply a mapping. The response repeats the immutable projection and coverage
  lineage used by recovery, materialization, AnalysisResult, publication readiness, and warnings.

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
- `GET /analyses/{id}/price-monitoring/catalog` returns the active publication-time Price
  Intelligence retailer catalog as schema `1.0.0-price-monitoring-catalog-page`. Required scope is
  `retailer`; optional filters are `q`, `brand_type`, exact `brand`, exact `seller`, `offset`, and
  `limit` (1–100). The envelope returns one contract-valid compact Price Monitoring view, facets,
  and exact total/filtered/returned/has-more pagination. Rows sort by distinct observed retailer
  locations descending, then product name and ID. The endpoint never builds a catalog on demand;
  missing materialization returns `404` so a trusted predecessor can remain active.
- `POST /internal/analyses/{id}/price-monitoring/catalog/materialize?retailer=...` requires the
  internal service token and backfills one active report catalog from retained evidence without a
  provider or AI call. Normal publication stages each retailer through the leased report job and
  atomically installs all catalogs only after the publication gate passes.

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

`POST /api/v1/matching-v2/review-queues/import` accepts the optional immutable-successor fields
`successor_of_version`, `carry_forward_certified`, `carry_forward_attribute_evidence`, and
`scope_only_pack_revision`. Attribute-evidence carry-forward is independent of final match-decision
carry-forward and requires an explicit predecessor. It copies only the latest human decision for a
proposal when the listing identity, attribute, current value and source, Product Pack version and
policy, AI output checksum, cited image, visible evidence, and original proposal checksum remain
identical; the new immutable decision supersedes the predecessor decision. A mismatch aborts the
decision carry-forward for that claim and leaves its complete predecessor history intact; the
import response reports every skipped proposal checksum. Global Product Pack or queue-policy
incompatibility still aborts the entire import. Scope-only mode
requires the predecessor and certified-decision fields and is deliberately fail-closed: the
successor Product Pack must add hard scope exclusions without removing any, while every other
Product Pack and matching-policy field remains identical after version references are ignored.
Each finalized predecessor listing
pair must also retain identical governed evidence, proposal, and attributes; only revision-derived
IDs and additive PDP image references may differ. Compatible comparable and not-comparable
decisions retain their reviewer, rationale, evidence, and supersession provenance. Unresolved cases
remain unresolved. Import never starts AI, PDP, collection, analysis, or publication work.

`GET /api/v1/matching-v2/review-queues/{queue_id}/ai-drafts/eligible-cases` returns only the
exposure-ranked case IDs and counts needed to prepare a queue-wide paid AI-review confirmation. It
may be scoped by `competitor_retailer_id`, excludes existing tasks and final decisions, reapplies
first-party seller policy, and fails closed when Search-derived observed-location evidence is
missing. `POST .../ai-drafts` accepts the confirmed unique IDs (1–1,500) and creates one durable,
idempotent, non-authoritative batch; it never certifies a relationship.

`GET /api/v1/matching-v2/review-queues/{queue_id}/attribute-evidence-claims` is the product-level
administrator work queue for AI image evidence. It collapses eligible pair-level proposals into one
claim per retailer listing and Product Pack attribute, while retaining every distinct cited image,
visible label excerpt, proposed value, confidence, affected match-case count, and counterpart
retailer as context. It accepts `batch_scope=latest_lineage|all_lineages`, optional
`root_batch_id`, `attribute`, `claim_status=all|awaiting_review|conflict|verified|rejected`,
`offset`, and `limit`. Repeated pair proposals are not counted as independent evidence. Multiple
proposed normalized values fail closed as a conflict.

`POST /api/v1/matching-v2/review-queues/{queue_id}/attribute-evidence-claims/{claim_checksum}/decisions`
records one append-only administrator decision for the product-attribute claim. Verification binds
the selected source proposal, complete claim membership, queue and Product Pack versions, cited
image, visible evidence, selected normalized value, and current claim checksum. Stale checksums and
unselected conflicts are rejected. Rejection applies to the complete claim, not just one repeated
pair observation. This route updates derived governed evidence only: it does not mutate raw Search,
PDP, or AI evidence; certify a match; run analysis; or publish reporting.

`POST /api/v1/matching-v2/review-queues/{queue_id}/attribute-evidence-claims/bulk-preview`
projects the complete current safe-consensus population for a named AI lineage scope. A claim is
eligible only when it awaits review, contains exactly one normalized value, fills an unknown rather
than changing an existing governed value, has at least 95% confidence across its observations, and
retains both the exact source image and visible label text. The response includes policy and
confirmation checksums, product/attribute/retailer counts, exclusion reasons, and a bounded sample.

`POST /api/v1/matching-v2/review-queues/{queue_id}/attribute-evidence-claims/bulk-commit`
requires an administrator identity and the exact current preview checksum. It recomputes the full
population, stops on stale or newly decided evidence, and persists every accepted claim in one
Postgres transaction. Every append-only decision retains the batch policy and confirmation
checksum. Conflicts, low-confidence evidence, refinements, and corrections remain unresolved. The
operation does not certify matches, start analysis, or publish reporting.

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
