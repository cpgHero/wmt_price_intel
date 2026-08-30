# Phase 13.78 — Catalog-driven location eligibility reconciliation

## Status

Implemented and test-verified on August 30, 2026. Production deployment and the first Kroger apply
remain pending until active paid Search runs have drained. No production row, collection task,
provider call, PDP request, AI task, or report was changed while this phase was built.

## Problem

Location eligibility is calculated when a location roster is imported. A later Retailer Catalog
correction therefore did not automatically revise eligibility already persisted in Postgres. Kroger
exposed the risk: its provider requires the canonical eight-digit store ID, but the prior broad
numeric rule admitted both canonical IDs and seven-digit duplicates. The source retains both forms
for audit; only canonical provider-safe IDs should enter a new collection geography.

A full source reimport could refresh the flag, but it would touch the complete 157,866-row master
when only a retailer policy changed. Direct SQL would be faster but would duplicate catalog logic,
provide weak audit lineage, and be easy to apply without a dry run.

## Implemented control

`rci-location-eligibility` re-evaluates persisted rows through the same `RetailerCatalog` policy used
by the importer. It is retailer-agnostic; Kroger is the first policy correction, not a core-code
branch.

- The default is read-only and emits a complete JSON plan.
- `--retailer` may be repeated to constrain the scan; omitting it evaluates the full location
  master.
- Unknown retailer IDs fail before any mutation.
- `--apply` requires both `--requested-by` and `--change-reason`.
- The plan records the catalog SHA-256, selected retailer IDs, a SHA-256 over every selected
  persisted eligibility input, before/after counts and reasons, every exact proposed change, and a
  versioned checksum of the complete proposal.
- Apply requires the reviewed dry-run JSON through `--reviewed-plan`; it will not silently create a
  replacement plan. The parser rejects an altered checksum, an applied artifact, an unsupported
  schema, ambiguous `--retailer` overrides, or an output path that would overwrite the evidence.
- Import and apply take the same cross-process PostgreSQL advisory lock for their complete
  operation. Apply then regenerates the catalog-derived plan, requires exact equality with the
  reviewed artifact, creates a durable audit containing the reviewed-plan checksum, locks the
  location table as a second defense, rereads the selected population, and rejects a stale snapshot.
- All row updates and the audit transition to `completed` commit in one transaction. A failure
  rolls back the corrections and leaves a durable failed audit with a safe error message.
- Rows superseded by an authoritative import retain the more specific
  `superseded_by_authoritative_import` lifecycle reason; reconciliation cannot resurrect them.
- A second dry run after a successful apply must report zero changes.

Migration `0050_location_reconcile` adds the durable
`location_eligibility_reconciliation_run` audit table. The existing location rows remain the
authoritative current state, and historical/frozen collection geographies remain unchanged.

## Kroger policy correction

The catalog now requires `^[0-9]{8}$` for `kroger_us` store numbers. Identifiers remain strings, so
leading zeros are preserved. Fixture validation finds 1,369 active canonical eight-digit Kroger
locations eligible for future collection. Seven-digit duplicates stay in the master with
`store_number_not_provider_safe`; they are not deleted or rewritten.

After deployment and only after paid runs are idle, the production operator must run and retain the
dry-run artifact before applying:

```bash
rci-location-eligibility \
  --retailer kroger_us \
  --output /tmp/kroger-location-eligibility-dry-run.json
```

The dry-run totals must reconcile to the expected production population before the explicitly
identified apply is executed:

```bash
rci-location-eligibility \
  --apply \
  --reviewed-plan /tmp/kroger-location-eligibility-dry-run.json \
  --requested-by "<identified administrator>" \
  --change-reason "Require canonical eight-digit MetricsCart Kroger store IDs" \
  --output /tmp/kroger-location-eligibility-apply.json
```

Then rerun dry mode and require `changed_rows = 0` and `eligible_after = 1369` before resolving any
new Kroger geography. The exact production audit ID and counts must be appended here after apply;
this document does not claim them early.

## Verification

- Canonical eight-digit Kroger IDs are eligible; their seven-digit forms are not.
- The complete supplied location fixture and read-only production inspection both contain exactly
  2,667 Kroger rows: 1,369 canonical eight-digit rows and 1,298 seven-digit rows. All 2,667
  production rows are active and presently eligible, so the reviewed first production plan must
  disable exactly 1,298 and leave exactly 1,369 eligible.
- Dry-run planning does not write an audit or modify a location.
- Apply is identified, reasoned, auditable, idempotent, and preserves authoritative-retirement
  lineage.
- Import and reconciliation are mutually exclusive for their entire operations; a state change
  still invalidates the reviewed checksum and fails closed.
- Unknown retailer IDs and anonymous/unreasoned applies are rejected.
- Migration `0050_location_reconcile` is the current migration head. Its downgrade succeeds only
  before audit history exists.

## Rollback

Before a production apply, code can be rolled back with no data change. After apply, the audit
contains every before/after decision. A reversal must use a new reviewed catalog policy and a new
reconciliation run; do not delete the audit or hand-edit flags. Migration 0050 refuses downgrade
when audit history exists and is not the operational rollback for an already applied eligibility
decision. Before the first production apply, all legacy importer processes from the prior release
must be drained; thereafter every importer and reconciliation process shares the durable advisory
lock.
