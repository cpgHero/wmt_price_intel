# Phase 13.81 — Verified Local Availability Boundary

Date: 2026-09-08
Status: implemented and locally validated; production deployment and governed report replay pending

## Decision

Search placement is not evidence of local carriage. A product-location observation is verified
locally available only when the provider explicitly reports `in_stock=true` and the Search result
explicitly reports `is_sponsored=false`.

Positive Search prices, sponsored placements, explicit out-of-stock results, missing stock flags,
missing sponsorship flags, and legacy observations remain usable as Search discovery and
Search-listed price evidence. They cannot contribute to verified availability, store or ZIP
distribution, local comparisons, price architecture, assortment breadth, competitive leadership,
or publishable report readiness.

## Defect and root cause

The prior Search adapter replaced the provider stock signal with `price > 0`. Because each result
inherited the requested Search task's store context, repeated sponsored or unavailable tiles could
be counted as distinct store distribution. Downstream projectors then reused that promoted value.
The defect was category-neutral and therefore potentially affected every product, not only the item
that exposed it.

## Corrected trust boundary

The canonical availability states are:

- `verified_in_stock`: `in_stock=true` and `is_sponsored=false`;
- `explicitly_out_of_stock`: `in_stock=false`;
- `unverified_sponsored`: sponsored Search exposure without explicit out-of-stock evidence; and
- `unverified`: missing or legacy stock/sponsorship evidence.

The provider adapter now preserves explicit stock booleans and leaves missing values null. Offer
identity includes observation time, stock, and sponsorship so a later state cannot be discarded as
a duplicate. Contradictory or malformed stock and sponsorship aliases are rejected rather than
resolved by field order. These evidence errors abort bulk normalization and historical replay rather
than dropping the newer row and leaving an older verified state behind. Same-timestamp organic
stock conflicts fail closed to out of stock and create a blocking quality check. For each exact
product-location, the projector selects the latest availability state before admitting price: a
newer out-of-stock, sponsored, unknown, price-less, or known-third-party row retracts an older
verified state. The latest PDP seller observation is likewise authoritative; a missing seller cannot
inherit an older first-party value. Only an eligible selected state may then enter the positive-price
Search projection. Matching v1/v2, assortment, Price Monitoring, price architecture, leadership,
report rendering, and the browser consume the same strict boundary.

## Contracts and presentation

- Price Observation is `1.2.0`.
- Price Monitoring View is `1.4.0`.
- Price Monitoring Map is `1.2.0`.
- Price Architecture Matrix is `1.2.0`.
- Competitive Product Leadership is `1.3.0`.
- Matching evidence-review prompt is `1.5.0`.

Search reach and Search-listed prices are reported separately from verified-local availability.
Product availability coverage divides verified locations by the full eligible local-query
population; a known-stock subset cannot make sponsored or unknown evidence look like 100%
carriage. Assortment product and brand cards require explicit verified counters and status. Brand
Workbench supports an explicit `verified_local_search_availability` mode and labels every legacy
Search or PDP-only mode unverified. Price Architecture suppresses verified-price values, ranges,
maps, and exception labels when verified location or price counts are absent; its verified and
Search retailer counters use the same active geography, brand-type, and brand filters. Aggregate and
row-level price contracts reject `$0.00` as evidence; a true zero price difference remains valid.
Legacy or contradictory presentation inputs fail closed, including shareable-report assortment
rollups and matching-footprint scope materialization. Current reports must carry a passed
`verified-local-availability` check and complete verified offer/location metrics for every scoreable
retailer.

## Quarantine

Public listings omit legacy availability contracts. Direct public analysis, report, artifact,
Price Monitoring, competitive-leadership, automation-history, global alert-event and email-delivery
feeds, alert-evaluation, and leadership-email paths enforce the same quarantine. Historical baseline
values in automation feeds must also come from a certified result in the same organization. Public
HTTP reads return 409 with
`legacy_availability_contract_quarantined`; pending or archived current reports return
`report_not_active`. Responses are non-cacheable. Only ready artifacts owned by the latest
certified publication can be enumerated or downloaded. Successful and failed availability-bearing
browser proxy responses are private and `no-store`; browser clients revalidate and exit any open
legacy view when a later quarantine returns 409. Internal materialization, collection-lineage,
review, and governed replay paths remain available so operators can diagnose and replace a
quarantined result; their internal
accessibility does not make their availability claims shareable. Stored read models are also
restricted to ready, unarchived owners. Direct browser routes render a clear quarantine explanation
rather than exposing an opaque HTTP 409 status.

The materialization finalizer revalidates current JSON contracts, staged checksums, and
cross-document availability totals before publication. Publication overlays cannot alter evidence,
scope, validation, or provenance. Predecessor archival is organization-scoped, and the Price
Architecture retailer population must reconcile to the full configured report scope. Governed
replay also binds the source collection organization to the certification queue organization.

## Item 46942839 validation

The audited Walmart milk Search source contains 83 rows for item `46942839`: 83 stores, 78 ZIPs,
and 59 cities. All rows join to the Walmart store master and all are in California. No row is in
Nevada or another state. All 83 stock fields are blank, and Seller and Buy Box Seller are blank.

The defensible result from this source is therefore 83 California Search observations and zero
verified-available locations. The previously displayed 4,510-location value is invalid as a
distribution claim. The full-source regression asserts all six facts directly.

## Regression evidence

- Repository Python suite: 1,023 passed and 31 environment-gated tests skipped.
- Web and generated contracts: 130 web tests and 1 contract test passed; TypeScript type checking
  passed.
- Full source goldens: 4 passed across 348,980 Milk rows, 168,440 Banana rows, and 386,889 Egg rows.
- Browser acceptance: all 17 Playwright tests passed against the production standalone build.
- Python formatting, Ruff, full mypy, JSON contract validation, Prettier, changed-file web ESLint,
  contract ESLint, and the Next.js production build passed.

The full filesystem-wide web ESLint scan remained unusually slow locally; every changed web file
passed ESLint directly. CI remains the authoritative full lint, migration, PostgreSQL, and
container gate.

## Production rollout

Deploy the exact accepted commit, wait for CI and all Railway services to become healthy, then
replay active governed reports sequentially from retained immutable source artifacts with
`force_rebuild=true`. Start with Milk. Replays use the current adapters and analytics and do not
require new provider or AI calls. Do not restore a category to public visibility unless the new
availability check passes and every scoreable retailer has positive verified offer evidence.

The retained August 7 Milk and Banana exports contain no explicit Walmart or ALDI stock signal.
Their zero-credit replays must therefore remain quarantined unless the production raw evidence
contains a valid explicit signal absent from those exports. A fresh paid collection is a separate
operation requiring provider-field preflight, an exact reviewed credit ceiling, and explicit owner
authorization; this correction does not authorize one.
