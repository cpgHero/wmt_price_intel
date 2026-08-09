# Phase 9.5.5: Deterministic Insight and Reporting Engine

Status: implemented and locally accepted on 2026-08-08.

## Outcome

AnalysisResult V2 is now the canonical output for new worker analysis runs. The result contains a
registry of deterministic metrics, resolved evidence references, ranked insight candidates,
recommendations, deterministic narratives, validation, and provenance. Existing AnalysisResult V1
records and rendering remain supported.

There are no product-category branches in the insight engine, result builder, report projector,
renderers, API, or web workspace. Product-specific language, thresholds, section ordering, and
artifact contents are selected by the versioned Product Pack and its report blueprint.

## Runtime boundaries

- `rci-analytics` owns deterministic aggregation, insight-rule evaluation, scoring, ranking, and
  AnalysisResult V2 assembly.
- `rci-results` validates and persists the immutable result, resolves report-blueprint selectors,
  and renders stored values without recalculating analytics.
- The API exposes a blueprint-projected report view for AnalysisResult V2.
- The web application presents report sections supplied by that view while retaining the legacy V1
  workspace.

The ranking score is a configured weighted combination of normalized breadth, magnitude,
confidence, and actionability. Stable sorting and configured limits make repeated runs
deterministic. Every emitted insight and recommendation has metric and evidence references.

## Product Pack and report-blueprint contract

Each Product Pack now declares:

- an immutable report-blueprint ID and version;
- ranking weights, minimum score, and candidate limit;
- generic rule conditions against deterministic comparison fields;
- configured business impact and action language.

Each report blueprint declares:

- ordered UI/report sections and their metric selectors;
- required evidence kinds and empty states;
- artifact-specific section profiles;
- Excel worksheet definitions;
- narrative reference policy.

Production blueprints exist for strawberries, shell eggs, fluid milk, bananas, and ground beef.
Adding another category uses the same contracts and runtime.

## Acceptance evidence

The following gates passed locally:

```text
Python:       186 passed, 9 environment-gated skips
Web:          5 passed
TS contracts: 1 passed
Mypy:         95 source files, no issues
Ruff:         all changed Python files passed
ESLint:       web and contracts passed
Next.js:      production build passed
Contracts:    24 normative JSON documents validated
Goldens:      all configured benchmark assertions passed
```

The environment-gated skips are the existing full-source and Postgres integration suites. They are
run with their documented data/database variables during final Railway acceptance. No live
MetricsCart calls and no billable credits were used for this phase.

## Deferred to the next phases

- Phase 9.5.6 adds governed AI narratives without granting AI authority over metrics.
- Phase 9.5.7 applies final CPGHero branding and richer presentation treatment.
- Phase 9.5.8 runs full-source, Postgres, browser, concurrency, and Railway acceptance gates.

Product Details enrichment remains disabled until its separate acceptance decision.

## Railway acceptance evidence

- Commit `3f0e563` deployed the deterministic insight/reporting engine to web, API, worker, and
  scheduler.
- Production verification identified that the API image did not yet package the new blueprint
  catalog. Commit `da14ccf` added that catalog to the API image and added Product Pack/report
  blueprint watch paths for every Python runtime consumer.
- API, worker, and scheduler deployed `da14ccf` successfully; the compatible web build remained
  healthy on `3f0e563`.
- The production-backed result-persistence and worker-analysis suites completed with `5 passed`.
- The deployed API loaded `fresh_ground_beef_leadership` version `1.0.0` with all 10 configured
  sections.
- Public `/health/ready` returned `ready` with the API dependency `ok`.
- The temporary Railway SSH credential and all local temporary key material were removed after the
  acceptance run.
