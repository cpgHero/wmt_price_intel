# Phase 13.98 — Canonical report footprint-share labels

## Why this changed

The canonical product report already used source-backed exact-product store distribution, but some report labels still expressed distribution as a share of the searched rows returned by the map/drawer endpoint. For products with complete returned evidence but regional distribution, that could display as 100% and create the false impression of national footprint.

## Implemented behavior

- Executive Summary win/loss lists remain comprehensive and untruncated.
- Product Wins & Losses image cards remain comprehensive after filters are applied.
- Distribution & Assortment keeps every governed Walmart product footprint visible; broad distribution is a metric, not a hidden filter.
- Report-facing footprint labels show each product's observed positive-price store distribution as a share of that retailer's report footprint denominator.
- The report footprint denominator is the largest observed positive-price store footprint for the retailer in the current canonical report dataset.
- The denominator is not total chain stores, inventory, or a sampled returned-row count.
- Store-evidence drawers continue to expose row-level store details with CSV, Excel-compatible, and JSON downloads.
- Drawer JSON now includes `report_footprint_store_count`, `report_footprint_share`, and `searched_row_share` so business-facing footprint share and row-audit share are separately inspectable.

## Trust boundary

This is a presentation, UX, and export-metadata change only. It does not change source Search evidence, matching-v2 certification, report calculations, price normalization, seller rules, distribution definitions, provider collection, PDP calls, AI calls, report replay, PDF export, or historical artifacts.
