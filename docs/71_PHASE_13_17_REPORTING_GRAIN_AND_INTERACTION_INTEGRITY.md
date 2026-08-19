# Phase 13.17 — Reporting Grain and Interaction Integrity

Status: implementation and release validation

## Outcome

This phase corrects trust and interaction defects found during owner review of Price Intelligence
and Competitive Intelligence. The work preserves immutable source evidence while changing read
models, labels, navigation, and payload shape where the previous presentation was slow or
ambiguous.

## Price Intelligence

- The API prepares one canonical product-location population per analysis and retailer, then
  reuses it for product, geography, and map projections. Product selection no longer reparses and
  reclassifies the complete Search evidence set on every view.
- Home contains one row per exact retailer product and removes the redundant Availability
  Evidence column. Observed and not-observed counts use distinct retailer location identity from
  the location master; ZIP is descriptive geography, not the store-counting grain.
- Product navigation exposes an explicit loading state. Full-map requests continue to use all
  available location points, while the prepared population removes redundant upstream work.
- PDP product media are available with identifiers and attributes. Search remains authoritative
  for price, observed presence, sponsorship, and collection time.
- Median Shelf Price includes the observed minimum-to-maximum range.
- Geographic Structure provides an explicit clear-geography action and changes its viewport from
  national to state or city bounds as the user drills down.

## Competitive geography

Two comparison generations remain explicit during migration:

1. Legacy publication scorecards and comparable-cohort records retain the immutable exact-ZIP
   geography used when those AnalysisResults were created. The UI labels them as legacy
   exact-ZIP evidence and does not present them as radius metrics.
2. Product Leadership uses one Walmart store as the counting grain. Physical competitor stores
   must fall within the selected 1-, 3-, or 5-mile radius. Service-area retailers, including
   Amazon Same Day, use same-ZIP delivery evidence because no competitor store point exists.

Portfolio and cohort read models will move to the shared radius correspondence only through a
governed replay. Existing stored ZIP results are never silently relabeled.

## Footprint price ladder

Product Leadership contract `1.2.0` replaces a full ladder repeated inside every store outcome
with one footprint-level ladder summary:

- one row per Walmart or governed competitor retailer product;
- median, minimum, and maximum Search comparison values across its eligible footprint;
- the number and share of Walmart stores at which the product was comparable;
- below, tied, and above Walmart counts at the benchmark-store grain;
- Walmart's median local rank and rank-one share across comparable stores.

At each Walmart store, a competitor product contributes at most one price: its lowest eligible
positive Search price inside the radius. This reduces response size materially and answers the
category price-architecture question without pretending one store represents the national
footprint. Store Comparisons remains the local evidence drill-down.

## Match governance navigation

Match Certification is the single active relationship-governance surface. Report and Product
Leadership links carry Product Pack, retailer, and product-pair context into Match Certification;
when the case is available, its evidence drawer opens directly. Retired Match Workbench routes
redirect to Match Certification, and the duplicate navigation entry is removed.

Relationship cards now distinguish:

- **global eligibility** — valid across observed Walmart stores under the selected basis;
- **governed benchmark-store scope** — valid only at explicitly admitted Walmart stores; and
- **used as lowest eligible offer** — stores where this relationship controlled the displayed
  outcome. A zero in the third measure does not mean the relationship is unapproved.

## Assortment and cohort presentation

- Assortment & Whitespace presents one benchmark-versus-competitor tab at a time.
- The redundant scope card and three-layer educational cards are removed.
- Comparable Cohort Explorer removes the oversized 1/2/3 cards and describes its current records
  as paired location observations and legacy exact-ZIP markets.
- Every cohort row identifies how many governed product pairs contribute and breaks those pairs
  down by governed benchmark and competitor brand type. New replays retain Product Pack brand
  governance in the assortment product index; unresolved evidence remains explicitly labeled.
- Included-product counts are labeled relationship pairs consistently between the scorecard
  button, drawer summary, and rendered cards.

## Trust gates

1. Observed and not-observed store counts reconcile by stable location key, not ZIP count.
2. Physical Product Leadership outcomes never exceed the chosen radius; service areas reconcile
   by exact ZIP.
3. Every Product Leadership outcome remains mutually exclusive and complete only after the API
   response passes independent certification.
4. Footprint ladder product-position counts reconcile to their comparison-location denominator.
5. No legacy exact-ZIP result is relabeled as a radius result.
6. Empty or failed requests remain explicit; the client does not merge partial payloads into a
   previously loaded view.
