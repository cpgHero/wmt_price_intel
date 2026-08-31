# Phase 13.81 — Audited alias reconciliation with governed denominator gaps

## Status

Implemented and locally test-verified on August 30, 2026. Forward migration
`0054_audited_alias_reconcile`, the additive API/AnalysisResult fields, publication warning, and
documentation are ready for independent review and the mandatory real-PostgreSQL CI gate. They are
not deployed and have not approved or materialized a production projection. This phase makes no
provider call, consumes no paid credit, writes no production row, and changes no frozen task,
geography, audit, artifact, PDP evidence, match decision, analysis input, or published report.

Migration 0053 remains historical authority for `canonical_alias_collapse` and
`limited_provider_footprint`. Phase 13.81 does not edit migration 0053 or change either policy's
manifest/checksum bytes.

## Problem and production-shaped evidence

The Egg Kroger frozen run contains 2,667 retailer tasks after the provider-safe location policy was
audited:

- 1,369 provider-safe tasks use eight-digit Kroger store numbers and are eligible to execute;
- 1,298 tasks use seven-digit provider-unsafe store numbers disabled by the completed audit;
- 1,296 of those seven-digit tasks have an otherwise-identical retained request whose store number
  is exactly the zero-filled eight-digit value; and
- store `1400945` at ZIP `45069` and store `2900768` at ZIP `25064` have no identical retained
  request in the frozen run.

Calling the two unmatched scopes aliases would fabricate evidence. Removing them would hide the
frozen collection's denominator. Treating all 1,298 disabled task rows as missing physical stores
would also be wrong because 1,296 are exact request duplicates. The governed outcome is therefore:

- raw task retention: `1,369 / 2,667 = 0.513311`;
- exact mapped aliases: 1,296;
- distinct audited unpaired physical gaps: 2; and
- governed physical coverage: `1,369 / (1,369 + 2) = 0.998541`.

Coverage is above the existing 95% minimum, so Kroger is scoreable with an explicit nonblocking
two-gap warning. The two gaps never become zero-valued stores.

## Additive policy and invariants

Phase 13.81 adds projection kind `audited_alias_reconciliation` under the separate policy version
`audited-alias-reconciliation-v1`. Its complete task inventory has three possible decisions:

| Decision | Mapping | Required proof |
|---|---|---|
| `provider_safe_canonical_scope` | null | Eligible frozen location, durable physical location, and eight-digit provider-safe store number |
| `audited_alias_of_provider_safe_canonical_scope` | exact retained task | Same adapter, ZIP, page, request payload, and only seven-to-eight-digit zero-fill store normalization |
| `audited_provider_unsafe_unpaired_scope_gap` | null | Exact completed-audit change with `after_reason=store_number_not_provider_safe` and no exact retained request twin |

The policy never infers physical or request equivalence from proximity, address, city, state, or a
shared ZIP. One excluded physical location cannot be both a mapped alias and a gap. One alias
physical location cannot map to multiple retained locations, and multiple alias physical locations
cannot collapse into one retained location.

Task rows remain the immutable inventory control. Distinct definition-bound frozen location IDs
drive physical coverage, so keywords/pages cannot weight one store more than once.

## Legacy provider-request identity

The historical Kroger tasks predate persisted `_provider_request_contract` payloads. Read-only
production inspection established the exact compatibility shape:

- 0 of 2,667 tasks persist `_provider_request_contract`;
- all 2,667 stored request fingerprints equal the canonical checksum of the original persisted
  request payload;
- 2,663 tasks are cancelled with zero attempts, zero billable credits, null HTTP status, and no
  raw artifact; and
- four called rows have one attempt, three billable credits, and immutable same-run raw artifacts:
  one HTTP 200 success plus three HTTP 404 failures.

All four artifacts prove provider `metricscart`, retailer `kroger_us`, adapter
`metricscart_kroger_search_zipcode`, method `GET`, path `/mc/kroger/search/zipcode/`, and parameter
names `keyword`, `page`, `store`, and `zipcode`, with task, object, and body checksums.

The projection therefore keeps two request representations instead of mutating history:

1. `persisted_request_payload` and `persisted_request_fingerprint` preserve and rehash the exact
   historical database values.
