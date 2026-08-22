# Phase 13.32 — Controlled Publication Acceptance and API-Only Collection Contract

## Outcome

This phase proves the Phase 13.31 durable publication path with a small certified Strawberry replay,
then with the larger Milk replay. It also makes MetricsCart Search by ZIP APIs the only collection
mechanism for all future studies and prevents live payload drift from silently producing incomplete
reports.

## Search API contract

The versioned contract in `config/retailer-catalog.json` pins the SHA-256 hashes of the
owner-supplied 2026-08-16 MetricsCart catalog and its endpoint export. Fourteen Search by ZIP sample
responses were audited. All expose `query` plus a top-level `results` array and the same 31 result
fields.

The adapter maps explicitly governed aliases into canonical Search offers. Every successful page
must have a recognized result-array path and object rows that satisfy the required field-presence,
non-null identity, price-type, and sponsorship-type rules. A recognized empty array remains a valid
pagination stop. An unrecognized shape or invalid result fails closed as `schema_drift` after the raw
response is written. This preserves billable evidence and prevents a provider change from appearing
to be a legitimate zero-result page.

Search price greater than zero is authoritative for observed/in-stock status. Search
`is_sponsored` is authoritative for sponsorship and may be null. Provider stock flags remain raw
diagnostic evidence. Historical CSVs remain available for reproducibility, but their column names
do not govern a live API mapping and they cannot create a new production collection.

Only Walmart, ALDI, and Amazon Same Day Search adapters remain enabled in V1. Catalogued retailers
must pass endpoint, required-parameter, location, billing, empty-page, and response-mapping preflight
before enablement.

## Controlled publication acceptance

1. Rebuild Strawberry from its retained certified release without MetricsCart or OpenAI calls.
2. Observe queued, leased, staged, audited, and atomically activated materialization states.
3. Reconcile every configured comparison basis at 1, 3, and 5 miles and all Price Architecture
   documents against the semantic trust audit.
4. Confirm the prior Strawberry report remains active until the replacement becomes `ready`, then is
   recoverably archived in the activation transaction.
5. Repeat with Milk to validate large-report stage resumption, progress visibility, lease safety,
   and bounded retry behavior.

## Acceptance gates

- Provider and contract unit suites pass, including recognized empty pages, null sponsorship,
  unknown shapes, missing required fields, and non-object result entries.
- Generated TypeScript contracts contain `schema_drift`.
- Ruff, mypy, Python tests, contract tests, TypeScript checks, browser tests, builds, and container
  gates pass.
- Production provider configuration loads the pinned contract without making a paid call.
- Strawberry and Milk each finish with zero semantic errors and complete required scopes.
- No predecessor is archived before its replacement is ready.
- No Search rows, raw objects, PDP evidence, certification history, immutable releases, archived
  reports, or audit lineage are deleted.

## Cost

The controlled replays use retained governed evidence and make no MetricsCart or OpenAI request.
Future paid Search collections are protected by the same estimate, approval, rate-limit, immutable
raw-evidence, response-contract, and billable-ledger controls.
