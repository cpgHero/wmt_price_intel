# Phase 13.86 - Reporting Surface Inventory and Removal Map

Date: 2026-09-09

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

This document starts Phase A of the reporting simplification work. It inventories the current reporting, price-intelligence, publication, and administrative surfaces that affect the user experience, then classifies what should remain primary, move behind drilldowns, consolidate, or be removed from the active workflow.

This is intentionally non-destructive. It does not authorize deletion of raw evidence, database tables, immutable artifacts, or production history.

## Confirmed redesign direction

- App-first. The app is the primary review and trust-building surface.
- PDF/export follows once the app report is final and validated.
- Bananas are the first pilot.
- Milk and eggs are required regression categories.
- No old/legacy clutter in the active experience.
- Remove pages/tabs/labels/reports from the active workflow when they no longer serve the target experience.
- Delete code/data only after a usage audit proves safe removal.

## Current primary navigation

Current navigation creates three mental zones:

1. Analytics
   - Price Intelligence
   - Competitive Intelligence

2. Operations
   - Collections
   - Schedules & Alerts
   - Data Quality

3. Administration
   - System Operations
   - Platform Docs
   - Match Certification
   - Brand Workbench
   - Study Discovery
   - Report Publishing
   - Product Packs

### Finding

The split between Price Intelligence and Competitive Intelligence is analytically defensible but confusing for the primary user journey. Users experience them as competing report surfaces even though Price Intelligence is better understood as product evidence and price architecture support for the unified report.

### Recommended action

Create one primary report entry point. Keep Price Intelligence functionality, but route it as a drilldown/evidence workspace from the redesigned report instead of making it a peer top-level report destination.

## Current app route inventory

### Primary user-facing analytics routes

| Route | Current purpose | Recommended disposition |
| --- | --- | --- |
| `/analyses` | Competitive report library | Keep as primary report library, renamed/reframed as Reports or Intelligence Reports. |
| `/analyses/[analysisId]` | Competitive report workspace | Replace internals with simplified five-tab report shell. |
| `/price-intelligence` | Price Intelligence library | Remove from primary navigation after the unified report shell is live; keep as redirected or advanced evidence entry point. |
| `/price-intelligence/[analysisId]` | Price Intelligence report route wrapper | Keep temporarily as compatibility route; route users into report evidence/drilldown context. |
| `/price-monitoring` | Price monitoring library | Treat as legacy/technical naming; remove from primary navigation if not already hidden. |
| `/price-monitoring/[analysisId]` | Price Intelligence workspace implementation | Convert into shared evidence/detail components consumed by the report. |
| `/data-quality` | Decision readiness and evidence exceptions | Consolidate into Evidence & QA and admin pipeline status. |

### Operations and administration routes

| Route | Current purpose | Recommended disposition |
| --- | --- | --- |
| `/collections` | Collection definitions/runs | Keep as admin/operator workflow. |
| `/collections/new` | New collection wizard | Keep. |
| `/collections/definitions/[stableKey]/edit` | Edit collection definition | Keep. |
| `/collections/runs/[runId]` | Collection run details | Keep. |
| `/automation` | Schedules & Alerts | Keep, but not part of report review. |
| `/admin/operations` | System operations | Keep as advanced admin. |
| `/admin/docs` | Platform Docs | Keep; must be updated with the new workflow. |
| `/admin/matching-v2` | Match Certification | Keep as critical admin workflow. |
| `/workspace/brands` | Brand Workbench | Keep as admin workflow; remove from buyer-facing report path. |
| `/workspace/brands/[analysisId]` | Analysis-specific brand workbench | Keep as admin drilldown. |
| `/workspace/matches` | Match workspace | Classify as legacy/secondary; verify usage before removal. |
| `/workspace/matches/[analysisId]` | Analysis-specific match workspace | Classify as legacy/secondary; use Match Certification as canonical admin surface. |
| `/admin/studies` | Study discovery | Keep as onboarding/admin workflow. |
| `/admin/product-packs` | Product Pack administration | Keep as critical admin workflow. |
| `/admin/product-packs/drafts/[draftId]` | Product Pack draft authoring | Keep. |
| `/admin/report-publishing` | Report materialization status | Move behind a unified pipeline/status surface. Do not keep as primary user-facing concept. |

