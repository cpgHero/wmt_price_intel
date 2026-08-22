# Phase 13.37 — ALDI Updated-Roster Regional Preflight

## Outcome

The owner-approved five-store ALDI Strawberry Search preflight completed in production on
2026-08-22 after the current MetricsCart ALDI roster was imported. One Florida store returned HTTP
200 with 14 contract-valid results. The California, Illinois, Ohio, and Pennsylvania stores returned
the same nonretryable billable HTTP 404 unavailable-page response seen in the earlier regional
diagnostics.

The updated roster therefore supplies one newly proven callable store, but it does not establish
broad regional ALDI Search coverage and does not justify a multi-retailer or all-location replay.
Roster `active` status remains a location-dimension fact, not provider-callability evidence.

## Approved and executed scope

- Run ID: `c0f76364-3380-45b7-95cc-60b0a908cf31`
- Definition version ID: `0202f837-a60b-4fee-adff-0ca67b3dc830`
- Geography resolution ID: `c1e927ae-7a99-45aa-be23-2cda4f9543d4`
- Geography checksum: `f69c9d837d0c5169166ccea437e26958cc579908fa2219f6f21ce32f9c554504`
- Scope-estimate ID: `2b9c6119-5f76-461a-9e47-8e5e6824e4ba`
- Configuration checksum: `18683361cbd1dff02ecd5b7fbbd5478a5466c55bbce049aa0ccd9f34c7972b1e`
- Product Pack: Fresh Strawberries `1.0.1`
- Endpoint: `GET /mc/new_aldi/serp/zipcode`
- Request parameters: `keyword`, `page`, `store`, and `zipcode`
- Pages: one per store
- Retailers called: ALDI only
- PDP enrichment and AI: disabled
- Approved and actual hard cap: 10 Search credits, approximately `$0.02`
- Retries and HTTP 429 responses: zero

The geography snapshot contains exactly five ALDI primary stores and zero competitor locations.
Amazon Same Day was named only to satisfy the current geography-resolution contract and every
generated Amazon ZIP scope was explicitly excluded before the estimate. No Walmart, Amazon, PDP,
or AI request was planned or issued.

## Provider results

| State | Store | ZIP | HTTP | Result | Credits |
| --- | --- | --- | ---: | --- | ---: |
| California | `479-001` | `92399` | 404 | Requested URL or store unavailable | 2 |
| Florida | `482-033` | `32548` | 200 | 14 contract-valid results | 2 |
| Illinois | `464-033` | `60073` | 404 | Requested URL or store unavailable | 2 |
| Ohio | `461-019` | `45013` | 404 | Requested URL or store unavailable | 2 |
| Pennsylvania | `469-051` | `15301` | 404 | Requested URL or store unavailable | 2 |
| **Total** |  |  |  | **1 success / 4 failures** | **10** |

All five requests completed on their first and only provider attempt. The run status is
`completed_with_warnings`: one successful page, four failed pages, and ten actual credits. The
availability gate's configured `1.0` ceiling allowed the diagnostic-only run to reach a terminal
state after observing every approved sample; that mechanical gate status is not a regional
acceptance verdict.

## Raw and contract verification

- Every compressed raw-object SHA-256 matches its `dataset_artifact.checksum`.
- Every decompressed body SHA-256 matches the artifact metadata `body_checksum`.
- Every compressed byte size matches the recorded artifact byte size.
- The four 404 bodies are byte-identical JSON containing
  `{"error":"Page not found","message":"Requested URL or Store is not available on the website"}`.
- The Florida 200 body has top-level `query` and `results` keys and 14 result objects.
- The successful page passed Search contract `1.0.0`, result path `results`, the shared 31-field
  ALDI inventory, positive Search price availability authority, and `is_sponsored` sponsorship
  authority.
- No schema drift, retry, rate limit, or provider 5xx response occurred.

This was intentionally an ALDI-only provider diagnostic, not a competitive analysis. After Search
completion, the generic downstream analysis job exhausted its three bounded attempts because an
`AnalysisResult` requires non-empty competitors, comparison modes, and comparisons. It produced no
user-facing report and remains in audit history rather than being misrepresented as an analytical
failure or deleted.

## Decision

- Keep the ALDI Search adapter and request shape unchanged; the Florida 200 proves the deployed
  contract works.
- Do not interpret the 80% 404 rate as a malformed response or silently empty assortment.
- Do not expand to all ALDI locations or replay the five-region competitive collection. The current
  roster is not a callability catalog.
- Record `482-033` / `32548` as a newly verified positive regional control and retain the prior
  `463-048` / `44906` Ohio positive control.
- Escalate the preserved 404 request/response evidence and store list to MetricsCart, or obtain a
  provider-supported callability mapping, before spending on another broad ALDI sample.
- Any additional paid diagnostic requires a new exact scope and approval.
