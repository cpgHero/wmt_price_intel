# Phase 13.62 — Vitamin Reporting Decision-Quality Certification

Status: deployed, rematerialized, and production-verified

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

## Verification

- 777 Python tests pass; 16 environment- or fixture-dependent tests skip with
  their documented prerequisites.
- 21 focused release-audit and portfolio service tests pass.
- 73 web unit tests and all 15 Playwright acceptance tests pass.
- Contracts, formatting, Ruff, ESLint, TypeScript, mypy across 151 Python source
  files, migrations, production builds, and all four container builds pass.
- GitHub Actions run `33035290829` passes for commit `9be8a04`.
- Railway deployments are web `533cb00c-b8db-40da-978e-da4146f61918`, API
  `d12d7642-45c2-4539-817b-da7dbb1c8d02`, worker
  `50ad6ef2-9868-4d89-a156-e910e1726096`, and scheduler
  `faad40a2-4dfd-4aa3-8e03-14ba67ef01f4`.
- Production rematerialized all six portfolio documents from retained evidence
  and reported `provider_calls_queued: 0`.
- The public decision-quality endpoint returns a passing 54-of-54 matrix with
  the expected 28/17/9 state partition.
- Browser acceptance verified all three visible states: `Local price evidence
  ready`, `Local evidence limited`, and `No eligible relationship`. The latter
  explicitly explains that the zero is governed rather than missing data.

No provider or AI call was made and no match, source evidence, or historical
report was changed or deleted.
