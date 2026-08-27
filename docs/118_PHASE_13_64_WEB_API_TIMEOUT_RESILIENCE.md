# Phase 13.64 — Web/API Timeout Resilience

Status: production incident remediated and verified

Date: 2026-08-27

## Incident

The primary application displayed `API unavailable` even though the Railway API
container, database dependency, and requested endpoints remained healthy.

## Root cause

The web server allowed only five seconds for every internal API GET. Production
logs showed valid analytical requests occasionally completing after roughly
seven seconds during cold or concurrent loads. The web layer canceled those
requests and incorrectly presented the timeout as API unreachability.

## Correction

Server-side API reads remain bounded but now allow 20 seconds. This covers the
observed healthy production latency without permitting an indefinite request.
The API, database, source evidence, calculations, reports, and publication
state are unchanged.

## Live evidence

- Web health returned HTTP 200 with API dependency `ok`.
- The Competitive Intelligence library returned all six active reports.
- Ten internal `analyses?limit=200` requests returned HTTP 200 in 89–168 ms
  after the cache was warm.
- API logs showed continued HTTP 200 responses for analyses, reports,
  scorecards, decision-quality, price-monitoring, collection, and matching
  endpoints during the reported incident.
- No provider or AI call was made.
