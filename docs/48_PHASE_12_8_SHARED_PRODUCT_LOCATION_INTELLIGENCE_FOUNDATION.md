# Phase 12.8 — Shared Product-Location Intelligence Foundation

## Outcome

Price Intelligence and Competitive Intelligence now begin from one canonical, versioned
product-location observation population. The shared projector owns eligibility, source authority,
location enrichment, identity enrichment, governed brand classification, and latest-row selection.
Downstream modules may aggregate or compare these facts, but they no longer rebuild the population
with separate rules.

This phase is an upstream integrity change. It preserves the existing Price Intelligence and
Competitive Product Leadership user experiences while making their evidence reconcilable before
the remaining Competitive Intelligence mockup work is expanded.

## Canonical grain and authority

The canonical grain is:

`retailer × retailer product ID × retailer location × latest observation in the collection run`

The authority rules are:

- Search owns package price, regular/discounted price fields, sponsorship, observation time, and
  location-specific availability.
- A positive Search price is the governed available/in-stock signal.
- The retailer location master owns store or service-area identity, ZIP, city, state, country,
  latitude, and longitude.
- PDP enrichment may replace Search identity fields such as product name, brand, image, and URL;
  it cannot replace Search price, availability, location, or observation time.
- Retailer Packs, the governed brand universe, and approved overrides own brand identity and the
  private-label/regional/national/unclassified role.
- Product Packs own classification and comparison metrics such as package price or price per pound.
- Retailer and product IDs remain strings, including leading zeros.

## Admission and deduplication

An observation enters the canonical population only when it is in Product Pack scope, has a
positive USD Search price, and has a usable store or service-area identity. Exclusions remain
counted by reason for quality reporting.

Duplicate product-location rows are reduced to the latest `collected_at` value. The immutable offer
ID is the deterministic tie breaker. Conflicting prices remain disclosed as a quality count even
though only the selected latest row reaches downstream metrics.

Each population receives a deterministic SHA-256 checksum over its authoritative retailer,
product, location, offer, price, time, and Product Pack metric values. Price Monitoring publishes
that checksum and the canonical observation schema version in its source metadata.

## Shared runtime boundary

`ProductLocationProjector` produces immutable `ProductLocationObservation` rows and population
quality metadata. It is consumed in two ways:

1. Price Monitoring converts each canonical row into its retailer-only product, geography,
   distribution, quality, and evidence views.
2. Competitive Product Leadership converts the same row into the Product Pack-selected comparison
   basis, then applies governed product relationships and 1/3/5-mile or same-ZIP correspondence.

The API's full-retailer preparation and predicate-pushed selected-product path load the same
analysis-scoped Product Pack and brand revision and call the same projector. A cold competitive
request therefore retains the performance benefit of reading only selected products without
bypassing PDP identity or brand governance.

## Contracts and provenance

`schemas/price-observation.schema.json` version 1.1.0 is the canonical portable observation
contract. It includes Product Pack version, retailer display name, governed brand status, identity
authority, location authority, PDP references, Search price fields, sponsorship, availability, and
all classified price metrics.

`schemas/price-monitoring-view.schema.json` now requires the canonical observation schema version
and population checksum. Competitive Product Leadership contract version 1.1.0 exposes the same
governed brand, PDP reference, Search price context, sponsorship, and offer ID without changing
metric authority.

## Persistence boundary

This phase intentionally reuses immutable classified Parquet artifacts and existing API caches; it
does not claim that the historical `price_intelligence_snapshot` tables are populated. Durable
cross-run materialization belongs with Competitive History and price-movement work, where snapshot
completeness, comparable Product Pack/relationship versions, and continuous product-location pairs
can be certified together. Current snapshot calculations do not depend on those future tables.

## Acceptance tests

- Price and Competitive projections select the same product, location, latest offer, price, PDP
  identity, and governed brand role.
- Leading-zero product and store IDs survive without coercion.
- Search/PDP disagreements preserve Search price while using PDP identity.
- Search/location-master disagreements preserve location-master geography.
- Zero-price, out-of-scope, unsupported-currency, and unknown-location rows cannot enter either
  module and remain visible as exclusion counts.
- Duplicate selection and checksums are deterministic regardless of input row order.
- The canonical observation and both downstream response contracts validate.
- The phase requires no new MetricsCart or OpenAI calls.

## Verification

```bash
uv run mypy apps packages/python
.venv/bin/ruff check apps packages/python
.venv/bin/pytest
pnpm contracts:check
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```
