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
- Source Product Pack ID/version matches the review queue.
- Legacy and Matching v2 authorities cannot be combined.
- AnalysisResult contract validation passes.
- Published Egg metrics reconcile to immutable match artifacts and the certified release.
