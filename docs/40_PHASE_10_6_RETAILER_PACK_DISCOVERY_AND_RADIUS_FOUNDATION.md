# Phase 10.6 — Retailer Packs, Governed Discovery, and Store-Level Competition

## Outcome

Make a location-specific Search observation the primary price fact, then derive trusted
cross-retailer comparisons from governed product identity, retailer semantics, and explicit
store-to-store proximity. Product Packs continue to define category scope and comparability.
Retailer Packs define retailer-specific semantics and must never make a product-equivalence
decision by themselves.

## Architectural boundaries

1. Search is authoritative for observed price, availability, retailer location, ZIP, and time.
2. PDP is authoritative for reusable product identity and descriptive attributes. PDP never
   overwrites a Search price or location observation.
3. Product Packs govern category admission, required attributes, unit conversions, matching
   lenses, QA, and reporting.
4. Retailer Packs govern retailer identity, location and price semantics, brand portfolios,
   enrichment behavior, and retailer-specific cautions.
5. Brand role is candidate-generation evidence only. Final matches still require Product Pack
   compatibility across every required product attribute.
6. AI may draft discovery queries, Product Packs, attribute hypotheses, and match explanations.
   Deterministic code and governed human decisions remain authoritative.

## Phase 10.6A — Retailer Pack and brand foundation (this increment)

- Add normative Retailer Pack, brand-foundation, and brand-discovery contracts.
- Import the supplied 172-row private-label master and 45 alias observations with source
  checksums and canonical application retailer IDs.
- Resolve brands retailer-first, exact canonical before exact alias, and fail closed when
  unresolved. No fuzzy match can become authoritative.
- Require `in_private_label_matching=true`, `review_status=Approved`, an eligible temporal
  status, and an eligible private-label class before strict private-label equivalence.
- Preserve Product Pack rules as category-specific compatibility and backward-compatible
  overlays. Preserve Brand Workbench decisions as the highest-precedence governed override.
- Record exact Retailer Pack and brand-foundation checksums in new analysis outputs.

## Phase 10.6B — Study discovery and certification

1. User supplies a category brief, benchmark retailer, competitors, fulfillment mode, geography,
   and cost ceiling.
2. AI drafts Search-first discovery queries and likely exclusions; the user approves the paid
   sample.
3. Search samples produce provisional product scope and observed brand candidates.
4. The engine removes obvious noise and deduplicates `(retailer, product ID)` before PDP calls.
5. Every unique provisionally admitted product is PDP-enriched once per reusable context, with an
   additional context only when retailer/product price variants require it.
6. AI drafts Product Pack configuration and evidence-backed unknown-brand hypotheses.
7. Deterministic contract, fixture, compact-golden, and full-golden certification gates run.
8. A human approves immutable Product Pack and Retailer Pack/brand-foundation versions.

An unknown brand enters the discovery queue as `Candidate/Unknown`; Search or PDP evidence never
silently mutates the approved brand foundation.

## Phase 10.6C — Recurring two-pass collection and enrichment

1. Pin exact Product Pack and Retailer Pack versions in the Study snapshot.
2. Collect Search pages at approved retailer locations.
3. Validate page/location completeness before analysis.
4. Apply inexpensive scope and hard-noise rules.
5. Deduplicate admitted products by canonical retailer product identity.
6. Reuse unexpired PDP snapshots; enqueue only missing/stale identities under a separate budget.
7. Reclassify with PDP attributes while retaining Search price/location authority.
8. Build canonical product distribution footprints from Search observations.
9. Generate deterministic, lens-specific candidates and apply governed match relationships.
10. Pair benchmark and competitor stores explicitly, then calculate store-specific outcomes.
11. Run metric/readiness gates before AI narrative or publication.

## Phase 10.6D — 1/3/5-mile physical-store reporting

- Resolve and approve a superset of physical competitor stores within five miles of each
  benchmark store. Reuse that collection for one-, three-, and five-mile filters.
- Use benchmark store locations as the executive denominator.
- Primary view: lowest nearby competitor price within the selected radius.
- Sensitivity view: nearest competitor store outcome.
- Preserve retailer store number, provider location ID, latitude/longitude, ZIP, distance, and
  pairing method in evidence.
- Treat ZIP-only comparisons as a secondary compatibility view for physical retailers.
- Treat Amazon Same Day as a ZIP/delivery-market exception until a physical-store model exists.

## Phase 10.6E — Trust and rollout gates

- Re-run existing beef, milk, strawberries, bananas, and eggs goldens without silent metric drift.
- Add discovery fixtures for canonical, alias, ambiguous, legacy, unknown, and rejected brands.
- Prove that a private-label brand classification alone cannot match incompatible package,
  product-type, flavor/form, claim, or unit attributes.
- Surface pack versions, source authority, comparison radius, denominator, and match status in
  every drill-down and exported evidence set.
- Only after the primary app is accepted should HTML, shareable, email, and workbook renderers be
  synchronized from the same immutable result and presentation context.

## Acceptance tests

1. `Great Value` at Walmart resolves to an approved private label, while the same text at ALDI is
   unresolved.
2. `Better Goods` resolves through a retailer-scoped alias; unknown brands remain unclassified.
3. Acquired and partner brands cannot enter strict private-label equivalence without an explicit
   governed override.
4. A human rejection overrides a foundation suggestion without modifying the foundation version.
5. Search price/store fields remain unchanged after PDP enrichment.
6. Existing Product Packs and goldens pass without category branches in core code.
7. Future fresh shell egg support remains primarily configuration plus generic capabilities.
