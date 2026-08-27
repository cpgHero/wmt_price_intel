# Phase 13.62 — Vitamin Reporting Decision-Quality Certification

Status: implemented and locally certified; production deployment pending

Date: 2026-08-26

## Objective

Turn every retailer × comparison basis × radius view into an explicit governed
decision context, then block publication when identities, evidence funnels,
price bases, rollups, or radius behavior drift even when headline counts still
appear plausible.

This phase uses retained reporting evidence only. It does not collect Search or
PDP data, call an AI model, change a match certification, or delete a report.

## Governed context matrix

The Vitamin publication has:

- nine competitor retailers;
- two comparison bases: Exact Specification and Compatible Specification; and
- three physical-store radii: 1, 3, and 5 miles.

That creates 54 mandatory decision contexts. Each context is classified as one
of three mutually exclusive states:

1. `scored` — at least one selected-basis product has local price evidence;
2. `local_evidence_limited` — certified selected-basis relationships exist, but
   none has scorable local evidence at the selected radius; or
3. `no_selected_basis_relationship` — no certified relationship qualifies for
   the selected price basis.

An explicit zero is therefore distinguishable from missing report data.

## New publication gates

The semantic audit now fails closed when any of the following occurs:

- the 54-context matrix is incomplete or retailer scope differs by basis/radius;
- product or relationship IDs are empty, duplicated, orphaned, replaced across
  radii, or assigned to the wrong retailer/comparison basis;
- product scored outcomes do not equal their relationship lineage;
- a funnel disposition does not equal its exact preceding-stage subtraction;
- selected-basis product counts differ from the included product identities;
- locally scored counts differ from products with scored location evidence;
- source catalog, governed scope, or benchmark observation denominators drift
  by retailer, basis, or radius;
- certified identity products drift by comparison basis or radius;
- one comparison basis mixes package and normalized-unit metrics;
- selected identities change when only radius changes; or
- a wider radius loses scored products/evidence or creates additional local
  evidence gaps.

Existing schema, status-partition, denominator, rate, weighted-gap, cohort,
assortment, ordering, and geography gates remain active.

## Runtime visibility

- Public API: `GET /api/v1/analyses/{analysis_id}/competitive-decision-quality`
  returns the complete audited context matrix.
- The Competitive Intelligence top-bar Decision Readiness drawer evaluates the
  current retailer, basis, and radius instead of showing one generic report
  status.
- Report Publishing administration displays matrix completeness, state totals,
  and the per-context certified, eligible, locally scored, and scored-location
  counts stored with future publication jobs.

## Vitamin acceptance result

The six retained Vitamin Competitive Portfolio documents validate against the
new contract:

- 54 of 54 required contexts present;
- 28 scored contexts;
- 17 local-evidence-limited contexts;
- nine contexts with no selected-basis relationship;
- zero blocking semantic errors; and
- 65 explicit nonblocking warnings covering incomplete cohort attributes,
  certified relationships without local scored evidence, or retailers with no
  certified relationship under that basis.

All 478 Compatible Specification relationship rows use `price_per_item` in
`USD/item`. All 48 Exact Specification relationship rows use `package_price` in
`USD/package`. Exact relationship identities are a subset of Compatible
Specification identities at every radius.

## Verification required before completion

- focused audit, portfolio, API, and UI tests;
- generated-contract and schema checks;
- full Python and web test/static/build gates;
- Railway deployment and public endpoint verification;
- visual verification of context-aware Decision Readiness; and
- rematerialization or governed publication-job audit refresh using retained
  data only.

No provider or AI spend is authorized or required for this phase.
