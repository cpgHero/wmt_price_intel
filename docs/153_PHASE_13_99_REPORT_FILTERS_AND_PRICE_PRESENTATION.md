# Phase 13.99 — Canonical Report Filters and Price Presentation

Date: 2026-09-10

Status: filter and price-label changes merged, CI-passed, and production-verified; image-card store-list actions implemented in follow-up code with CI, merge, and production verification pending.

## Purpose

The canonical report needs fast, source-backed filtering and clearer price presentation. A normalized comparison value such as `$/gallon` must not be presented as a shelf or package price unless the report dataset supplies package-price evidence.

## Implemented behavior

- Executive Summary shows one comprehensive action list at a time with a Losses / Wins toggle.
- Product Wins & Losses uses a filter drawer for source-backed relationship fields:
  - search text
  - outcome
  - Walmart brand
  - Walmart brand type
  - competitor retailer
  - competitor brand
  - Product Pack category
  - comparison basis
  - unit basis
  - price basis
  - Walmart footprint tier
  - sort
- Product Wins & Losses shows one comprehensive image-card section at a time through Losses / Wins / Parity controls.
- Each image card exposes Walmart and competitor store-list actions that open the exact-product evidence drawer with state filtering and CSV, Excel-compatible, and JSON downloads.
- Global subcategory and global state are not invented when absent from the canonical relationship dataset.
- Exact-product maps and store-evidence drawers expose a state filter after store rows are loaded from the product-scoped map API.
- Store-evidence JSON exports include the active `state_filter` and visible filtered row counts.
- Price tables and image cards distinguish source-backed package price from normalized comparison value. When package price is absent, the UI states that pack/shelf price is not supplied in the report dataset.

## Non-goals

This phase does not change source data, matching-v2 certification, report calculations, price normalization, seller rules, distribution definitions, provider collection, PDP calls, AI calls, report replay, PDF export, or historical artifacts.