## Current tab inventory

### Legacy analysis workspace tabs

Found in `apps/web/src/app/analyses/[analysisId]/workspace.tsx`:

- Executive Summary
- Geographic Coverage
- Price Position
- Segment Analysis
- Product Matches
- Assortment
- Data Quality / QA
- Methodology

Disposition:

- Keep only the intent of Executive Summary.
- Fold Product Matches into Product Wins & Losses.
- Fold Geographic Coverage and Assortment into Distribution & Assortment.
- Fold Price Position and Segment Analysis into Price Architecture.
- Fold Data Quality / QA and Methodology into Evidence & QA.
- Remove the legacy workspace from active report handling once current reports all use the governed report dataset.

### Current competitive report tabs

Found in `apps/web/src/app/analyses/[analysisId]/workspace.tsx` and `apps/web/src/lib/competitive-report-tabs.ts`:

- Retailer Scorecards
- Cohort Scorecards
- Competitive Footprint
- Matched Price Matrix
- Match Summary
- Price Ladders
- Store Comparisons
- Competitive History
- Assortment Scorecards

Disposition:

- Collapse Retailer Scorecards, Competitive Footprint, Matched Price Matrix, and Match Summary into Product Wins & Losses where they describe product relationships.
- Collapse Cohort Scorecards and Price Ladders into Price Architecture where they describe price structure.
- Collapse Store Comparisons and Assortment Scorecards into Distribution & Assortment where they describe footprint, assortment, local comparable coverage, or gaps.
- Remove Competitive History from the primary shell until comparable cross-run continuity is certified. If unavailable, show it only as a clearly disabled capability in Evidence & QA.

### Current Price Intelligence tabs

Found in `apps/web/src/app/price-monitoring/[analysisId]/workspace.tsx`:

- Home
- Price Architecture Matrix
- Product Overview
- Price Architecture
- Store Review
- Product History

Disposition:

- Home becomes the product evidence catalog behind Product Wins & Losses or Evidence & QA.
- Price Architecture Matrix moves into Price Architecture.
- Product Overview becomes product evidence drawer/detail.
- Price Architecture becomes product evidence drawer/detail or supporting section under Price Architecture.
- Store Review moves into Distribution & Assortment or Evidence & QA depending on whether the user is reviewing footprint or exceptions.
- Product History remains hidden unless comparable cross-run history is certified.

## Proposed target app navigation

### Primary navigation

1. Reports
   - replaces the current split between Competitive Intelligence and Price Intelligence.
   - opens the report library and unified report workspace.

2. Collections
   - data acquisition and run history.

3. Admin
   - Match Certification
   - Product Packs
   - Brand Governance
   - Study Discovery
   - Pipeline Status
   - System Operations
   - Platform Docs

### Alternative if a broader sidebar is still desired

Keep the three sections, but simplify labels:

1. Analytics
   - Reports

2. Operations
   - Collections
   - Schedules & Alerts
   - Pipeline Status

3. Administration
   - Match Certification
   - Product Packs
   - Brand Governance
   - Study Discovery
   - System Operations
   - Platform Docs

Data Quality and Report Publishing should not remain standalone primary destinations. Their useful content belongs inside Evidence & QA and Pipeline Status.

## API and service inventory

### Current report and artifact APIs

