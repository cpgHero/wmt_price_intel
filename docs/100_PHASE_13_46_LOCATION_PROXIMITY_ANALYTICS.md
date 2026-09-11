# Phase 13.46 — Location Proximity Analytics

Date: 2026-09-11

## Scope

Add a primary Analytics page named Proximity that explores store-network geography
from the authoritative location master. The first implementation fixes Walmart
US or Walmart CA as the benchmark and compares it against exactly one selected
competitor retailer.

## Evidence boundary

- Source authority is `retailer_location` rows that are `collection_eligible`
  and have non-null latitude and longitude.
- Distance is Haversine straight-line distance in miles.
- Proximity is not product assortment, observed product distribution, inventory,
  stock status, drive time, sales opportunity, or a provider Search result.
- The feature does not call MetricsCart, PDP, OpenAI, or any external map API.

## User experience

- Analytics navigation includes Proximity in both full and simplified navigation.
- The page provides country, competitor-retailer, radius, search, state, relation,
  and sort controls.
- KPI cards show Walmart mappable locations, competitor mappable locations,
  Walmart locations inside the selected radius, and median nearest distance.
- The map, side list, selected-pair drawer, table drawer, and CSV /
  Excel-compatible CSV / JSON downloads all use the same filtered row set.

## Validation expectations

- API tests cover Walmart-to-one-competitor pairing and same-retailer rejection.
- Navigation tests cover the new route in full and simplified navigation.
- Platform Docs document the page, source authority, and limitations.
