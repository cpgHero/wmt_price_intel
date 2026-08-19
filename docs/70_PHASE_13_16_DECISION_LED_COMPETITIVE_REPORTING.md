# Phase 13.16 — Decision-led Competitive Reporting

Status: implementation and release validation

## Outcome

Competitive Intelligence becomes a decision workspace rather than a collection of partially
overlapping report tabs. The primary report navigation is:

1. **Executive Overview** — portfolio-level retailer coverage, readiness, matched evidence,
   leadership position, executive narrative, product decisions, and retailer scorecards.
2. **Price Architecture** — governed comparable cohorts and the included product relationships
   behind each cohort.
3. **Product Leadership** — product- and store-level price leadership, footprint, match groups,
   price ladders, store comparisons, market performance, exceptions, and history readiness.
4. **Assortment & Whitespace** — range, distribution, brand, exclusive-product, and missing-option
   evidence kept separate from direct price comparison.
5. **Data Integrity** — definitions, exclusions, source authority, evidence coverage, and explicit
   limitations.

The former outer Products and Geography tabs are removed from primary navigation. Their useful
product and location capabilities remain available in Product Leadership, Price Architecture,
Assortment & Whitespace, and evidence drawers. Their sparse or engineering-oriented projections
are not presented as finished business reporting.

## Decision hierarchy

The report answers questions in this order:

1. **Can the result be trusted?** Identify the pinned snapshot, certified relationship authority,
   selected comparison basis, retailer evidence state, and unresolved limitations.
2. **Where does Walmart lead or trail?** Show retailer-level scorecards and ready-view leadership
   without inventing a composite score.
3. **Which products explain the outcome?** Drill from retailer and cohort summaries to governed
   product relationships, images, attributes, and store evidence.
4. **Where does the outcome occur?** Use benchmark-store geography, 1/3/5-mile correspondence,
   exact ZIP for service-area retailers, market tables, maps, and store exceptions.
5. **Is it a price problem or an assortment problem?** Keep comparable price outcomes separate
   from exclusive products, distribution gaps, and whitespace.

## Source authority

| Evidence | Authoritative use | Prohibited use |
| --- | --- | --- |
| Search | Positive store-specific price, observed availability, sponsorship, collection time | Product identity enrichment when PDP evidence exists |
| PDP | Product identity, package attributes, brand/seller evidence, descriptions, imagery | Replacing store-specific Search price or availability |
| Location master | Store, ZIP, city, state, country, latitude, longitude | Inferring product availability |
| Product Pack | Eligibility, normalization, attribute policy, comparison bases, cohort definitions | Category branches in generic analytics or rendering |
| Retailer/Brand Packs | Retailer identifiers, first-party policy, brand ownership/type evidence | Overriding a known hard product-specification conflict |
| Matching v2 release | Certified comparable and not-comparable relationship decisions | Filling unresolved cases with automatic fallback |

## Analytical capability matrix

### Supported by the current Egg snapshot

- Governed exact/equivalent product relationships and match-certification evidence.
- Package price and supported normalized unit price, including price per dozen for Eggs.
- Walmart lower, competitor lower, and parity outcomes with explicit denominators.
- Absolute and percentage price gaps derived from the same atomic comparison values.
- Footprint-level product price ladders with local-rank distribution, Walmart rank-one share,
  product price ranges, and below/tied/above counts. Store Comparisons retains local detail.
- Retailer, product, store, state, city, and local-radius geographic analysis.
- Snapshot price dispersion and exception analysis where the current deterministic result
  provides the necessary observations.
- Brand name/type and assortment analysis where governed evidence is present.
- Sponsorship from the Search `is_sponsored` field.
- Data-quality, evidence-state, readiness, and certification-coverage reporting.

### Not supported by the current data

- Price-change response, persistence, volatility, stability, or trend claims. These require at
  least two compatible certified snapshots; meaningful persistence requires more.
- Basket price indexes or trip-level economics. No governed basket definition, weighting, or
  purchase data is present.
- KVI/KVC weighting. No governed item-importance model is present.
- Consumer price-image measurement. No survey, panel, or perception evidence is present.
- Elasticity, demand response, sales impact, margin, ROI, or profit-pool claims. No governed sales,
  cost, margin, or demand data is present.
- Promotion dependency. Sponsorship is observable; sponsorship is not promotion.

Unsupported frameworks may appear only as clearly labeled future capabilities or honest zero
states. They must not be estimated from the current snapshot.

## Metric definitions

- **Matched price observation**: one admissible comparison at the governed product × benchmark
  location × competitor context and selected comparison basis.
- **Retailer evidence coverage**: retailer scorecard views with reported matched evidence divided
  by configured retailer scorecard views in the current context.
- **Decision-ready retailer view**: a scorecard meeting its Product Pack minimum observations and
  geographies and the release-readiness rules.
- **Retailer-view leadership**: count of decision-ready retailer scorecards whose dominant outcome
  is Walmart lower versus competitor lower. Parity or mixed views remain visible separately; this
  is not a count of stores or products.
- **Price gap**: competitor comparison value minus Walmart comparison value at the atomic matched
  observation. A negative value means the competitor is lower.
- **Footprint price ladder**: ordered governed products within one match group, geography, time
  period, and comparison basis, summarized across the Walmart store footprint. It is not a
  category-wide sort of unrelated products or a single-store proxy for national position.

A Competitive Price Index may be added only with one prominently documented formula. The preferred
definition is `Walmart comparison value / competitor comparison value × 100`, where 100 is parity,
above 100 means Walmart is higher, and below 100 means Walmart is lower. The application does not
currently use CPI as an authoritative headline metric.

## Interaction integrity

- Competitive View and Comparison Basis must change every downstream metric and evidence view.
- An unavailable profile or product returns an explicit zero state; the API must not silently fall
  back while the UI continues to display the rejected selection.
- Product changes clear incompatible state/city filters.
- Sparse or unavailable evidence is labeled, never rendered as an unlabeled zero.
- Scorecard and cohort summaries drill into the governed products behind the metric.

## Release gates

1. Every visible headline number is already present in, or is a transparent aggregation of, the
   deterministic report contract.
2. Retailer scorecard counts reconcile to selected context and evidence state.
3. Product Leadership rejects unavailable explicit profile/product selections and never retains
   stale metrics after a context change.
4. The current one-snapshot history state does not imply a trend.
5. Unsupported basket, KVI, response, elasticity, margin, and price-image claims are absent.
6. Web tests, typecheck, lint, build, targeted API/analytics tests, and production browser checks
   pass before the phase is marked deployed.
