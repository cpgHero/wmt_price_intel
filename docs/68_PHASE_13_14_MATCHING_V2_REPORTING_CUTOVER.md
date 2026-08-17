# Phase 13.14 — Matching v2 Reporting Cutover

Status: implementation and release validation

## Outcome

An administrator can explicitly snapshot the current certified Matching v2 gold set and bind that immutable release to a new analysis run. The replay uses certified comparable relationships only. Certified not-comparable labels and unresolved cases remain excluded from price comparison metrics.

## Authority boundary

- Search remains authoritative for store-specific price, observed availability, and location.
- PDP, brand, and image evidence may support identity and attribute certification.
- Human-certified Matching v2 labels are authoritative for relationship eligibility in a cutover replay.
- The worker does not add automatic relationships when a Matching v2 release is bound.
- AI never changes labels, prices, denominators, winners, or report math during replay.

## Release flow

1. Export the current certification view as a contract-valid gold set.
2. Compute its canonical SHA-256 checksum.
3. Store the document, coverage counts, Product Pack version, queue, releaser, and checksum as an immutable release.
4. Clone the selected source analysis input into a new queued analysis run and bind the release ID.
5. Convert comparable labels into generic scope-aware rules. Regional/many-to-one relationships are scoped to each benchmark product's observed store footprint.
6. Run relationship resolution and all deterministic report calculations with automatic fallback disabled.
7. Publish release ID, checksum, certified counts, and unresolved exclusions in AnalysisResult provenance and data-quality metrics.

## Coverage semantics

`queue_case_count = certified_comparable + certified_not_comparable + unresolved_excluded`.

Only `certified_comparable` labels can produce price observations. A small reported population is therefore an honest reflection of current certification coverage, not permission to fill gaps automatically.

Certified many-to-one relationships remain separate product-location evidence rows. A competitor
product may therefore support more than one certified benchmark relationship where the benchmark
products' observed footprints overlap. This does not create an automatic match or copy one price
to an unobserved location: each row still requires positive Search evidence for both products in
the applicable ZIP/store context. Global and explicit-location rules retain strict one-to-one
conflict validation.

## API

`POST /api/v1/matching-v2/review-queues/{queue_id}/gold-set/replays`

Body:

```json
{
  "source_analysis_id": "fresh_shell_eggs-...",
  "released_by": "platform-owner"
}
```

The operation is idempotent for the same review queue, gold-set checksum, and source analysis.

## Release gates

- Migration upgrades and downgrades cleanly.
- Gold-set schema validation passes.
- Certified-only matching test proves an eligible automatic pair is omitted.
- Product IDs remain opaque strings.
- Source category ID matches the review queue; the replay intentionally advances to the exact Product Pack version certified by the queue.
- Legacy and Matching v2 authorities cannot be combined.
- AnalysisResult contract validation passes.
- Published Egg metrics reconcile to immutable match artifacts and the certified release.

## Production verification — 2026-08-17

- Release ID: `0dd6df6d-9f9c-4251-9041-7d294c7042c5`
- Release checksum: `06373a3baabdfbaa2348c979e01ad51e36428f795b1b692ba49ebe2d0aa2e12c`
- Governed analysis: `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-0dd6df6d`
- Certified coverage: 1,305 queue cases; 99 comparable labels; 431 not-comparable
  labels; 775 unresolved cases excluded; automatic fallback disabled.
- Published evidence: 62 relationship records representing 62 retailer/product-ID pairs after
  location/profile admission. Every published relationship is confirmed and belongs to the
  certified comparable set; zero uncertified or certified-not-comparable relationships leaked
  into reporting. Thirty-seven certified relationships had no admissible co-observation under the
  current source data and Product Pack profiles and therefore produced no price comparison.
- Result validation: all deterministic metrics are evidence-linked, metric-reference coverage is
  100%, and unsupported numeric claims are zero. Overall validation remains `needs_review`
  because unresolved certification coverage is disclosed as a warning rather than hidden.
- Live UI: the report and included-product scorecard drawer were browser-verified in Railway
  production.
- Release evidence: GitHub Actions run `32080559215` passed Python, TypeScript, contracts,
  reversible migrations, 13 Playwright scenarios, and all four container builds. Railway worker
  deployment `883fad41-5f53-4c10-9e5d-04dcda19c487` is active.
