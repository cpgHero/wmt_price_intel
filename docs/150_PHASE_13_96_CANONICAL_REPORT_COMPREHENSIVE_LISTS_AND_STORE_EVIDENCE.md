# Phase 13.96 — Canonical report comprehensive lists and store evidence

## Intent

The simplified canonical report must not simplify away the product-level evidence that makes the report trustworthy. Executive and supporting tabs should expose every governed win/loss relationship, not a curated subset, and should keep distribution evidence close to the product rows that drive action.

## Implemented behavior

- Executive Summary renders complete Walmart-loss and Walmart-win action lists.
- Price Architecture brand-role sections render all governed relationships in the slice instead of truncating rows.
- Product cards and relationship tables display positive-price store footprints with searched-store percentages when a searched-store denominator is available.
- Store evidence drawers are available from executive rows, price rows, and distribution product footprints.
- Drawers load full price-monitoring map evidence for the exact retailer product ID, list positive-price store-level Search observations, calculate searched-store share from observed distribution stores plus searched-not-observed store locations, and expose CSV, Excel-compatible, and JSON downloads.
- Drawer downloads include observed distribution rows and searched-not-observed store rows so the store-count numerator, searched-store denominator, and percentage are auditable outside the app.
- Service-area presence remains separately labeled and is never included as a store count.

## Non-goals

This change does not change source data, matching-v2 certification, report calculations, price normalization, seller rules, distribution definitions, provider collection, PDP calls, AI calls, report replay, PDF export, or historical artifacts.
