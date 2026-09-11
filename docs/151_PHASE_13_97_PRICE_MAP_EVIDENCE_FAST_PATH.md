# Phase 13.97 — Price Map Evidence Fast Path

Date: 2026-09-10

## Status

Merged, CI-passed, and production-verified.

## Context

The canonical report now restores comprehensive product win/loss lists and
store-evidence drawers with CSV, Excel-compatible, and JSON downloads. Production
verification showed that the map/detail API could time out even for a summary
request because the endpoint still rebuilt the full retailer price-monitoring
catalog before answering one exact-product map request.

That latency made the restored evidence drawer unreliable as a user-facing trust
surface. The drawer must be able to expose the number and percentage of searched
stores where the product was observed, plus the searched-but-not-observed store
rows that support the denominator.

## Change

`PriceMonitoringService.map_view` now answers an exact-product map request from:

1. selected positive-price Search observations for the requested retailer product;
2. the eligible searched-location set for the same analysis and retailer.

It no longer invokes full retailer catalog preparation for this path. The
response contract remains the same:

- observed distribution store rows;
- searched-but-not-observed location rows;
- distribution-store count;
- service-area presence count;
- searched-store denominator inputs;
- map sampling metadata;
- distribution contract stating this is not an inventory or in-stock claim.

The map cache key was bumped from `map-v3` to `map-v4` so newly deployed API
processes do not reuse stale map responses from the old path.

## Validation

Local validation completed:

- `.venv/bin/ruff format --check apps/api/src/rci_api/price_monitoring.py apps/api/tests/test_price_monitoring.py`
- `.venv/bin/ruff check apps/api/src/rci_api/price_monitoring.py apps/api/tests/test_price_monitoring.py`
- `.venv/bin/pytest apps/api/tests/test_price_monitoring.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache-price-report /Users/ugp/Library/Python/3.11/bin/uv run mypy apps packages`
- `git diff --check`

The API regression test proves the map endpoint:

- returns observed exact-product store rows;
- returns searched-but-not-observed location rows for drawer/export denominators;
- does not include `in_stock` or `availability_status` in map points;
- does not call the full `_prepare` catalog path.

## Non-goals

This does not change collection, matching, price normalization, seller rules,
report calculations, PDF export, provider calls, PDP calls, AI calls, or
historical artifacts.
