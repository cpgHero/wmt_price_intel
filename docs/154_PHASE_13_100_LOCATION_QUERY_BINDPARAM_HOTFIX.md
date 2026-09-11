# Phase 13.100 — Location Query Bind-Parameter Hotfix

## Status

Implemented in code; CI, merge, and production verification pending.

## Trigger

Production verification of the new Proximity analytics page found that the web proxy for `/api/proximity/retailers?country=USA` returned HTTP 500. API logs showed the upstream `/api/v1/retailers?country=USA` request failed in Postgres with a psycopg ambiguous-parameter error on the optional `country` predicate.

## Change

The Postgres location repository now declares SQLAlchemy bind-parameter types for optional string and integer parameters used by the location read queries:

- retailer list country filter;
- location search retailer, country, ZIP, search, limit, and offset filters.

## Non-goals

This hotfix does not change:

- source location rows;
- retailer eligibility;
- coordinates;
- proximity Haversine distance math;
- product Search evidence;
- observed product distribution;
- matching or certification;
- report price calculations;
- seller governance;
- provider collection;
- PDP or AI calls;
- PDFs or historical artifacts.

## Validation

Local validation:

- `ruff format packages/python/rci-locations/src/rci_locations/repository.py`
- `ruff check packages/python/rci-locations/src/rci_locations/repository.py`
- `pytest apps/api/tests/test_locations.py -q`

Production verification must re-run after deployment:

- `/api/proximity/retailers?country=USA` returns a retailer list.
- `/api/proximity?country=USA&competitor_retailer_id=<selected-retailer>&selected_radius_miles=10` returns Walmart benchmark rows paired to one selected competitor.
- `/proximity` renders the Proximity page.
