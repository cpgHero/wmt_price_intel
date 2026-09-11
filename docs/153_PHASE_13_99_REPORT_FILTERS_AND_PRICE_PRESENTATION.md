# Phase 13.99 — Canonical Report Filters and Price Presentation

Date: 2026-09-10

Status: filter and price-label changes merged, CI-passed, and production-verified; image-card store-list actions merged, CI-passed, and production-verified; compact report-level state filter merged, CI-passed, deployed, and production-verified after direct state-index optimization; image-card pagination merged, CI-passed, deployed, and production-verified; package-equivalent price display merged, CI-passed, deployed, and production-verified after the follow-up package-fact projection fix; executive action-board upgrade implemented and awaiting CI/deployment.

## Purpose

The canonical report needs fast, source-backed filtering and clearer price presentation. A normalized comparison value such as `$/gallon` must not be presented as a shelf or package price unless the report dataset supplies package-price evidence.

## Implemented behavior

- Executive Summary shows one comprehensive action list at a time with a Losses / Wins toggle.
- Executive Summary uses the same source-backed filter drawer, quick search, state coverage, and comprehensive paginated image-card board as Product Wins & Losses, so the VP-facing landing view no longer falls back to table-only relationship rows.
- Executive Summary image cards expose product IDs plus direct Walmart and competitor map links and store-list drawer actions for every visible relationship.
- Product Wins & Losses uses a filter drawer for source-backed relationship fields:
  - search text
  - outcome
  - Walmart brand
  - Walmart brand type
  - competitor retailer
  - competitor brand
  - Product Pack category
  - comparison basis
  - state distribution footprint
  - unit basis
  - price basis
  - Walmart footprint tier
  - sort
- Product Wins & Losses shows one comprehensive image-card section at a time through Losses / Wins / Parity controls.
- Product Wins & Losses paginates the active comprehensive image-card set so the browser renders a bounded number of cards while keeping every governed relationship accessible through page controls, filters, and quick search.
- Each image card exposes Walmart and competitor map links plus store-list actions that open the exact-product evidence drawer with state filtering and CSV, Excel-compatible, and JSON downloads.
- The report-level State filter uses compact source-backed product state coverage derived from exact-product positive-price Search observations. Selecting a state keeps relationships where either product has observed store distribution in that state; it does not make the displayed price gap state-specific.
- The state coverage read path must remain fast enough for large product-level reports. It should scan only the raw Search fields needed for exact-product store-state membership, positive package-price eligibility, latest product-location selection, and seller-policy retractions; it must not invoke the full price-monitoring product projector just to populate report filter options.
- Global subcategory is not invented when absent from the canonical relationship dataset.
- Exact-product maps and store-evidence drawers expose a state filter after store rows are loaded from the product-scoped map API.
- Store-evidence JSON exports include the active `state_filter` and visible filtered row counts.
- Price tables and image cards distinguish source-backed package price from normalized comparison value. When package price is absent, the UI states that pack/shelf price is not supplied in the report dataset.
- When source package price is absent but a governed fluid package size and gallon-normalized value are available, price tables and image cards display a package-equivalent primary value and move the gallon-normalized value into secondary audit context.
- The canonical report dataset preserves explicit package measures from governed Matching v2 `match_attributes`, including `volume_oz` as a fluid-ounce package quantity, so the package-equivalent display uses source-backed package facts rather than product-title inference.
- Production smoke testing on Fresh Fluid Milk verified Organic Valley 10849883 renders `Package-equivalent $6.26` with normalized `$12.52/gallon` only in secondary context, and Horizon Organic 19857008 renders `Package-equivalent $6.46` with normalized `$12.92/gallon` only in secondary context.

## Non-goals

This phase does not change source data, matching-v2 certification, report calculations, price normalization, seller rules, distribution definitions, provider collection, PDP calls, AI calls, report replay, PDF export, or historical artifacts.