2. The executable snapshot adds one projection-sealed normalized current-catalog contract and
   derives a new executable fingerprint. Its provenance mode is
   `reconstructed_current_catalog`; `historical_parameter_values` and
   `historical_catalog_defaults` are explicitly listed as unverified.

Every called legacy row must match its own immutable same-run artifact, including provider,
retailer, adapter, task ID, method, path, sorted parameter names, HTTP status, object checksum, and
body checksum. A legacy no-artifact row is accepted only when it is an exact zero-attempt,
zero-credit cancellation with null HTTP status. Each reconstructed adapter must have at least one
called artifact; the manifest seals every called artifact ID/checksum, not a cherry-picked sample.

Recovery clones use the sealed executable payload and recompute the clone fingerprint from that
payload. Original payload/fingerprint values remain only in projection lineage. New collection
tasks can persist a modern frozen contract directly and must match the same sealed contract.

## Database trust boundary

Migration `0054_audited_alias_reconcile` adds
`denominator_gap_location_count` and expands the existing immutable projection tables. For the new
kind, database validation does not trust caller-supplied snapshot JSON:

- the base run must be terminal;
- the projection retailer must be enabled, non-benchmark, and present in the completed audit;
- actual task run, retailer, adapter, request inputs, persisted payload/fingerprint, status, usage,
  and artifact bindings are checked;
- each task location/store/ZIP must equal its definition-version-bound frozen geography row;
- the complete projection inventory must equal the full actual base-run/retailer task population;
- ordinals must fill the declared range exactly;
- the manifest and source evidence are canonical-hashed, and every header count, ratio, semantic,
  audit ID, reviewed base-snapshot checksum, and disposition must match;
- the ordered inventory checksum is recomputed with set-based canonical serialization;
- raw retention and governed coverage use PostgreSQL-compatible six-decimal half-up rounding;
- exact mappings, unpaired-gap absence of a twin, completed-audit changes, one-to-one physical
  mappings, and distinct gap counts are recomputed from actual rows; and
- one deferred header-level completeness scan avoids an O(N²) full-inventory scan per task insert.

The database checksum-binds the reviewed `base_snapshot_checksum` to the header and manifest, but it
does not implement a second global serializer across every retailer in the base run. The
administrator approval path recomputes the complete frozen-run snapshot before insert, and every
recovery/materialization path recomputes it again before applying a projection. A privileged direct
SQL writer that invents a self-consistent base checksum therefore cannot bind that projection to
recovery or reporting. Once a new-policy projection commits, targeted source guards reject
insert/update/delete drift in its retailer task population, updates/deletes to its base run,
definition version and task-linked frozen geography location rows, and updates/deletes to
referenced raw artifacts. The geography-resolution header, unrelated location rows, and
precomputed edges are outside this projection's identity boundary. Tasks for nonprojected
retailers remain covered by the authoritative full-run checksum recomputation at the API/runtime
boundary rather than by an overbroad database freeze.

Approval takes ordered share locks on the target retailer's task rows and task-linked,
definition-bound geography rows before locking the parent run and geography resolution, then locks the current
retailer-location eligibility row and any referenced raw artifact while each inventory row is
validated. This order serializes concurrent source updates and late child inserts without a
task-to-parent deadlock. The live `retailer_location` master intentionally remains mutable after
commit for future collection planning; the projection instead seals its approval-time eligibility
value and immutable completed audit. Projection-bound recovery and materialization explicitly
restore that sealed retained eligibility, so the live master is not consulted to reinterpret
historical projection evidence. A retry of the identical approval recomputes the full raw base
checksum and returns the verified immutable record without rebuilding an eligibility-dependent
scope preview.

For audited legacy rows, projection-bound runtime rehydrates the sealed executable request payload
before recomputing the raw base checksum, while retaining the original persisted fingerprint for
that checksum lineage. Retained recovery items then use the sealed payload with a newly derived
executable fingerprint. Later catalog-content changes therefore cannot reinterpret an approval;
the historical adapter identifier must still remain registered so the base task can be loaded.

Precomputed `collection_geography_edge` distance rows are not projection identity, denominator, or
scoreability inputs and remain outside the Phase 13.81 source guard. Downstream analysis uses the
coordinates sealed on the task-linked frozen geography snapshots.

