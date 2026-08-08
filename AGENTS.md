# AGENTS.md - Rules for Codex

## Product boundary

This is a standalone retailer competitive-intelligence product. Do not import CPGHero application assumptions unless explicitly provided later. Walmart is the initial benchmark retailer, but the core engine must support other benchmark retailers in the future.

## Architectural invariants

- NEVER add `if product_type == "strawberries"` (or eggs/milk/bananas) inside generic collection, normalization, matching, analytics, reporting, or orchestration logic. Category behavior belongs in Product Packs or generic capability modules.
- NEVER put MetricsCart-specific request logic in the analysis engine. It belongs in Retailer Adapters/provider clients.
- NEVER let an LLM compute authoritative counts, prices, medians, win rates, distances, unit conversions, match eligibility, or denominators.
- NEVER let report/email renderers recalculate analytics. They only consume `AnalysisResult` plus evidence references.
- NEVER coerce store IDs, retailer product IDs, ASINs, product IDs, ZIPs, or provider location IDs to integers.
- NEVER expose `METRICSCART_API_KEY`, `OPENAI_API_KEY`, database credentials, or bucket credentials in client code, logs, artifacts, or prompts.
- NEVER mutate raw snapshots after successful collection. Corrections create a new artifact/version.
- NEVER merge analytical logic that changes golden metrics without an explicit benchmark update and documented rationale.

## V1 technology constraints

- Frontend: Next.js + TypeScript.
- Backend/control API: FastAPI + Python.
- Analytical worker: Python using Polars and DuckDB where useful.
- Database/control plane: PostgreSQL.
- Durable collection queue: PostgreSQL rows claimed with `FOR UPDATE SKIP LOCKED`.
- Blob/data storage: S3-compatible Railway Bucket; Parquet preferred for normalized analytical datasets.
- Redis is NOT required for V1. Add only if measured throughput/latency warrants it.
- Deployment: Railway services from one monorepo.

## Data contracts

Treat these as normative:
- `schemas/product-pack.schema.json`
- `schemas/collection-definition.schema.json`
- `schemas/normalized-offer.schema.json`
- `schemas/provider-error.schema.json`
- `schemas/analysis-result.schema.json`
- `schemas/golden-benchmarks.schema.json` (test-fixture contract)

If implementation needs a contract change, update schema, examples, migrations, docs, and tests together.

## Test gates

1. Contract/schema tests.
2. Retailer response-normalization fixtures.
3. Location normalization tests (leading-zero ZIPs, leading-zero store IDs, country filtering).
4. Queue concurrency tests with multiple workers.
5. Global MetricsCart rate-limit tests across simulated worker replicas.
6. 429 shared cooldown tests.
7. Product Pack classification/matching tests.
8. Strawberry compact fixture tests.
9. Full strawberry golden regression when full source datasets are attached.
10. Eggs, milk, and bananas regression before the abstraction is considered mature.

## First vertical slice

Fresh Strawberries must be implemented through generic Product Pack capabilities. If strawberry implementation requires broad strawberry-specific core branches, stop and redesign.

## Definition of done for each phase

- Code is formatted/linted.
- Unit/integration tests pass.
- Database migrations are reversible where practical.
- New environment variables are documented in `.env.example` and Railway docs.
- API contracts are documented.
- No secrets or large local artifacts are committed accidentally.
- Acceptance criteria in the corresponding prompt are demonstrated.
