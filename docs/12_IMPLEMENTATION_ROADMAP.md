# Implementation Roadmap

## Phase 0 - Repository foundation
Monorepo, formatting/linting/tests, shared schemas, local Postgres, environment config, CI.

## Phase 1 - Location Master
Migrations, importer, normalization, retailer alias/country mapping, location admin/search APIs, location counts.

## Phase 2 - Collection Control Plane
Collection Definition CRUD/versioning, cost estimator, Collection Run, task expansion, Postgres task queue, worker leases, cancellation.

## Phase 3 - MetricsCart Adapters
Shared provider client/limiter, Walmart, ALDI, Amazon Same Day, raw object persistence, retries/429 cooldown, actual credits.

## Phase 4 - Normalization and Strawberry Product Pack Runtime
Canonical offers, Parquet artifacts, deterministic classification rules, AI fallback feature flag, strawberry attributes and exclusions.

## Phase 5 - Matching / Analytics / Validation
Strict and unit-price matching, geography, 10-mile proximity sensitivity, AnalysisResult, golden regression.

## Phase 6 - Application UI and Deliveries
Run wizard, monitor, analysis workspace, HTML, Excel, leadership email, audit package.

## Phase 7 - Railway production deployment
Migrations, private networking, bucket, worker scaling, logging, backups, health checks.

## Phase 8 - Prove abstraction
Add Eggs, Milk, Bananas in that order. Minimize new generic capabilities and prohibit category branches.

## Phase 9 - Automation
Schedules, historical run comparison, alert definitions/events, email delivery, collection budgets.

## Phase 10.1 - Dynamic Collection Builder
Approved geography snapshots, primary/competitor correspondence, exact Search estimates,
explicit paid launch, immutable version editing, and a separately governed PDP cadence.

## Phase 10.2 - Admin Product Pack Builder
Governed guided authoring, exact-version runtime catalog, immutable evidence manifests,
leased deterministic certification, and explicit publish/activate controls. Product Packs remain
configuration over category-neutral capabilities; published versions are immutable and existing
collections remain pinned to their original version.
