# Standalone Retail Competitive Intelligence - Codex Implementation Handoff

## Purpose

This repository package is the implementation specification for a standalone, Railway-hosted Retail Competitive Intelligence application. It is intentionally separate from CPGHero. CPGHero remains supplier/broker/agency oriented; this application is retailer-side competitive intelligence with Walmart as the initial benchmark retailer.

## Non-negotiable architecture

1. One generic analysis engine; no category-specific branches in core analytics.
2. Product-specific behavior lives in versioned Product Packs.
3. Retailer/API-specific behavior lives in versioned Retailer Adapters.
4. Authoritative calculations are deterministic code, never LLM output.
5. All UI/report/email/export surfaces consume one canonical `AnalysisResult`.
6. Raw provider responses and normalized datasets are immutable, versioned artifacts.
7. Store/provider identifiers are strings; never coerce them to integers.
8. PostgreSQL is the V1 control plane, durable task queue, and shared rate-limit coordinator.
9. Large raw/normalized datasets live in S3-compatible object storage (Railway Bucket); PostgreSQL stores metadata, summaries, state, and audit records.
10. Golden regression tests must pass before analytical logic is considered production-ready.

## First vertical slice

Fresh Strawberries: Walmart vs ALDI + Amazon Same Day.

The existing August 7, 2026 strawberry analysis is the first golden acceptance case because it includes exact ZIP comparisons, weight-normalized comparisons, and a 10-mile ALDI/Walmart proximity sensitivity check.

## How to use this package with Codex

1. Create a new standalone Git repository.
2. Unpack the package into the repository root so `AGENTS.md`, `README.md`, `schemas/`, `prompts/`, and the other handoff folders are directly visible to Codex.
3. Read `AGENTS.md` first.
4. Give Codex `prompts/00_CODEX_MASTER_PLANNING_PROMPT.md` and instruct it not to implement until the repo plan is approved.
5. Execute implementation phases in order. Do not skip golden tests.
6. Full source datasets for the four golden studies are not duplicated here because of size. Attach them separately when running full regressions. Compact parser fixtures and all validated summary outputs are included.

## Package map

- `docs/` - product, architecture, collection, analytics, UI, deployment, security, testing, rollout.
- `schemas/` - normative JSON contracts.
- `product-packs/` - eggs, milk, bananas, strawberries.
- `config/` - retailer endpoint/credit catalog and provider limits.
- `database/` - PostgreSQL control-plane schema and seed strategy.
- `fixtures/api_samples/` - real-shape representative API responses supplied by the product owner.
- `fixtures/location_master/` - full supplied 157,806-row location master, sample, and profile.
- `fixtures/golden/` - human-validated regression summaries and executable expected assertions.
- `schemas/golden-benchmarks.schema.json` - machine-readable regression assertion contract used by `scripts/validate_handoff.py`.
- `reference_outputs/` - prior human-validated HTML/Excel outputs for report-quality reference.
- `starter_contracts/` - reference-only Python interface examples; not production architecture.
- `prompts/` - staged Codex prompts.
- `examples/` - canonical collection definition and analysis result examples.
