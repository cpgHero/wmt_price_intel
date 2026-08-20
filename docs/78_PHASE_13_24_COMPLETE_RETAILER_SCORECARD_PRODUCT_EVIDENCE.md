# Phase 13.24 — Complete Retailer Scorecard Product Evidence

Status: implementation and verification in progress

## Purpose

Make **View included products** on Retailer Scorecards represent every product in the governed
comparison, rather than only the Walmart side of each certified relationship.

## Read-model design

Competitive portfolio scorecards schema `1.2.0` adds an optional `product_relationships` collection
to each retailer scorecard. Every record retains both sides of one certified relationship:

- Walmart product ID, name, and image;
- competitor product ID, name, image, brand, and brand type;
- comparison profile, metric, unit, and location-scope metadata; and
- the product-location outcomes where that exact relationship supplied the selected lowest eligible
  competitor evidence.

The existing Walmart-only `products` collection remains for Cohort Scorecards and compatibility
with stored schema `1.1.0` documents. It is no longer the evidence source for the Retailer
Scorecards drawer. Stored `1.1.0` portfolio documents are rebuilt on first read instead of being
served with incomplete evidence.

## User experience

The scorecard action reports the distinct included-product count across both retailers. The drawer
uses one compact paired row per certified relationship, with Walmart on the left and the selected
competitor on the right. Search covers both names and IDs plus competitor brand. Images remain
bounded, names wrap, and one-to-many regional relationships remain explicit rather than being
flattened into an ambiguous product list.

The aggregate scorecard still selects the lowest eligible certified competitor product for each
observed Walmart product-store. A certified relationship can therefore have zero selected local
observations when another eligible competitor product was cheaper throughout the active context;
the drawer labels that state rather than implying the product was excluded.

## Authority boundary

This phase changes an additive reporting read model and its presentation only. It does not change
matching, certification, retailer eligibility, price authority, distance calculation, comparison
basis, denominators, price-position rates, immutable evidence, or audit lineage.

## Cost and lifecycle

- No MetricsCart or OpenAI calls are required.
- Existing publications, Search/PDP evidence, certification history, and audit records remain
  intact.
- Current portfolio materializations are regenerated from retained certified product-location
  evidence after deployment.

## Verification plan

- Contract validation for both legacy `1.1.0` and additive `1.2.0` documents.
- API regression proving all certified relationships retain both retailer product identities,
  including a relationship that contributes zero selected local outcomes.
- Web type, unit, lint, format, build, and browser suites.
- Production Egg walkthrough proving the action count includes both retailer assortments, paired
  identities render without overflow, and search finds a competitor product.
