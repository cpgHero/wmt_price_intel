# Phase 13.22 — Pre-materialized Radius Cohort and Assortment Scorecards

Status: implemented; production verification pending

## Purpose

Complete the radius-native reporting conversion without relabeling historical exact-ZIP
aggregates. Cohort Scorecards and the local-comparison portion of Assortment Scorecards now consume
the same certified product-location outcomes as Retailer Scorecards.

## Authoritative grain

For a physical competitor, the engine begins with each positive-price Walmart product-store
observation, retains only certified relationships under the selected comparison basis, and selects
eligible competitor evidence within 1, 3, or 5 miles. A service-area retailer uses the same delivery
ZIP because no comparable physical store footprint exists.

The API aggregates these atomic outcomes into:

- retailer scorecards;
- Product Pack cohorts;
- assortment local-comparison coverage; and
- contributing benchmark-product summaries.

The browser formats these metrics but does not calculate them.

## Cohort behavior

Product Pack segment attributes assign certified relationships to cohorts. Relationships remain
one-to-one; cohort membership does not create new matches. Every cohort exposes its observed
benchmark product-location denominator, locally scored product-locations, mutually exclusive
Walmart-lower/competitor-lower/parity rates, medians, paired median gap, relationships, products,
and explicit active radius.

## Assortment behavior

Global distinct-product, admitted-relationship, unmatched-product, whitespace, and brand evidence
remain assortment facts. The selected radius changes the locally comparable product-location
coverage; it does not rewrite global category breadth. Scorecard metrics open bounded product
evidence drawers. Product and brand breadth still originate in governed Search evidence, with PDP
used only for descriptive enrichment.

## Durable read model

Migration `0043_competitive_portfolio_materialization` stores one JSON document per immutable
analysis result, comparison profile, and radius. Each document contains all configured competitors,
allowing retailer selection without rebuilding the portfolio. Publication builds profile/radius
documents sequentially because product projections already use bounded concurrency. The operation
is idempotent and makes no provider or AI calls. State and city filters remain on-demand because the
combination space is unbounded.

## Failure and lifecycle rules

- The immutable AnalysisResult remains publishable if derivative materialization fails.
- A missing read model may be rebuilt from persisted Search evidence and certification history.
- No paid MetricsCart or OpenAI call is part of materialization.
- A zero relationship, no local overlap, unscored evidence, and a measured zero remain distinct.
- Obsolete reports may be recoverably archived only after replacement validation. Raw Search/PDP,
  normalized evidence, certification decisions, releases, and audit lineage are never deleted.

## Verification

Contract, API aggregation, migration, TypeScript, UI, and production reconciliation evidence will be
recorded here before the status changes to deployed and production-verified.
