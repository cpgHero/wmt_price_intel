# Phase 13.87 - Canonical Report Dataset Contract

Date: 2026-09-09

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

Start Phase B by defining the governed data contract that the redesigned app report and later PDF/export must consume. This contract is intended to prevent future report surfaces from presenting similar facts with different meanings, stale definitions, or renderer-side recalculations.

## New contract files

- `schemas/canonical-report-dataset.schema.json`
- `examples/canonical-report-dataset.bananas.json`
- `packages/typescript/contracts/src/generated/canonical-report-dataset.ts`
- `apps/web/src/lib/canonical-report-dataset.ts`
- `apps/web/src/lib/canonical-report-dataset.test.ts`

Validator integration:

- `packages/python/rci-contracts/src/rci_contracts/validator.py`
- `packages/python/rci-contracts/tests/test_validator.py`
- `packages/typescript/contracts/scripts/generate-contracts.mjs`
- `packages/typescript/contracts/scripts/validate-handoff.mjs`
- `packages/typescript/contracts/src/index.ts`

## Contract purpose

The canonical report dataset is the single governed input for:

- app report tabs
- product win/loss cards
- distribution and assortment reporting
- price architecture summaries
- Evidence & QA
- PDF/export after the app experience is accepted

It is not a renderer. It must be produced by deterministic analytics/readiness services from retained evidence, Product Packs, Retailer Packs, matching certification, and materialized evidence references.

## Trust boundaries encoded

The contract directly encodes the following trust boundaries:

1. Product IDs remain strings.
2. Reportable comparison prices must be greater than zero.
3. Optional regular and discounted prices must be null when absent; zero sentinels are rejected.
4. Store distribution is positive-price store Search presence.
5. Store distribution makes no inventory claim.
6. Store distribution does not use stock status.
7. Store distribution does not use sponsorship status.
8. Store distribution is not extrapolated.
9. Service-area presence is separate and cannot be presented as stores.
10. Benchmark products in reportable relationships must be seller-qualified or not applicable.
11. Excluded relationships must carry reason codes.
12. Readiness blockers and warnings must be explicit.
13. `comparison.price_delta` has one sign convention: benchmark reporting price minus competitor reporting price. Negative means Walmart/benchmark is lower; positive means the competitor is lower.

## Initial schema shape

Top-level sections:

- identity and timestamps
- benchmark retailer and competitors
- Product Pack and Retailer Pack versions/checksums
- distribution and service-area contracts
- readiness
- seller governance
- price normalization
- summary
- product relationships
- excluded relationships
- QA

Product relationship sections:

- benchmark product
- competitor product
- comparison
- evidence references

Product sections:

- retailer ID
- retailer product ID
- title
- URL
- image URL
- brand
- brand type
- seller status
- package
- price
- distribution

## What this enables next

The redesigned app can now be built against one target object instead of stitching together:

- current report view
- competitive portfolio scorecards
- competitive product leadership
- price monitoring catalog
- price architecture matrix
- decision quality
- evidence exports

The first implementation may still adapt those existing sources behind the scenes, but the app should only care about the canonical report dataset shape.

## Validation performed

Completed:

- JSON syntax validation for the new schema.
- JSON syntax validation for the bananas example.
- Direct AJV validation of the bananas example against the new schema.
- TypeScript contract generation completed after validation-only dependency links were restored; the generated canonical report dataset type produced no additional diff.
- Direct AJV negative checks confirmed rejection of:
  - zero reporting price
  - zero discounted price sentinel
  - inventory claim in distribution contract
  - numeric benchmark retailer product ID
  - unqualified benchmark seller in a reportable relationship
- Targeted Python validator coverage passed with 18 tests.
- Adapter unit tests confirmed:
  - a fully evidenced product decision maps into a product win/loss relationship
  - a Walmart benchmark product with a non-Walmart seller is excluded
  - a zero/missing reportable price is excluded
  - a relationship with missing competitor distribution evidence is excluded
  - summary counts reconcile to included and excluded relationships
- Platform Docs unit tests passed after change-order updates.

Blocked or pending:

- Full Python pytest run has not been run for the entire repository; only targeted contract-validator tests were run.
- Full web TypeScript checking remains blocked by local dependency-linking/runtime duration in this worktree.

## Required next implementation step

Build a read-only app preview route or feature-flagged report shell that consumes the adapter output for the bananas pilot. The adapter should not change published report behavior until the generated dataset validates and reconciles to existing evidence.

Acceptance criteria for the adapter:

- Produces a canonical report dataset from the existing app report view.
- Validates against the schema.
- Reports only fully evidenced product win/loss relationships with product imagery when available.
- Routes invalid zero-price and seller-unqualified records to `excluded_relationships`.
- Reconciles summary counts to `product_relationships` plus `excluded_relationships`.
- Uses the positive-price store Search distribution contract.
- Makes no provider, AI, PDP, collection, publication, or data-deletion call.

Status:

- Initial read-only adapter implemented in `apps/web/src/lib/canonical-report-dataset.ts`.
- Adapter tightened so missing competitor distribution evidence routes to `excluded_relationships` instead of rendering as a zero-distribution buyer-facing relationship.
- Canonical `price_delta` and `price_delta_percent` sign conventions documented in the schema and TypeScript contract comments.
- Hidden app preview shell implemented in `apps/web/src/app/analyses/[analysisId]/canonical-report-workspace.tsx`.
- Preview gate implemented in `apps/web/src/lib/canonical-report-preview.ts`.
- The current report remains the default. Visit an analysis with `?experience=canonical`, `?experience=simplified`, `?reportExperience=canonical`, `?reportExperience=simplified`, `?canonical=1`, or `?canonical=true` to render the preview.
- Next work should compare the preview output against the current bananas report before replacing any active UI.
