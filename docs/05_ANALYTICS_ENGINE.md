# Product Classification, Matching, and Analytics Engine

## Pipeline

NormalizedOffer -> deterministic scope rules -> deterministic attribute extractors -> AI fallback for unresolved fields -> human-review queue if confidence/risk threshold requires -> classified offer -> dedupe -> match candidates -> comparison profiles -> summary metrics -> validation -> AnalysisResult.

## Deterministic responsibilities

- price parsing and currency validation,
- unit conversions,
- package weight/count normalization,
- deduplication,
- geographic intersection/proximity,
- match eligibility,
- lowest-price selection,
- medians/means/rates/counts,
- parity calculations,
- distance calculations,
- availability/coverage metrics.

## Product Pack responsibilities

Each pack defines:

- inclusion/exclusion scope,
- target terms and hard exclusions,
- attributes and ordered declarative extraction rules,
- required strict-match fields,
- compatible match relaxations,
- unit normalization formulas and the comparison metric for each profile,
- brand aliases and retailer private-label sets where relevant,
- forbidden metrics,
- private-label definitions where relevant,
- QA rules,
- reporting segments,
- regression benchmarks.

The engine implements six category-neutral extraction primitives: constant, canonical/raw field,
measurement with configured unit factors, regex number capture, term-to-value mapping, and boolean
term mapping. Product names, category attributes, claim vocabularies, and unit assumptions are data
in Product Packs; the core engine does not branch on them.

Matching profiles enforce `same_brand`, `private_label_equivalent`, and `ignore_brand` uniformly.
`wildcard_if_one_unknown` permits a match only when exactly one side supplies a missing dimension;
two unknown values never establish equivalence.

## Reference category lessons

### Eggs
Count, size, grade, color, organic, housing claim and brand materially change comparability. Normalize to price/dozen only after valid package matching.

### Milk
Exact volume and milk type are mandatory; specialty claims (organic, lactose-free, ultrafiltered, A2, etc.) matter. Same-brand, private-label, and all-brand equivalent are distinct analytical lenses.

### Bananas
Displayed each price can mislead when expected piece weight differs. Preserve each-price perception and weight-normalized economics separately. Bunch count ranges must be normalized cautiously.

### Strawberries
Primary unit is package weight. Do not invent price-per-strawberry when berry counts are absent. 1 lb and 2 lb packages can reverse the retailer winner and must remain distinct.

## Match evidence

Every match record retains both source offer IDs, geography key, profile ID/version, normalized attributes, selected prices, computed unit metrics, and explicit rejection reason where candidates were not comparable.