| API | Current purpose | Recommended disposition |
| --- | --- | --- |
| `GET /api/v1/analyses` | Report library | Keep. Add explicit status/blocker fields if missing from list response. |
| `GET /api/v1/analyses/{analysis_id}` | Analysis record | Keep as source record endpoint. |
| `GET /api/v1/analyses/{analysis_id}/report` | Current report view | Replace or wrap with canonical governed report dataset endpoint. |
| `GET /api/v1/analyses/{analysis_id}/product-decisions/{decision_id}/evidence` | Product decision evidence | Keep; likely feeds Product Wins & Losses evidence drawer. |
| `GET /api/v1/analyses/{analysis_id}/artifacts` | Artifact list | Keep, but expose PDF once parity is ready. |
| `POST /api/v1/analyses/{analysis_id}/artifacts/{artifact_type}` | Generates html/xlsx/email/audit artifacts | Update after PDF parity. Avoid HTML-only stakeholder delivery. |
| `GET /api/v1/artifacts/{artifact_id}/download` | Artifact download | Keep. |

### Current price evidence APIs

| API | Current purpose | Recommended disposition |
| --- | --- | --- |
| `GET /api/v1/analyses/{analysis_id}/price-monitoring` | Product price/distribution workspace | Keep internally; consume as evidence/detail source. |
| `GET /api/v1/analyses/{analysis_id}/price-monitoring/catalog` | Product catalog page/filter | Keep; likely source for product selection and evidence drawer. |
| `GET /api/v1/analyses/{analysis_id}/price-architecture-matrix` | Price architecture matrix | Keep; move into Price Architecture tab. |
| `GET /api/v1/analyses/{analysis_id}/price-monitoring/map` | Product distribution map | Keep as evidence/detail. |
| `GET /api/v1/analyses/{analysis_id}/price-monitoring/evidence.csv` | Evidence export | Keep under Evidence & QA. |

### Current competitive/product leadership APIs

| API | Current purpose | Recommended disposition |
| --- | --- | --- |
| `GET /api/v1/analyses/{analysis_id}/competitive-portfolio-scorecards` | Portfolio scorecards | Use as input to canonical report dataset until replaced. |
| `GET /api/v1/analyses/{analysis_id}/competitive-product-coverage` | Product coverage evidence | Keep as evidence source. |
| `GET /api/v1/analyses/{analysis_id}/competitive-decision-quality` | Decision quality | Move into Evidence & QA/readiness service. |
| `GET /api/v1/analyses/{analysis_id}/competitive-product-leadership` | Product leadership views | Collapse into Product Wins & Losses, Distribution & Assortment, and Price Architecture. |

### Current publication/materialization APIs

| API | Current purpose | Recommended disposition |
| --- | --- | --- |
| `POST /api/v1/internal/report-materialization-jobs/{job_id}/prepare` | Builds materialization plan and blocks if readiness fails | Keep internally; move readiness calculation out of renderer/report view. |
| `POST /api/v1/internal/report-materialization-jobs/{job_id}/price-architecture` | Stages price architecture document | Keep as cache/materialization layer. |
| `POST /api/v1/internal/report-materialization-jobs/{job_id}/price-catalog` | Stages price catalog document | Keep as cache/materialization layer. |
| `POST /api/v1/internal/report-materialization-jobs/{job_id}/competitive-portfolio` | Stages portfolio document | Keep as cache/materialization layer. |
| `POST /api/v1/internal/report-materialization-jobs/{job_id}/finalize` | Atomically activates staged docs | Keep. |
| `GET /api/v1/admin/report-materialization-jobs` | Admin job list | Move into Pipeline Status. |
| `POST /api/v1/admin/report-materialization-jobs/{job_id}/retry` | Admin retry | Keep behind Pipeline Status. |

## High-priority trust findings

### 1. Price Intelligence context still uses misleading location copy

Current code shows:

- Price source: Search
- Product grain: One median per SKU
- Location source: Retailer master

This is misleading under the corrected distribution contract. Store distribution is not derived from a retailer master; it is the count of distinct physical stores where the exact product appears in store-level Search with price greater than zero.

Recommended fix:

- Replace "Location source: Retailer master" with "Distribution source: positive-price store Search presence" or equivalent concise text.
- Ensure the same wording appears consistently in Product Wins & Losses, Distribution & Assortment, Evidence & QA, and PDF export.

