# Phase 13.72 — Retailer Registry and Source-to-Metric Lineage

## Outcome

Platform Docs now contains two maintained reference guides for the platform owner,
administrator, analysts, and engineering:

1. **Retailer Integration Registry** records the current live Search-by-ZIP and PDP
   contracts for all 18 enabled U.S. Search retailers, including paths, credit costs,
   required request context, location behavior, seller policy, provider limits,
   selective enrichment, and honest callability boundaries.
2. **Source-to-Metric Lineage** traces immutable raw collection evidence through
   normalization, location resolution, Product Pack admission, PDP/brand/seller evidence,
   certified matching, radius-native geography, deterministic analytics, publication gates,
   UI metrics, and supporting drill-downs.

The documentation version advances from `1.3.70` to `1.3.71` and the owner-visible guide
count advances from 18 to 20.

## Source authorities audited

The guides were derived from current executable/configured sources rather than historical
sample files:

- `config/retailer-catalog.json`
- `config/product-detail-catalog.json`
- `config/metricscart-endpoint-overrides.json`
- active versioned Retailer Packs and seller evaluator
- normalized-offer and Price Intelligence JSON Schemas
- Price Intelligence and Competitive Leadership deterministic projectors
- Matching v2 certification and trust-gated publication contracts
- the August 27 authoritative ALDI numeric Store-ID refresh

The registry explicitly states that `enabled` means planner/runtime support, not universal
provider availability. The immutable run-specific retailer preflight remains authoritative
for one retailer, category, request shape, location, and time context.

## Trust-critical lineage rules

- Search is authoritative for store-specific package price, positive-price observed presence,
  sponsorship, retailer product identity, and collection time.
- The frozen location-master snapshot is authoritative for current store identity and physical
  geography. Amazon Same Day remains a delivery-ZIP service area.
- PDP enriches identity, package/specification facts, brand, seller, imagery, and descriptive
  context but never replaces local Search price or presence.
- Product Packs govern admission, category attributes, units, relationship tiers, and price
  bases. Retailer Packs govern retailer-specific endpoint, identifier, location, seller, and
  sponsorship behavior.
- Final Matching v2 certification governs relationship comparability. AI review remains
  advisory and price similarity is not semantic match evidence.
- Product-location rows, distinct benchmark stores, distinct competitor stores, certified
  relationships, scored pairs, and delivery ZIPs are separate grains.
- Comparable-store coverage counts a benchmark store once when one or more valid local
  comparisons exist; multiple products at that store do not inflate coverage.
- Physical competitors use the selected 1-, 3-, or 5-mile radius; service-area competitors
  use the same delivery ZIP.
- Zero, unknown, unavailable, and unscored remain distinct report states.

## Automated maintenance contract

The Platform Docs unit suite now reads the current Search catalog, PDP catalog, and runtime
overrides. For every enabled Search retailer, it requires the guide to contain the retailer ID,
current Search path, and effective PDP runtime path. Additional assertions protect:

- adapter enablement versus run-specific callability;
- the 30-day selective PDP cache policy;
- known-third-party and missing-seller behavior;
- Search, location, PDP, Product Pack, and Retailer Pack authority;
- distinct-store deduplication;
- physical-store versus service-area counting;
- 1-, 3-, and 5-mile comparison geography; and
- the prohibition on AI calculating or repairing authoritative values.

The browser test verifies both guides are discoverable through Platform Docs search and that
the maintained guide count is 20.

## Change scope

This phase changes documentation and documentation regression tests only. It makes no
MetricsCart Search or PDP call, no OpenAI call, no certification decision, no source-data or
location mutation, no analytical formula change, and no report publication or archival change.

## Required future maintenance

Any Search/PDP path, credit, parameter, location behavior, runtime override, seller policy,
enabled status, source authority, normalized field, grain, denominator, formula, exclusion,
radius policy, label, drill-down, or semantic publication gate change must update the relevant
catalog/schema/code, both Platform Docs guides, regression tests, and the append-only change
order in the same release.
