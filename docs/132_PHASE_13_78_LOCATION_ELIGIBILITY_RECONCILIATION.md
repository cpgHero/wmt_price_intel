# Phase 13.78 — Catalog-driven location eligibility reconciliation

## Status

Implemented, deployed, and production-verified on August 30, 2026. The first reviewed Kroger plan
was applied only after all paid Search runs were terminal. The reconciliation changed current
location eligibility only; it did not rewrite a frozen geography, historical task, raw artifact,
provider response, PDP record, AI decision, or report.

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

The production operator ran and retained the dry-run artifact after paid runs became idle:

```bash
rci-location-eligibility \
  --retailer kroger_us \
  --output /tmp/kroger-location-eligibility-dry-run.json
```

The reviewed dry run reconciled exactly to 2,667 selected rows, 1,298 proposed disables, and 1,369
remaining eligible canonical locations before the explicitly identified apply was executed:

```bash
rci-location-eligibility \
  --apply \
  --reviewed-plan /tmp/kroger-location-eligibility-dry-run.json \
  --requested-by "<identified administrator>" \
  --change-reason "Require canonical eight-digit MetricsCart Kroger store IDs" \
  --output /tmp/kroger-location-eligibility-apply.json
```

Production audit `6901fd05-6390-4052-a331-88f5c16ef773` records the completed apply. Its reviewed
plan checksum is `7b07bc6dbce372ea7f0aed0d364d09f5bdc29ae4b5cca7ec39b7f6cb2e29149d`.
The immediate second dry run returned `changed_rows = 0`, `eligible_before = 1369`, and
`eligible_after = 1369`. New Kroger geographies may now resolve only from those eligible canonical
rows.

## Verification

- Canonical eight-digit Kroger IDs are eligible; their seven-digit forms are not.
- The complete supplied location fixture and production audit contained exactly 2,667 Kroger rows:
  1,369 canonical eight-digit rows and 1,298 seven-digit rows. Audit
  `6901fd05-6390-4052-a331-88f5c16ef773` disabled the 1,298 aliases and left exactly 1,369 eligible;
  the immediate second dry run proved `changed_rows = 0`. The older frozen Egg run still contains
  all 2,667 task scopes. Phase 13.77 therefore blocks paid Kroger recovery and marks Kroger
  unavailable/no-scorecard. Follow-on Phase 0052 must bind a scope projection to this audit before
  the 1,369-row denominator may be used for recovery or scoring.
- Dry-run planning does not write an audit or modify a location.
- Apply is identified, reasoned, auditable, idempotent, and preserves authoritative-retirement
  lineage.
- Import and reconciliation are mutually exclusive for their entire operations; a state change
  still invalidates the reviewed checksum and fails closed.
- Unknown retailer IDs and anonymous/unreasoned applies are rejected.
- Migration `0050_location_reconcile` is directly followed by the current
  `0051_composite_evidence` head. Its downgrade succeeds only before audit history exists.
- Release commit `8259a0ae67a24e840931999652c4a6bc3ff306a9` deployed to the API as Railway
  deployment `aa589a13-05ee-411a-9710-b077fda463d7`; the production database reported
  `0050_location_reconcile` as its migration head before the apply.

## Rollback

Before a production apply, code can be rolled back with no data change. After apply, the audit
contains every before/after decision. A reversal must use a new reviewed catalog policy and a new
reconciliation run; do not delete the audit or hand-edit flags. Migration 0050 refuses downgrade
when audit history exists and is not the operational rollback for an already applied eligibility
decision. Before the first production apply, all legacy importer processes from the prior release
must be drained; thereafter every importer and reconciliation process shares the durable advisory
lock.
