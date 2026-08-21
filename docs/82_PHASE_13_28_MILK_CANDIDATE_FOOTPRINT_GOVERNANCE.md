# Phase 13.28 — Milk Candidate Footprint Governance

## Status

Implemented, deployed, and imported on August 20, 2026. AI assistance completed
for every corrected queue case; human certification and governed Milk replay
remain separate fail-closed gates. No MetricsCart or OpenAI call was made during
candidate regeneration.

## Problem

The first exhaustive Product Pack 1.5.0 Milk build emitted 6,396 cases. The
attribute matcher correctly allowed brand-independent specification matches,
but it did not know the products' observed locations. It therefore formed
national Cartesian combinations among regional products that never appeared
in the same competitive footprint. The queue was rejected before certification.

Static recovered Product Pack overrides also contained contradictions with
current Search titles, including reduced-fat products labeled as whole. The
candidate index treated integer and floating representations of the same
volume as different values and did not honor configured numeric tolerances.

## Generic correction

Matching v2 now carries immutable positive-price location evidence while it
builds listing candidates. Product Pack configuration, not a Milk branch,
selects `observed_overlap` candidate geography:

- a physical-store competitor must have at least one observed store within five
  miles of an observed Walmart store for the two products;
- a service-area retailer such as Amazon Same Day must share at least one
  observed ZIP service area with the Walmart product;
- missing candidate-location evidence fails closed;
- package volume and fat type must be known and compatible for Milk;
- brand remains descriptive, so regional and private-label products can still
  form valid many-to-one relationships where their footprints overlap; and
- optional claims remain reviewable when unknown instead of becoming blanket
  exclusions.

The candidate layer independently checks explicit current title evidence
against static overrides. Clear title evidence may correct an override only in
the new candidate evidence and records `search_override_correction` provenance.
The authoritative classifier and historical report metrics are unchanged.
Invalid enum sentinels are unknown. Numeric indexing treats `64` and `64.0` as
equal and honors Product Pack tolerances.

## Audited queue

The accepted local Product Pack 1.6.0 / policy 2.1.0-shadow.1 build is queue
version 2.5.0 with canonical queue checksum
`046450fabd69ede298f495cd34f6a577758ee3cff933e2ffa5e6197fec511f12`.
It contains 1,064 unique relationships:

- ALDI: 253 cases, 249 Walmart products, and 15 ALDI products;
- Amazon Same Day: 811 cases, 233 Walmart products, and 171 Amazon products;
- zero duplicate retailer-product pairs;
- zero cases missing package volume or fat type;
- zero known seller-ineligible listings; and
- zero obvious title-versus-fat-type contradictions in admitted listings.

For ALDI, 11,426 of 11,772 theoretical pairs fail attribute gates and 93 more
fail observed-footprint overlap. For Amazon Same Day, 140,998 of 146,496 fail
attribute gates and 4,687 more fail service-area overlap. These partitions
reconcile exactly to the 1,064 admitted cases.

## Authority and lifecycle

Queue 2.5.0 is a new immutable certification scope. It does not mutate or
reinterpret the rejected 6,396-case artifact, older decisions, source Search
files, PDP evidence, or audit history. No prior Milk decision is automatically
carried forward unless the succession rules prove exact Product Pack, policy,
pair, and structured-evidence equivalence.

The remaining sequence is:

1. review the guarded bulk-certification preview and human-confirm final outcomes;
2. manually review any case not accepted through the guarded bulk flow;
3. export an immutable certified release;
4. replay Milk without automatic fallback;
5. audit every comparison-basis × 1/3/5-mile portfolio document; and
6. activate the replacement only after semantic and live-route acceptance.

## Verification

- focused Matching v2, normalization/classification, Product Pack, API, and
  queue suites: 206 passed;
- complete Python suite: 622 passed and 13 environment-gated integration or
  separately supplied golden tests skipped as designed;
- full three-retailer Milk golden regression: passed against the original
  Walmart, ALDI, and Amazon source files;
- Ruff formatting and lint: passed;
- all 60 normative JSON documents and generated TypeScript contracts:
  validated;
- Prettier, TypeScript lint, typecheck, and unit tests: passed (70 tests);
- Next.js production build: passed;
- GitHub CI run `32443021145`: passed, including mypy, migrations, E2E, and all
  four container builds;
- Railway API deployment `2cb11c80-78f6-43a1-b575-df9414e11f2a` runs commit
  `a0f60016b211e0bd2e5b24d743a3170b0a4bf5a7`;
- production queue import ID: `c396f810-fdab-4d4d-82e3-8f8ee376ff20`, with
  1,064 pending cases and zero carried-forward decisions;
- governed AI-assistance batch `c1192df2-b766-44a7-b642-84f1c3549eff`: 1,064
  succeeded, zero terminal failures, estimated model cost `$34.4601425`;
- guarded 50-case-chunk preview: all 1,064 cases are eligible for explicit human
  bulk confirmation; the preview proposes 887 comparable and 177 not-comparable
  outcomes and records advisory warnings without treating them as hidden final
  decisions;
- full source profile: 348,980 rows reconciled into a deterministic queue;
- evidence-profile file SHA-256:
  `42a6cc8f499de3a8993b29e407e362d9a5ab0ce21cba3ce7c250c748c6e8ba93`;
- review-queue file SHA-256:
  `d48f005b615fc0873f2fbdd8da87dfee87436ad3462d19031fd277292e11e7d7`;
- no paid provider or model call was made.
