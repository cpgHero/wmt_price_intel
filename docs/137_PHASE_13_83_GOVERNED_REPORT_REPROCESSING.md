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

The first governed retry identified two independent retained-evidence defects rather than
masking them behind a generic server error:

- optional `regular_price` and `discounted_price` fields used provider zero sentinels. Those
  values now normalize to missing, while the authoritative listed price remains unchanged;
  a `$0.00` reference price can neither enter a report nor fail schema materialization;
- conflicting or malformed provider availability aliases now normalize to unknown. Stock is
  advisory metadata under this contract and cannot reject an otherwise eligible positive-price
  Search row. Sponsorship and seller-governance validation remain strict.

Spreadsheet-coerced numeric product identifiers also recover a leading zero only when a longer
numeric token in the retailer product URL is numerically equivalent. Unrelated URL numbers do
not rewrite product identity.

## Release and production acceptance

Focused regression coverage establishes the diagnostic contract. Production acceptance is
separate: every category replay must reach a terminal state, its materialized report must
pass the publication gate, and the resulting public report must be checked against retained
source evidence. A queued, running, failed, or blocked replay is not reported as complete.

The focused API diagnostic suite passes 23 tests; one PostgreSQL isolation test is skipped
only when no local test database URL is configured. The normalization, Matching v2, and
competitive-leadership regression suite passes 124 tests. Ruff format/check, Python
compilation, and Prettier checks pass. Browser execution remains a CI acceptance item when
the local Chromium binary cannot launch under the host sandbox.

No provider call, AI call, or paid collection credit is required for this reprocessing.