Canonical object keys use C collation to match Python's deterministic Unicode key ordering. The
production-shaped real-PostgreSQL test requires the full 2,667-row approval and deferred validation
to finish within a bounded 30-second CI budget.

Downgrade refuses while any new-kind or nonzero-gap history exists. With only 0053 history,
downgrade restores the prior validators and constraints, drops Phase 13.81 helpers in dependency
order, removes the additive column, and permits a subsequent clean re-upgrade. Existing 0053
header/manifests and ordered inventories must remain byte-identical through that round trip.

## API, recovery, and reporting behavior

The existing administrator routes remain the public workflow:

1. `GET /api/v1/collection-runs/{run_id}/scope-projection-preview` accepts the new projection kind,
   retailer, completed audit ID, and bounded item pagination. The checksum covers all items.
2. `POST /api/v1/collection-runs/{run_id}/scope-projections` recomputes the complete preview under a
   transaction lock and idempotently approves only the exact checksum/base snapshot.
3. Exact recovery preview, approval, and launch remain bound to projection ID/checksum. Excluded
   aliases and gaps cannot be launched.
4. Composite materialization filters the complete inventory before readiness, precedence, lineage,
   artifacts, analysis inputs, and analysis queueing.
5. AnalysisResult and generated TypeScript contracts expose the gap count, coverage numerator,
   coverage denominator, and semantic definition.
6. Publication validates raw counts, raw retention, location counts, gap denominator, coverage,
   threshold, and disposition before rendering. A valid scoreable nonzero gap is always disclosed,
   even if its rounded ratio displays `1.000000`.

The report renderer is advanced to `2.15.2`, so immutable artifact reuse cannot serve an older
pre-Phase-13.81 readiness interpretation.

The warning is informational and publishable. Inconsistent coverage lineage blocks publication.
Existing version-1 limited-provider behavior is not reinterpreted by the new warning validator.

## Verification contract

Local deterministic/unit coverage includes:

- exact 2,667 / 1,369 / 1,296 / 2 production-shaped preview counts;
- exact `0.513311` raw retention and `0.998541` governed coverage;
- no mapping inferred for same-ZIP or nearby unpaired scopes;
- audit reason/retailer mismatch and conflicting physical classifications fail closed;
- modern and reconstructed legacy request identity, all-called artifact corroboration, and sealed
  recovery-clone fingerprints;
- Python/renderer half-up tie behavior (`1/128 = 0.007813`);
- gap warnings keyed to positive gap count even when coverage rounds to one;
- corrupt raw counts, location counts, raw retention, coverage, semantic, or disposition block
  publication; and
- byte-compatible version-1 limited-provider rendering remains publishable.

The real-PostgreSQL CI suite is mandatory before deployment and includes:

- migration upgrade, allowed 0054→0053→0054 round trip with exact 0053 history equality, and
  downgrade refusal after new history;
- the full 2,667-row legacy insert/commit and idempotent approval;
- a projection-bound recovery launch proving sealed executable payload/fingerprint and retained-only
  scope;
- Python/PostgreSQL canonical checksum and half-up rounding parity;
- direct-write rejection for nonterminal bases, partial inventories, header/manifest/inventory/raw
  ratio drift, null exact-alias maps, mapped gaps, false gaps with exact twins, wrong audit retailer
  or change, spoofed snapshots, request input drift, frozen-geography drift, sealed-contract drift,
  called-artifact drift, invalid no-artifact legacy status/usage, and post-approval source drift;
  and
- unchanged 0053 canonical and Wegmans limited-provider safeguards.

## Deployment and rollback

Deploy migration, API, worker, schemas/contracts, web documentation, and report renderer together
only after independent review and the real-PostgreSQL GitHub Actions gate pass. Before deployment,
run a read-only production preflight that reconstructs all 2,667 rows and proves the exact expected
counts/checksums without writing a projection. After deployment, preview must be re-read and
approved by the authorized administrator before recovery or materialization.

Operational rollback is to stop new approvals/materialization and restore the prior compatible
application build while retaining additive immutable evidence. Never delete or rewrite the base
run, source tasks, audit, artifacts, projection history, or analysis lineage. A schema downgrade is
allowed only when no Phase 13.81 history exists; otherwise it fails closed.
