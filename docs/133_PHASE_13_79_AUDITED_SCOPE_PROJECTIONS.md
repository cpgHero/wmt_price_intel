# Phase 13.79 — Audited collection scope projections

## Status

Implemented and locally test-verified on August 30, 2026. Migration
`0053_scope_projections`, its administrator APIs, and the downstream reporting safeguards are
ready for independent review. They are not deployed and have not changed production data. No
provider call, paid credit, production write, frozen task, frozen geography, raw artifact, PDP
record, certification label, or published report was created, changed, or deleted in this phase.

## Problem

A frozen collection is historical evidence and cannot be edited when later evidence proves that
part of its planned provider scope was duplicated or unavailable. Two Egg retailers demonstrate
different cases that must not share one denominator:

- Kroger's frozen run contains 2,667 task scopes: 1,369 canonical eight-digit store requests and
  1,298 seven-digit aliases. The aliases were later made ineligible by completed location audit
  `6901fd05-6390-4052-a331-88f5c16ef773`. Removing tasks would destroy lineage, while treating
  1,369 / 2,667 as coverage would incorrectly call an alias collapse a 51.33% network footprint.
- Wegmans has 114 frozen physical locations. Provider evidence accepts 89 and rejects exactly 25
  with the governed HTTP 400 invalid-store response. Every exclusion is backed by a distinct
  immutable raw-artifact ID, verified compressed-object checksum, HTTP-status metadata, and the
  reviewed exact response-body checksum; mutable task error text is diagnostic only. This is a
  real limited provider footprint: 89 / 114 = 78.07%, below the 95% scoreability minimum. It must
  remain visible as limited source evidence but cannot publish a scorecard or zero-valued metrics.

## Implemented model

An administrator can now preview and approve one immutable projection for one retailer in one
frozen base run. The projection has an immutable header and a complete, ordered inventory of every
source task. Its checksum covers policy, base snapshot, retailer, projection kind, source evidence,
task and physical-location counts, both ratios, disposition, and the inventory checksum.

The two projection kinds have deliberately different semantics:

| Projection kind | Raw-task retention | Governed coverage | Scoreability rule |
|---|---:|---:|---|
| `canonical_alias_collapse` | Retained tasks / all frozen retailer tasks | Canonical physical scopes retained / canonical physical scopes | Must equal 100%; every excluded alias maps to one retained canonical task and completed audit evidence |
| `limited_provider_footprint` | Retained tasks / all frozen retailer tasks | Distinct provider-valid physical locations / all distinct frozen physical locations | Scoreable only at or above 95%; otherwise `unavailable` |

Task counts remain an inventory control. Physical-location counts drive network coverage, so adding
keywords or pages at one store cannot weight that store multiple times or move a retailer across
the 95% boundary. One physical location cannot have conflicting retained/excluded decisions.

## Immutable evidence and database controls

Migration `0053_scope_projections` adds:

- `collection_scope_projection` — the reviewed header, source evidence, distinct-location counts,
  separate ratios, disposition, checksum, reviewer, reason, and manifest.
- `collection_scope_projection_task` — every frozen retailer task, its decision, reason, complete
  source snapshot, and—only for a canonical alias exclusion—the retained canonical task mapping.
- `analysis_input_scope_projection` — immutable projection ID/checksum lineage for each materialized
  analysis input generation.
- `scope_projection_id` and `scope_projection_checksum` on recovery plans, so recovery cannot be
  previewed under one denominator and launched under another.

Database triggers require the projection organization to match the base run, target only an enabled
non-benchmark retailer, bind canonical collapse to a completed audit, keep source and mapped tasks
inside the same base-run/retailer scope, require every alias mapping target to be retained in the
same projection, forbid a mapping for limited-footprint exclusions, validate analysis-input and
recovery-plan bindings, and prevent update/delete of projection lineage. Completed location audits
are immutable after this migration. Runtime reads independently rehash the manifest and inventory,
reconcile every header value to the reviewed manifest, and compare a bound location-audit snapshot
to its durable audit row before use.

Limited-provider exclusions have an additional evidence boundary. The Retailer Catalog supplies a
reviewed adapter-specific error contract. An exclusion requires a non-null raw-artifact ID, valid
64-character object checksum, MetricsCart provider metadata matching the frozen retailer and
adapter, metadata HTTP 400, and an exact uncompressed response-body SHA-256 in that contract's
allowlist. The complete verified artifact proof and contract checksum are copied into the immutable
task snapshot and projection source evidence. `collection_task.last_error` is hashed only as a
mutable diagnostic and cannot authorize an exclusion.

