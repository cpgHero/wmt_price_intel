# Phase 13.80 — Canonical Retailer Publication Scope

Date: 2026-08-30
Status: Production-complete and verified

## Outcome

Report publication now builds Price Intelligence catalog work from canonical governed retailer IDs rather than human-readable report labels. A label such as `ALDI` is presentation only; the deterministic Price Intelligence service is keyed by `aldi_us`.

The correction is live in production. The retried Banana publication and the independently completed Milk publication both passed their complete semantic gates, activated their replacement results, and recoverably archived their predecessors.

## Incident and cause

The governed Banana composite analysis completed successfully, but its durable publication job blocked after three attempts while staging retailer catalogs. Production logs showed the exact failure:

`ValueError: retailer 'ALDI' is not in this analysis`

The publication planner had read `benchmark_retailer` and `competitors` from the rendered report view. Those fields intentionally contain display labels. The same view already exposes canonical IDs under `retailer_scope`, but the planner did not use them.

## Correction

- Read the benchmark and competitor service keys only from `retailer_scope`.
- Fail closed if the canonical benchmark, competitor list, or any canonical competitor ID is missing.
- When a governed report exposes `scoreable_retailers`, stage catalogs only for those competitors plus the benchmark.
- Reject a scoreable ID that is not present in the configured canonical competitor scope.
- Preserve display labels for presentation only.
- Preserve explicitly unavailable competitors in audit provenance without generating a misleading catalog or scorecard.

## Trust and compatibility

This change does not alter Search or PDP evidence, collection tasks, AI behavior, certification, Product Packs, prices, metrics, comparison relationships, or geographic rules. Each prior trusted result remained current until its replacement passed the complete semantic publication gate; activation and predecessor archival then completed atomically and recoverably.

## Verification

- Eight canonical-scope unit cases pass, including display-label separation, unavailable-retailer exclusion, missing-scope rejection, and unconfigured-scoreable rejection.
- Twenty-six focused API Price Intelligence, report-publication, and worker materialization tests pass.
- Code commit `8e621bef9082ec773821e213d34cabf0592006f0` passed the complete GitHub Actions release gate in run `33340858383`.
- Railway API deployment `1fd29c75-2e57-48c9-a452-388d5bdb34fc` completed successfully and passed live and ready health checks.
- Banana publication job `8d6c4756-c44f-487e-9a6a-393dc1661b96` succeeded through 25 of 25 stages. Its semantic audit passed with zero errors and 39 nonblocking warnings. Replacement result `d148c963-d080-4164-9d1c-d1f23233786d` is ready; predecessor `c148b5fe-014b-4232-b064-1647c8362d4c` was recoverably archived at 2026-08-30 23:15 UTC.
- Milk publication job `9f0bb4d2-d743-4939-aaa5-b1b98b7d4271` succeeded through 16 of 16 stages. Its semantic audit passed with zero errors and nine nonblocking warnings. Replacement result `a12a43c6-f7d3-4a1d-a4fe-de656e75a0d0` is ready; predecessor `8294aa48-1e80-4454-ac54-7c58d53c8a55` was recoverably archived at 2026-08-30 23:09 UTC.
- Live browser acceptance was clean after activation.
- Publication and retry reused retained evidence. They made no provider or AI call and consumed no paid credit.
