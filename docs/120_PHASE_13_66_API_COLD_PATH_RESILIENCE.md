# Phase 13.66 — API Cold-Path Resilience

Date: 2026-08-27  
Status: Deployed and production availability-verified

## Incident

Price Intelligence displayed “The API is not currently reachable from the web service.” Railway still showed the API container as running, but both the web container’s private-network request and a localhost API readiness request timed out. Replacing the API instance restored readiness, proving that process state alone was not a sufficient health signal.

## Root cause

A cold, large Price Intelligence request performed CPU-heavy offer normalization, canonical product-location population construction, view projection, and contract validation on FastAPI’s event-loop thread. During that work, the single API process could not serve readiness checks or unrelated lightweight analysis reads. The application therefore presented a real dependency outage even though the container had not exited.

## Remediation

- Run classified-offer normalization outside the API event loop.
- Run canonical product-location population construction outside the API event loop.
- Run Price Intelligence catalog projection and contract validation outside the API event loop.
- Apply the same protection to full evidence-export and map projections.
- Coalesce concurrent requests for the same cold catalog into one shared build.
- Shield that build from a browser or web timeout so it can finish and populate the cache for the next request.
- Convert decoded Parquet frames to Python records outside the API event loop.
- Retain existing deterministic formulas, source authority, schema validation, and in-process caches.
- Add a regression test that holds a projection open, proves an independent event-loop heartbeat remains responsive, cancels the initiating request, and confirms the next request joins the same surviving build.

## Operational response

When web `/health/ready` reports `api: unavailable`:

1. Test API readiness from the web service over `RCI_API_INTERNAL_URL` without printing the private URL.
2. Test API readiness on API localhost.
3. If both time out while Railway reports the process running, replace the API instance and verify readiness before accepting user traffic.
4. Exercise a cold large Price Intelligence catalog while repeatedly checking readiness. A running container is not acceptance evidence.

## Governance

This change affects execution scheduling only. It does not alter Search or PDP evidence, product scope, price calculations, first-party governance, match certification, report metrics, source artifacts, or audit history.

## Production verification

- Thirteen targeted API tests passed, including event-loop responsiveness and disconnected-caller single-flight coverage.
- GitHub Actions run `33130172564` passed Python, TypeScript, contract, migration, browser, production-build, and all four container gates.
- Railway web deployment `f2ea0b54-f878-4f31-b658-ceeb75dc3e04` and API deployment `f7b28b84-0ee5-49ab-89db-cbb84c36f3d8` succeeded.
- Web `/health/ready` remained HTTP 200 for every poll during concurrent cold Milk catalog requests, generally in 0.20–0.24 seconds.
- After the shared build populated the cache, three complete Milk catalog requests returned in 0.46–0.78 seconds.
- A live Chrome validation rendered all 649 products, filters, price/unit-price evidence, observed/not-observed store counts, and seller evidence with no console warnings or errors. The first product workspace opened successfully with its exact-product footprint.

## Remaining performance boundary

The largest catalog can still exceed the web request timeout when it must be rebuilt from raw retained evidence after an API deployment. The shared build now survives that timeout, does not make the API unavailable, and serves subsequent requests quickly, but the first caller can still see a temporary unavailable state. Phase 13.67 should persist the compact catalog during publication so no end-user request owns that cold computation.