Status:

- Corrected in `apps/web/src/app/price-monitoring/[analysisId]/workspace.tsx` on 2026-09-09.
- Remaining work: carry the same wording into the redesigned report shell and PDF export.

### 2. Report library empty state is too generic

Current empty state says:

- "No reports to display"
- "Publish a validated AnalysisResult from a completed collection run to populate this workspace."

This is not actionable enough for the user. It does not distinguish missing collection, incomplete Product Pack, pending matching, failed validation, blocked publication, or unavailable report materialization.

Recommended fix:

- Add report status/blocker taxonomy to the library response or a companion status endpoint.
- Replace generic empty states with exact next actions.

### 3. One workspace interleaves too many report concepts

`apps/web/src/app/analyses/[analysisId]/workspace.tsx` contains both legacy and blueprint report handling and interleaves scorecard groups with product-leadership tabs in one tab list. This is a major contributor to cognitive load.

Recommended fix:

- Create a new report shell and keep this file as a compatibility adapter during transition.
- Move Product Leadership internals behind reusable Product Wins & Losses, Distribution & Assortment, and Price Architecture sections.

### 4. Renderer-level integrity logic is too heavy

`packages/python/rci-results/src/rci_results/renderers.py` applies substantial report integrity/readiness logic inside the report-view renderer. This conflicts with the architectural invariant that report/email renderers should consume analytics rather than recalculate or govern them.

Recommended fix:

- Extract readiness/integrity into a shared report-readiness service.
- Make renderers consume readiness output as data.

### 5. Artifact types do not yet reflect the confirmed PDF-first share path

Current artifact generation allows `html`, `xlsx`, `leadership_email`, and `audit_zip`. The confirmed path requires app-first, then PDF/export parity. HTML should not be the default stakeholder artifact.

Recommended fix:

- Add PDF artifact generation after the app report dataset is validated.
- Keep HTML only if useful internally or as a secondary artifact.

## First implementation work order

Do these in order:

1. Add a canonical report dataset schema or typed contract.
2. Add a report-readiness/blocker taxonomy.
3. Add a new app report shell behind a feature flag or route-local adapter.
4. Feed bananas through the new report shell.
5. Replace the misleading Price Intelligence location-source copy.
6. Replace generic report empty states with blocker-aware messages.
7. Collapse report tabs into the five target tabs.
8. Move Price Intelligence product details into evidence drawers/drilldowns.
9. Validate milk and eggs as regressions.
10. Add PDF only after app parity is accepted.

## Safe cleanup work order

Do these only after the new app shell validates:

1. Remove Price Intelligence from primary navigation.
2. Move Report Publishing into Pipeline Status.
3. Merge Data Quality into Evidence & QA and Pipeline Status.
4. Hide Product History unless continuity is certified.
5. Remove legacy analysis workspace fallback for current reports.
6. Remove dead routes/components after reference checks pass.
7. Keep raw evidence and immutable historical artifacts unless separately authorized for data deletion.

## Phase A status

Status: in progress.

Completed:

- Primary navigation inventory.
- User-facing route inventory.
- Reporting tab inventory.
- Backend/API inventory.
- Initial high-priority trust findings.
- Initial target consolidation map.
- Immediate correction of misleading Price Intelligence distribution-source copy.

Remaining before Phase A is complete:

- Produce line-level metric/source lineage for currently visible report metrics.
- Identify all code paths that still mention legacy report concepts.
- Identify tests that must be changed or added for the new shell.
- Capture live screenshots for bananas, milk, and eggs.
- Confirm current production report IDs for the three pilot categories before any implementation uses real data.

Downstream dependency now available:

- Phase B canonical report dataset contract started in `docs/141_PHASE_13_87_CANONICAL_REPORT_DATASET_CONTRACT.md`.
- The removal/consolidation work should target `schemas/canonical-report-dataset.schema.json` rather than extending the current tab-specific report views.
