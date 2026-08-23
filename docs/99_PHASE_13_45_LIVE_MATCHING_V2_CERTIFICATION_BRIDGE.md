# Phase 13.45 — Live Matching v2 Certification Bridge

## Outcome

Live Search-by-ZIP collections can now produce the same exhaustive, governed Matching v2 operational certification queue previously built from historical CSV fixtures. The bridge makes no provider or AI call. It reads retained evidence, verifies checksums, builds a non-authoritative proposal queue, and optionally imports that queue into the protected Match Certification workflow.

## Inputs and authority

- Search collection run IDs select immutable successful Search page artifacts.
- Search remains authoritative for store/ZIP observation, positive-price availability, price, and sponsorship.
- The latest successful normalized PDP snapshot per admitted retailer product supplies identity, seller, attributes, descriptions, identifiers, and available images.
- Product Pack classification, seller governance, Matching v2 profiles, tiers, hard blockers, and candidate limits remain generic configuration.
- A generated queue is explicitly `operational_match_certification`; it is not a gold set and cannot drive reporting before human certification and release.

## Processing

`scripts/build_live_matching_v2_queue.py`:

1. reads every task for the selected collection runs;
2. accepts only successful HTTP 2xx Search artifacts and verifies each compressed-object SHA-256;
3. uses the versioned retailer adapter to extract and normalize every result row;
4. writes one immutable-evidence CSV per retailer so location frequency remains auditable;
5. selects the latest successful PDP snapshot per collection-linked retailer product;
6. verifies and bundles retained raw PDP objects without a new MetricsCart request;
7. runs the generic Product Pack classifier and Matching v2 shadow evaluator;
8. applies Product-Pack-governed, deterministic candidate retrieval after attribute and geography eligibility, retaining a bounded evidence-review funnel without deciding comparability;
9. emits every retrieved candidate, including insufficient-evidence proposals, into an exhaustive operational queue;
10. blocks import when the evidence profile contains a critical quality finding;
11. validates the queue schema and canonical checksum; and
12. imports through the existing protected repository path, which rejects known third-party seller cases and preserves append-only review history.

## Spring Valley production scope

- Search runs: `e962ced9-9e83-4cf3-b5f2-2cf514009ae3` and `3093b480-d633-4f61-af47-ba499a355bb9`
- Product Pack: `vitamins_supplements@1.0.5`
- Benchmark: Walmart (Spring Valley allowlist only)
- Competitors: Amazon Same Day, Target, Costco, Sam's Club, Kroger, Walgreens, CVS, Meijer, and BJ's
- Intended queue version: `2026.08.23-spring-valley-4`

Meijer remains explicitly partial because 45 of its 85 Search pages were unavailable. PDP evidence cannot infer missing assortment observations.

Three pre-import diagnostics were rejected. The first empty queue exposed over-strict active-ingredient handling. The second produced 40,162 unresolved pairs because a title fallback mislabeled the entire title as the active ingredient and geography alone admitted too many unknown-attribute combinations. The third reduced the funnel to 2,243, but representative sampling found numeric and dosage-form noise admitting implausible pairs. None became an authoritative queue. Product Pack 1.0.5 removes that false field, makes structured PDP specification fields generically available to declared `raw.*` sources, and bounds checksum-governed lexical retrieval to five identity-oriented candidates per Walmart product and retailer.

The audited production queue imported successfully as database record `0a21f7b0-adcc-4bff-bae9-aa106b2176a9`, version `2026.08.23-spring-valley-4`, checksum `3a1da8ad4f1ce4ce80c22d7414d5e05617b5d4d82d25fbce18992a1c61d41044`. It contains 1,186 pending cases covering 111 Spring Valley anchors and 605 competitor products across all nine selected competitors. Database reconciliation found zero cases with missing positive-price location evidence, zero non-Spring Valley benchmark anchors, and zero known third-party seller cases. The proposals remain non-authoritative until certification.

## Human and reporting gates

1. An administrator reviews the imported queue in `/admin/matching-v2`.
2. Paid AI drafts remain a separate, disclosed approval and are not launched by this phase.
3. Final comparable/not-comparable decisions become authoritative only after certification.
4. A checksum-bound gold-set release is created only after queue completion.
5. A governed analysis replay binds that exact release, excludes unresolved cases, and disables automatic fallback.
6. Reporting must pass relationship, observation, metric-reference, and semantic publication gates before activation.

## Verification

GitHub Actions run `32674158407` passed Python tests, type checking, schema and reversible migration checks, all TypeScript checks, browser tests, production builds, and all four service-container builds. Production runs Product Pack 1.0.5 and the imported queue passed the post-import database reconciliation above.