## Administrator workflow

Both routes require authenticated administrator access. Pagination affects item display only; the
preview checksum always covers the complete inventory.

1. Preview with `GET /api/v1/collection-runs/{run_id}/scope-projection-preview`, providing
   `retailer_id`, `projection_kind`, optional canonical `source_audit_id`, `item_offset`, and
   `item_limit` (maximum 500).
2. Review the raw task and distinct-location counts, source evidence checksum, both ratios,
   scorecard disposition, inventory checksum, and every exclusion/mapping.
3. Approve with `POST /api/v1/collection-runs/{run_id}/scope-projections`, echoing the complete
   projection checksum and base snapshot checksum plus an identified review reason. Approval
   recomputes under a transaction lock and rejects drift.
4. Pass the projection ID/checksum when previewing or approving an affected recovery. Continuation
   plans inherit the exact projection.
5. Pass every recovery-bound projection to composite materialization. Projection filtering occurs
   before readiness, precedence resolution, lineage, artifact selection, analysis input creation,
   and queueing.
6. The idempotent materialization path rechecks the complete immutable association rows; missing,
   reordered, or changed projection lineage fails closed.

## Egg acceptance contract

The deterministic Kroger acceptance fixture proves exactly:

- 2,667 raw tasks and frozen location records;
- 1,369 retained canonical eight-digit tasks;
- 1,298 excluded seven-digit aliases;
- 1,298 non-null mappings to 1,298 retained canonical tasks;
- 51.3311% raw-task retention, separately disclosed; and
- 100.0000% canonical physical-scope coverage, therefore scoreable.

The deterministic Wegmans acceptance fixture proves exactly:

- 114 raw tasks across 114 distinct frozen physical locations;
- 89 provider-valid retained scopes and 25 governed invalid-store HTTP 400 exclusions;
- 78.0702% raw-task retention and provider-network coverage; and
- `unavailable` under the 95% minimum, with no scorecard or zero-valued metric.

A read-only production audit of Egg base run `10f96d03-0064-411a-a2d9-41eec6eec8f9` independently
verified all 25/25 failed Wegmans artifacts with zero object/body errors. All carry metadata HTTP
400 and the exact raw JSON response
`{"error":"Failed to process Request.","message":"Please provide a Valid Store"}`. Its reviewed
uncompressed body SHA-256 is
`8679d22d8b7999dd491147500b111c3749f24b11d62730945de6681a44b26191`; all 25 compressed immutable
objects also reconcile to artifact checksum
`05539dcd37a08ecc5427e839f9a9b65eeda03286ac2a2bcee2b2705d85a52054`, while retaining distinct
artifact IDs per task. Production projection approval must still recompute the complete reviewed
manifest. A read-only audit and fixture are not authorization to write production.

## Reporting safeguards

The complete Matching v2 certified release remains in `matching_v2_certification_coverage` as audit
provenance. The worker additionally creates a checksummed
`matching_v2_reporting_coverage` projection over scoreable retailers. Rules for unavailable
retailers are removed before profile scoping or presentation. Relationships, candidates, product
decisions, analytics, and scorecards may contain no unavailable retailer. Relationship counts must
still reconcile exactly—globally and per retailer—for every scoreable retailer. Certified
relationships withheld only because raw evidence is unavailable remain visible as a warning and in
the full release lineage; they do not become false unmatched or zero outcomes.

## Verification

- Exact Kroger and Wegmans count/ratio/disposition fixtures.
- Multi-keyword/page Wegmans fixture proving coverage uses distinct locations, not task rows.
- Conflicting location dispositions, unmapped aliases, missing raw artifacts, mismatched artifact
  HTTP metadata, unallowlisted response bodies, unproved provider errors, benchmark targets,
  disabled targets, header/manifest drift, source-evidence drift, incomplete inventories, and stale
  materialization lineage fail closed.
- Administrator authentication, bounded item pagination, reviewed checksum replay, recovery
  binding, result schema, generated TypeScript contract, worker reconciliation, renderer warnings,
  and unavailable-output leakage tests.
- Alembic offline upgrade generation and CI's real-PostgreSQL upgrade/downgrade/upgrade gate.

## Deployment and rollback

Deploy migration, API, worker, and web documentation together only after CI and independent review.
Before a projection exists, migration 0053 can downgrade normally. Once immutable projection
history exists, downgrade refuses rather than deleting evidence. Operational rollback is to stop
new approvals/materialization and restore the prior application build while retaining the additive
tables. A projection is never edited or deleted; a later evidence decision requires a new reviewed
projection and a new analysis input generation.
