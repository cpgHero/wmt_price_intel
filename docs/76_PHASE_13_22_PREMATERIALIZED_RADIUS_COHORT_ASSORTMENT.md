# Phase 13.22 — Pre-materialized Radius Cohort and Assortment Scorecards

Status: deployed and production-verified

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

The production Egg publication
`fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-80afd160` was
materialized into six documents: strict and compatible comparison profiles at 1, 3, and 5 miles.
The operation completed in 236.6 seconds with zero provider or AI calls.

Production reconciliation found:

- all six documents use schema `1.1.0` and contain all 13 configured competitor scorecards;
- compatible-spec retains 104 certified relationships and 41 Product Pack cohorts, with 7,597,
  13,596, and 16,846 scored product-locations at 1, 3, and 5 miles respectively;
- strict exact-spec retains four certified relationships and five cohorts, with 508, 519, and 531
  scored product-locations at 1, 3, and 5 miles respectively;
- Walmart-lower, competitor-lower, and parity rates reconcile to 100% for every scorecard with a
  scored denominator;
- cached in-service API reads completed in 2–25 milliseconds during the six-document verification;
- the live report shell returned HTTP 200, exposed Retailer, Cohort, and Assortment Scorecards, and
  contained no legacy `Exact ZIP` or `ZIP markets` wording; and
- production Postgres is at Alembic revision `0043_comp_portfolio_mat`, while the API and web are
  running commit `bf806dca12736bab6e7683f24b17a65dd2e6f9b9`.

GitHub Actions run `32405497085` passed 597 Python tests with 13 environment-gated skips, 66 web
and contract tests, 13 Playwright tests, reversible migrations, schema generation, formatting,
linting, type checks, production builds, and all four service container builds.
