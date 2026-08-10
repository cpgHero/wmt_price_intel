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
- `product-packs/` - eggs, milk, bananas, strawberries, ground beef.
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

Phase 9.5 decision-grade analysis and reporting acceptance is specified in
`docs/17_PHASE_9_5_DECISION_GRADE_PARITY.md`. V1 contracts remain active during the staged
transition; the V2 analysis, evidence, product-detail, governed-agent, and report-blueprint
contracts are validated alongside them.

Phase 9.5.2 adds portable, checksummed historical-input manifests and a zero-credit replay path
through the same durable analysis queue used by live collections. See
`docs/18_PHASE_9_5_2_HISTORICAL_REPLAY.md`.

Phase 9.5.3 adds bounded historical execution, generic retailer-aware comparison availability,
indexed proximity matching, and the full-source fresh-ground-beef Product Pack. See
`docs/19_PHASE_9_5_3_GENERIC_ANALYTICS_GROUND_BEEF.md`.

Phase 9.5.4 adds canonical retailer product identity and default-off, separately budgeted PDP
enrichment with durable leases, immutable cached snapshots, and replica-safe per-retailer/type rate
limits. See `docs/20_PHASE_9_5_4_PRODUCT_IDENTITY_PDP.md`.

Phases 9.5.5 through 9.5.8 add the generic insight/reporting engine, governed AI boundary,
CPGHero-branded delivery surfaces, full-source goldens, and immutable renderer versioning. See
`docs/21_PHASE_9_5_5_INSIGHT_REPORTING_ENGINE.md` through
`docs/24_PHASE_9_5_8_FULL_GOLDENS_AND_RENDERER_VERSIONING.md`.

Phase 9.6 adds the benchmark-derived semantic brief, category-configured narrative playbooks,
deterministic claim critic, and decision-grade narrative projection shared by web, email, and
workbook outputs. See `docs/25_PHASE_9_6_DECISION_GRADE_NARRATIVE_PARITY.md`.

Phases 9.7 through 9.9 add publication-scoped narrative evidence, selective PDP identity,
product-led decision surfaces, and one shared presentation contract for the app, HTML export, and
shareable report. See `docs/26_PHASE_9_7_DECISION_SURFACE_AND_ENRICHMENT.md` through
`docs/28_PHASE_9_9_REPORT_SURFACE_PARITY.md`.

Phases 9.9.1 through 9.9.3 add multi-retailer scorecards, globally one-to-one product-match
governance, and the implemented report-cohesion contract that separates comparison lenses, segments,
relationships, parity, readiness, and the insight-to-Match-Review workflow. See
`docs/29_PHASE_9_9_1_MULTI_RETAILER_REPORTING.md` through
`docs/32_PHASE_9_9_3_REPORT_COHESION_AND_MATCH_WORKFLOW.md`.

Primary application navigation, operational dashboard, collection history,
report discovery, schedules and alerts, and the decision-readiness quality
queue are governed by `docs/33_PRIMARY_APPLICATION_UX_COHESION.md`. This phase
does not change publication or export renderers.
