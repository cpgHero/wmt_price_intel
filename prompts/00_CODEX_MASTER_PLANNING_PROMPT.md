# Codex Master Planning Prompt

Do not implement anything yet.

You are the lead software architect for a brand-new standalone Retail Competitive Intelligence application that will be hosted on Railway. First read `README.md`, `AGENTS.md`, every file in `docs/`, the JSON Schemas, retailer catalog, Product Packs, database references, API fixtures, golden benchmarks, and example contracts.

Then inspect the empty/new repository environment and produce a concrete implementation plan.

## Required planning output

1. Proposed monorepo tree.
2. Exact runtime/package choices and versions you intend to pin (Next.js/TypeScript, FastAPI/Python, Polars/DuckDB, database migration framework, test tools).
3. Service boundaries for Railway: web, api, worker, scheduler, Postgres, bucket.
4. Database migration sequence based on `database/001_control_plane.sql`, with any justified changes.
5. JSON contract implementation approach shared across Python/TypeScript.
6. Durable Postgres queue implementation using `FOR UPDATE SKIP LOCKED`, leases, retries, cancellation, and idempotency.
7. Shared MetricsCart rate limiter/cooldown design that remains correct with multiple worker replicas.
8. Location import plan for `fixtures/location_master/locations.csv`, including leading-zero ZIP normalization and Target country filtering.
9. Retailer adapter plan for Walmart, ALDI, Amazon Same Day.
10. Raw object/Parquet storage layout and naming conventions.
11. Strawberry Product Pack runtime plan with no strawberry-specific branches in the core engine.
12. Golden-test plan and exact commands.
13. UI route/page plan.
14. Security/secret handling.
15. Railway deployment sequence.
16. Risks/questions that truly block implementation. Do not ask questions that can be resolved from the supplied package.

## Architectural acceptance test

After the strawberry vertical slice is complete, adding fresh shell eggs must be possible primarily through Product Pack configuration and generic capabilities. If your plan depends on product-category branches throughout core code, redesign it before implementation.

Return the plan only. Wait for approval before writing implementation code.
