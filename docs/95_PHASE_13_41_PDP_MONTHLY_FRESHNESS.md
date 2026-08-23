# Phase 13.41 — Monthly PDP freshness policy

Date: August 22, 2026

## Decision

Product Details enrichment uses a 30-day freshness window by default. Search remains the
store-specific authority for price, availability, and sponsorship on every collection. PDP calls
provide product identity and package evidence and therefore do not repeat on every Search run.

## Current behavior

- Scope/noise classification runs before PDP planning.
- The planner selects one representative positive-price observation for each distinct admitted
  retailer product.
- A normalized HTTP 200 snapshot with an unexpired cache entry is a zero-credit cache hit.
- Only new products, products without successful normalized PDP evidence, or products whose
  evidence is at least 30 days old enter the normal paid plan.
- Re-normalizing retained immutable PDP payloads after a parser improvement does not call the
  provider.
- A deliberate identity refresh may override the cadence only through a separately estimated and
  approved paid run.

`PRODUCT_DETAIL_CACHE_TTL_SECONDS` remains configurable. Its production/default value is now
`2592000` seconds (30 days). A future seven-day policy can be introduced by changing the governed
configuration and documenting the effective date; no code branch by product category is required.

## Existing evidence transition

At deployment, successful normalized HTTP 200 snapshots observed within the preceding 30 days are
eligible to have `cache_expires_at` extended to `observed_at + 30 days`. This prevents snapshots
created under the former seven-day default from being purchased again merely because the policy
changed. `cache_expires_at` is operational freshness metadata; raw payloads, observed timestamps,
normalized documents, failed snapshots, and audit lineage are not rewritten or deleted.

## Verification

- The package-level default is asserted as exactly 30 days.
- The worker and immutable-raw recovery path consume the same exported default when the environment
  variable is absent.
- Deployment examples and the environment template use `2592000`.
- Existing cache-hit tests continue to prove that a fresh PDP snapshot creates no job and consumes
  zero credits.

## Production verification

GitHub Actions run `32615296706` passed Python, TypeScript, contracts, formatting, linting, type
checking, reversible migrations, 14 browser tests, production builds, and all four service-container
builds. Railway deployed commit `c100b66`; the live worker reported the default as `2592000` seconds.
The bounded transition extended 2,768 successful normalized HTTP 200 snapshots observed during the
preceding 30 days, and a post-update reconciliation returned zero remaining eligible snapshots on
the former expiration. No Search, PDP, or AI call was made.
