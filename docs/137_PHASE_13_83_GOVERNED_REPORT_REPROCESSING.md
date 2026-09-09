# Phase 13.83 — Governed report reprocessing diagnostics

## Purpose

Reprocess the retained category evidence under the positive-price Search store-distribution
contract without collecting new evidence or calling a provider or AI service. Reprocessing
creates a new immutable analysis generation; it does not rewrite a prior report.

## Authoritative distribution rule

For an exact retailer product, `distribution_store_count` is the count of distinct,
nonblank store IDs where that product appears in a store-level Search result with a numeric
price greater than zero. Stock status and sponsorship do not gate the count. A retailer
location roster cannot add an unobserved store. Service-area Search observations remain
separate as `service_area_presence_count` and are never represented as stores or inventory.

Seller and category admission rules continue to apply before an observation is eligible.
The reprocessed coverage response uses the governed fields
`distribution_search_offers`, `distribution_stores`, and
`service_area_presence_count`; legacy rollups are not allowed to substitute for them.

## Failure diagnostics

- Administrator operations now show recent failed analysis runs with bounded, redacted
  error details and separately show current blocked report-materialization jobs. Active
  blocked jobs remain visible even after the 24-hour incident window, and jobs without a
  known total stage count remain valid diagnostic rows.
- Report-materialization failures preserve expected HTTP errors and record a bounded,
  redacted administrator diagnostic for unexpected failures, including the exact job and
  report request context. Full tracebacks remain in protected server logs.

## Release and production acceptance

Focused regression coverage establishes the diagnostic contract. Production acceptance is
separate: every category replay must reach a terminal state, its materialized report must
pass the publication gate, and the resulting public report must be checked against retained
source evidence. A queued, running, failed, or blocked replay is not reported as complete.

The focused API diagnostic suite passes 23 tests; one PostgreSQL isolation test is skipped
only when no local test database URL is configured. Ruff format/check, Python compilation,
and Prettier checks pass. Browser execution remains a CI acceptance item when the local
Chromium binary cannot launch under the host sandbox.

No provider call, AI call, or paid collection credit is required for this reprocessing.
