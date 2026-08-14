# Phase 12.6 — Interactive Local Price Maps and Unified Geography Context

## Outcome

Price Intelligence now uses an interactive vector basemap with streets, place names,
neighborhood context, pan, zoom, cluster expansion, and store-level selection. The map is
rendered with MapLibre GL JS `5.24.0` and the OpenFreeMap Liberty style. OpenFreeMap supplies
OpenStreetMap-derived tiles without an application API key; its required attribution remains
visible in the map.

## Filter ownership

The application top bar is the authoritative surface for retailer, product, and state scope.
The duplicated in-page product/state/city/ZIP filter row was removed. The Geography drawer has
an explicit **All states** option that also clears dependent city and ZIP filters.

City and ZIP are progressive map drill-downs rather than a second global filter surface. After
selecting a store, the inspector can scope the entire workspace to its state, city, or ZIP. The
top-bar Geography value reflects that scope and can always restore All states.

## Governed map analytics

The dedicated map response contract is `schemas/price-monitoring-map.schema.json` version
`1.1.0`. The API computes the following from the complete visible exact-product population before
any map sampling:

- stores below the visible-footprint median;
- stores at the visible-footprint median;
- stores above the visible-footprint median;
- observed and Search-not-observed location totals;
- mapped points, missing-coordinate counts, and sampling status.

The browser only renders those governed values. Search remains authoritative for store price and
positive-price observation. The retailer location master remains authoritative for store name,
state, city, ZIP, and coordinates. Search non-observation remains a review signal and is never
presented as proof of non-carriage.

## Interaction and performance

- Observed and not-observed points use separate clustered GeoJSON sources, so cluster counts never
  mix the two meanings.
- Clusters use a compact 26-pixel radius and stop clustering after zoom 8, exposing individual
  stores at metro-level zoom instead of requiring neighborhood-level zoom.
- Cluster selection zooms into local detail; individual store selection opens exact location and
  price evidence.
- Observed stores use below/at/above-median color classes and show exact price labels at local zoom.
- The Overview map retains the bounded, evenly distributed projection; Product Footprint retains
  the complete mapped set within the API safety cap.
- OpenFreeMap is currently a public external dependency without an SLA. A future high-availability
  deployment can self-host the same style and tiles without changing the analytical contract.

## Verification

```bash
.venv/bin/pytest apps/api/tests/test_price_monitoring.py -q
pnpm contracts:check
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web lint
pnpm --filter @rci/web test
pnpm --filter @rci/web build
pnpm --filter @rci/web test:e2e
```
