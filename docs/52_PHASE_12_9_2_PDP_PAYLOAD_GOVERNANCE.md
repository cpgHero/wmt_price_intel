# Phase 12.9.2 — PDP Payload Governance and Zero-Credit Re-normalization

## Decision

Search evidence remains authoritative for product price, observed availability, sponsorship, store,
and collection time. Product Details evidence is authoritative for product identity and descriptive
attributes and is a contextual reference for fulfillment, reviews, demand, and merchandising. No
PDP price or stock field may overwrite a Search observation.

The immutable compressed provider response remains the source record. A versioned normalization is
an append-only derived artifact linked by raw checksum. Normalizer upgrades never mutate a raw
object or an earlier snapshot document.

## Payload utilization audit

The supplied full Walmart, ALDI, and Amazon examples were reviewed field by field. The `2.0.0`
normalizer projects useful fields into these governed groups:

| Group | Source fields | Use |
|---|---|---|
| Identity | name, brand, seller, descriptions, URL, category, model, identifiers | Product index, seller filter, matching, match review, reporting |
| Package semantics | specification, physical properties, variant configuration | Product Pack completion and deterministic matching evidence |
| Media/content | primary/all images, videos, enhanced/360 flags | Product reference and review experiences |
| Commerce reference | item condition, regular/discounted PDP price, discount flags, offers | PDP detail only; never authoritative store price |
| Fulfillment | retailer fulfillment, store, pickup, shipping, returns | PDP detail and diagnostic context only |
| Reviews | rating/counts, distribution, aspects, retailer summary | Product detail and future review-intelligence context |
| Demand | weekly/monthly volume and retailer ranks | Contextual merchandising signal; never a price denominator |
| Relationships | variants, similar, sponsored, also-viewed, bought-together | Future assortment/discovery context; excluded from automatic exact matching |
| Source context | PDP retailer, source, ZIP | Provenance and audit |

Large provider-native enhanced-content bodies remain raw-only because they are duplicative, can be
very large, and are not required for current decisions. Every source key is recorded in a field
inventory. Any key not covered by the governed mapping is written to
`unmapped_source_fields`, aggregated in the normalization audit, and queued for explicit schema
review instead of being silently ignored.

## Historical repair

Migration `0028_product_detail_renormalization` creates a replica-safe leased queue keyed by raw
snapshot and normalizer version. The worker verifies the compressed-object checksum, decompresses
and parses the retained response, applies the current retailer adapter, validates the derived
contract, and writes an immutable normalization revision. It then refreshes canonical identity from
the newest successfully normalized PDP evidence. The workflow never calls MetricsCart and records
zero billable credits.

The Price Intelligence read model includes the current canonical seller plus a structured `pdp`
context. Its cache key incorporates the canonical-product revision, so completed backfills become
visible without publishing a new analysis or restarting the API.

The read model intentionally projects decision-useful summaries rather than copying the full PDP
into every product row. Descriptions, identifiers, package attributes, fulfillment, ratings,
demand, media counts, and relationship counts are available in Product Overview. Provider-native
offers, relationship bodies, and enhanced content stay in the governed normalization/raw evidence
so the product index remains responsive and those larger structures can be loaded on demand by a
future specialized workspace.
