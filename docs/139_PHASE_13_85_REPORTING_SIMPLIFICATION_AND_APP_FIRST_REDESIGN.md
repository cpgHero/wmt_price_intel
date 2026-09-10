# Phase 13.85 - Reporting Simplification and App-First Redesign

Date: 2026-09-09

## Owner direction

The reporting system must be simplified around the decisions users need to make, not around internal pipeline objects or accumulated legacy surfaces. The app is the primary review and trust-building surface. PDF/export is still very important, but it must come after the app/reporting experience is validated and must render from the same governed report dataset.

Confirmed pilot categories:

- Bananas first, because the current active workflow and trust questions are there.
- Milk and eggs as required regression categories before the framework is considered reusable.

Confirmed audience priority:

- Walmart buyer / VP / executive audience first.
- Analyst and administrator evidence remains available through drilldowns and QA surfaces, not as competing primary report tabs.

Confirmed legacy posture:

- No legacy clutter in the active user experience.
- Remove or hide old pages, tabs, reports, archives, and replaced concepts from the default app workflow.
- Do not destructively delete historical raw data, database tables, or code paths until a usage audit proves they are unused and a rollback/backup path exists.

## Problem statement

The current reporting experience has accumulated too many pages, tabs, workflows, materialization layers, and historical artifacts. That makes the platform harder for users and coding agents to reason about. The biggest trust risk is not that the app lacks information; it is that multiple surfaces can present similar information with subtly different definitions, stale assumptions, or presentation choices that make accurate data look misleading.

The redesign must address these trust defects directly:

- Price normalization defects, including `$0.00` sentinels shown as real prices.
- Store distribution defects, including over-broad product footprints.
- Seller governance defects, including third-party seller products appearing in Walmart reporting.
- Confusing distinction between physical store-level Search presence and broader service-area presence.
- Report summaries that obscure product-level wins/losses.
- Mixed presentation where a few product relationships receive image cards while the rest fall into low-signal tables.
- Old report versions and change commentary appearing in stakeholder-facing reports.
- "No reports to display" states that do not explain the exact blocker or next action.

## Non-negotiable analytical contracts

These contracts govern all redesigned report and app surfaces:

1. Report renderers must not calculate authoritative analytics.
   - They consume a governed report dataset and evidence references.
   - Readiness and integrity rules belong in shared services, not presentation code.

2. Store-level distribution means:
   - count distinct nonblank physical store IDs
   - where the exact retailer product appears in store-level Search results
   - with a numeric price greater than 0
   - with no store-level in-stock claim
   - with no sponsorship requirement
   - with no extrapolation

3. Service-area presence is separate from physical store distribution.

4. Zero regular or discounted prices are missing/invalid sentinels unless explicitly proven valid by the source contract.

5. Product IDs, store IDs, ZIPs, ASINs, and retailer identifiers remain strings.

6. Seller governance must be explicit.
   - Walmart price intelligence and Walmart benchmark reporting must identify whether included products are seller-qualified.
   - Products that cannot be proven to meet the seller rule must be excluded from buyer-facing conclusions or clearly routed to Evidence & QA.

7. Product-level evidence controls the report.
   - Summaries must reconcile to product-level relationships.
   - Product-level wins/losses must be visible and inspectable.
   - Broad-distribution benchmark products matter more than rollup averages.

8. Legacy artifacts must not define current behavior.
   - Old reports may be used as forensic evidence during audit.
   - They must not leak into the new user experience as current-state guidance.

## Target information architecture

The redesigned app should expose one primary report experience with five tabs:

1. Executive Summary
   - Buyer-facing answer.
   - What matters, where Walmart is winning, where Walmart is exposed, and what action follows.
   - Short enough for an executive to understand quickly.

2. Product Wins & Losses
   - Core working surface.
   - All qualified product relationships shown as consistent visual cards when imagery exists.
   - No "example-only" cards with the rest buried in plain tables.
   - Sort/filter by win/loss, distribution, brand type, brand, package size, unit basis, and retailer.

3. Distribution & Assortment
   - Physical store distribution and assortment footprint.
   - Uses only the approved store-level Search presence contract.
   - Clearly separates service-area presence when shown.
   - Highlights broad-distribution Walmart products with competitive risk or opportunity.

4. Price Architecture
   - Pack-size, unit-price, brand-tier, organic/conventional, and category-specific ladder views.
   - Designed to explain price structure, not replace product-level wins/losses.

5. Evidence & QA
   - Match certification status.
   - Seller qualification.
   - Price normalization status.
   - Excluded/suppressed records and reason codes.
   - Source/evidence links.
   - Methodology, caveats, and validation checks.

Pages and concepts to remove from the primary user journey:

- Product Leadership as a separate top-level report concept.
- Match Summary as a buyer-facing tab.
- Store Review as a primary report tab.
- Separate Data Quality and Methodology tabs.
- Report Publishing as a normal user page.
- Any old/current-version comparison commentary inside stakeholder-facing reports.

## Target workflow

The app workflow should become:

1. Select category/report.
2. Review Executive Summary.
3. Inspect Product Wins & Losses.
4. Drill into evidence only when needed.
5. Publish/share once the app report is trusted.
6. Export PDF from the same governed report dataset.

The admin workflow should become:

1. Collect.
2. Normalize.
3. Apply Product Pack.
4. Certify matches.
5. Build governed report dataset.
6. Publish app report.
7. Export/share PDF.

Every stage must show:

- Current status.
- Exact blocker when blocked.
- Next action.
- Whether retained evidence can be reprocessed.
- Whether provider/API calls are required.
- Whether the blocker is data, matching, validation, publication, or rendering.

## Canonical report dataset

Before building new UI, define or adapt a canonical report dataset that all app and PDF surfaces consume.

Required top-level fields:

- report ID
- analysis run ID
- category
- report generated timestamp
- evidence observed timestamp/range
- benchmark retailer
- competitor retailers
- product pack ID/version/checksum
- retailer pack versions
- match certification status
- price normalization status
- seller governance status
- store distribution contract version
- service-area presence contract version, if present
- readiness status
- blocking reasons
- caveats

Required product relationship fields:

- relationship ID
- benchmark retailer product ID
- benchmark product title
- benchmark product URL
- benchmark product image URL
- benchmark brand
- benchmark brand type
- benchmark seller qualification status
- benchmark package/size/unit basis
- benchmark normalized unit price
- benchmark physical store distribution count
- competitor retailer
- competitor product ID
- competitor product title
- competitor product URL
- competitor product image URL
- competitor brand
- competitor brand type
- competitor seller qualification status, if applicable
- competitor package/size/unit basis
- competitor normalized unit price
- competitor physical store distribution count, if available and contract-valid
- price delta
- price delta percent
- Walmart win/loss/neutral classification
- match confidence/certification source
- relationship evidence references
- exclusion/suppression reason, if not reportable

Required QA fields:

- count of included relationships
- count of excluded relationships by reason
- count of records with invalid/missing price
- count of products with unverified seller
- count of products without image
- count of products without valid distribution evidence
- certification completeness
- product pack coverage
- retailer coverage

## Implementation phases

### Phase A - Audit and source-of-truth map

Purpose: make the existing system legible before changing behavior.

Tasks:

- Inventory app routes, report pages, report tabs, admin pages, APIs, renderers, materialization jobs, and exports.
- Identify which surfaces are active, legacy, duplicate, or admin-only.
- Map each visible metric to the code path and data source that produces it.
- Identify renderer-level analytics or readiness calculations that should move into a shared service.
- Capture current screenshots for bananas, milk, and eggs.
- Document all "No reports to display" entry points and what state produces them.

Deliverables:

- Route/page inventory.
- Metric/source lineage map.
- Legacy/noise removal candidate list.
- Current-state UX screenshots.
- Risk register.

Acceptance criteria:

- Each report metric has one named owner.
- Each active tab/page has a stated user job.
- Each candidate for removal has a migration/rollback note.

### Phase B - Contract and readiness service

Purpose: establish the governed data shape and readiness logic before rebuilding visuals.

Tasks:

- Define the canonical report dataset schema.
- Add contract tests for zero price handling, seller qualification, distribution counts, and product ID string preservation.
- Move or wrap readiness/integrity rules into a shared report-readiness service.
- Ensure app and PDF render paths consume the same governed data.
- Add blockers that explain missing report states clearly.

Deliverables:

- Report dataset schema.
- Readiness service contract.
- Validation fixture set for bananas, milk, and eggs.
- Failure reason taxonomy.

Acceptance criteria:

- Bananas can build a governed report dataset from retained evidence.
- Milk distribution defects remain fixed under regression.
- Eggs remain valid under the same generic framework.
- A blocked report says exactly why it is blocked and what to do next.

### Phase C - App-first report redesign

Purpose: replace the bloated tab structure with the new decision-led report experience.

Tasks:

- Build the five-tab report shell.
- Hide/remove legacy tabs from the primary user path.
- Create reusable product win/loss card components.
- Use product imagery consistently.
- Add sort/filter controls that match the buyer workflow.
- Add product evidence drawers with source links and QA details.
- Preserve deep links only where they remain meaningful.

Deliverables:

- New report shell.
- Product win/loss card grid.
- Distribution & Assortment tab.
- Price Architecture tab.
- Evidence & QA tab.

Acceptance criteria:

- A user can answer "where is Walmart winning and losing?" from one report experience.
- All qualified wins/losses are visible, not just selected examples.
- Product cards and tables reconcile.
- Seller and distribution caveats are clear without dominating the report.

### Phase D - Admin workflow simplification

Purpose: make report operations understandable and prevent opaque failure states.

Tasks:

- Replace scattered report publishing concepts with a single pipeline status view.
- Show Collect → Normalize → Product Pack → Match Certify → Build Report Dataset → Publish → Export.
- Add explicit retained-evidence reprocess action.
- Show whether a step requires external provider calls or only local retained evidence.
- Move detailed operations pages behind an advanced/admin details affordance.

Deliverables:

- Simplified admin pipeline view.
- Reprocess retained evidence action.
- Clear blocker/next-action UI.

Acceptance criteria:

- "No reports to display" is replaced by an actionable state.
- Reprocess is understandable and does not imply unnecessary recollection.
- Admins can see whether the issue is data, matching, validation, publication, or rendering.

### Phase E - PDF/export parity

Purpose: create a shareable executive PDF only after the app report is trusted.

Tasks:

- Generate PDF from the same canonical report dataset.
- Use the same product relationship cards and image hierarchy where practical.
- Remove report-version change commentary.
- Include all qualified wins/losses or a clearly labeled appendix when the list is long.
- Add visual QA checks for clipping, broken images, missing product cards, and misleading formatting.

Deliverables:

- Bananas executive PDF.
- Milk regression PDF.
- Eggs regression PDF.

Acceptance criteria:

- PDF and app agree on product facts.
- PDF is suitable for email sharing.
- No HTML-only final deliverable when PDF is requested.

### Phase F - Legacy/code cleanup

Purpose: eliminate noise safely after the new path is validated.

Tasks:

- Mark old routes/components as deprecated or remove from navigation.
- Add telemetry/log review or static references to prove whether code paths are unused.
- Remove dead code only after tests and route inventory prove safe removal.
- Archive legacy docs in a clearly separated historical folder only if needed for audit.
- Keep raw evidence and immutable historical artifacts unless a separate data-retention decision authorizes deletion.

Deliverables:

- Legacy removal plan.
- Safe deletion PR(s).
- Updated Platform Docs and change-order log for workflow changes.

Acceptance criteria:

- Active app has no legacy report clutter.
- Removed code is covered by reference checks.
- Historical/raw data is not destroyed accidentally.

## Visual design requirements

Product Wins & Losses cards should show:

- Benchmark product image.
- Competitor product image.
- Product names and IDs.
- Retailer and brand.
- Seller qualification badge where relevant.
- Unit price and normalized unit basis.
- Absolute and percentage price gap.
- Distribution footprint.
- Win/loss badge.
- Evidence/inspect action.

Cards should support:

- Sorting by distribution, price gap, brand type, competitor, and severity.
- Filtering by brand type, brand, product size, organic/conventional, retailer, and seller status.
- Toggle between card grid and compact evidence table, where the table is a secondary inspection mode rather than the default report.

Executive Summary should avoid:

- Dense tables.
- Unsupported recommendations.
- Version-change commentary.
- Internal implementation terms.
- Metrics that summarize away the actual product-level risk.

## Validation plan

Minimum validation before user-facing acceptance:

- Bananas pilot renders in new app experience.
- Milk regression confirms corrected price normalization and distribution handling.
- Eggs regression confirms category-generic behavior.
- Seller filters verified for Walmart.com where required.
- `$0.00` prices verified absent from reported price claims unless explicitly source-valid.
- Store distribution counts reconcile to positive-priced store-level Search presence.
- Product-level counts reconcile to summaries.
- Image availability and fallback behavior verified.
- PDF and app fact parity verified.

Test coverage:

- Schema/contract tests for canonical report dataset.
- Unit tests for price normalization and zero sentinel handling.
- Unit tests for distribution contract.
- Unit tests for seller qualification.
- Component tests for empty/blocker states.
- E2E tests for bananas report navigation and filters.
- Regression tests for milk and eggs.

## Initial backlog

1. Audit current routes and tabs.
2. Audit current report APIs and materialization jobs.
3. Audit current frontend report components.
4. Define canonical report dataset schema.
5. Define report readiness/blocker taxonomy.
6. Build bananas governed dataset adapter from existing retained evidence.
7. Build new app report shell behind a feature flag.
8. Build product win/loss card grid.
9. Build Evidence & QA drawer.
10. Replace ambiguous empty states.
11. Validate bananas end to end.
12. Run milk and eggs regressions.
13. Build PDF export from canonical dataset.
14. Remove legacy navigation entries from active app.
15. Prepare safe code cleanup plan.

## Phase A initial audit findings

Initial code inventory confirms that the reporting experience is spread across too many user-facing, admin-facing, and internal projection surfaces.

Primary app surfaces found:

- `apps/web/src/app/analyses/page.tsx`
- `apps/web/src/app/analyses/[analysisId]/workspace.tsx`
- `apps/web/src/app/analyses/[analysisId]/product-leadership-workspace.tsx`
- `apps/web/src/app/price-monitoring/page.tsx`
- `apps/web/src/app/price-monitoring/[analysisId]/workspace.tsx`
- `apps/web/src/app/price-intelligence/page.tsx`
- `apps/web/src/app/price-intelligence/[analysisId]/page.tsx`
- `apps/web/src/app/data-quality/page.tsx`
- `apps/web/src/app/admin/report-publishing/page.tsx`
- `apps/web/src/app/admin/matching-v2/page.tsx`
- `apps/web/src/app/admin/product-packs/page.tsx`
- `apps/web/src/app/collections/page.tsx`

Primary app/API bridge routes found:

- `apps/web/src/app/api/price-monitoring/[analysisId]/route.ts`
- `apps/web/src/app/api/price-monitoring/[analysisId]/catalog/route.ts`
- `apps/web/src/app/api/price-monitoring/[analysisId]/architecture-matrix/route.ts`
- `apps/web/src/app/api/price-monitoring/[analysisId]/map/route.ts`
- `apps/web/src/app/api/price-monitoring/[analysisId]/evidence.csv/route.ts`
- `apps/web/src/app/api/analyses/[analysisId]/competitive-product-leadership/route.ts`
- `apps/web/src/app/api/analyses/[analysisId]/competitive-product-coverage/route.ts`
- `apps/web/src/app/api/analyses/[analysisId]/competitive-portfolio-scorecards/route.ts`
- `apps/web/src/app/api/analyses/[analysisId]/competitive-decision-quality/route.ts`
- `apps/web/src/app/api/analyses/[analysisId]/artifacts/[artifactType]/route.ts`
- `apps/web/src/app/api/admin/report-publishing/[[...path]]/route.ts`

Primary backend/reporting services found:

- `apps/api/src/rci_api/report_publication.py`
- `apps/api/src/rci_api/competitive_leadership.py`
- `apps/api/src/rci_api/price_monitoring.py`
- `apps/api/src/rci_api/analyses.py`
- `apps/api/src/rci_api/matching_v2.py`
- `apps/api/src/rci_api/matching_v2_review.py`
- `packages/python/rci-analytics/src/rci_analytics/result_v2.py`
- `packages/python/rci-analytics/src/rci_analytics/product_location.py`
- `packages/python/rci-analytics/src/rci_analytics/competitive_leadership.py`
- `packages/python/rci-analytics/src/rci_analytics/product_leadership_validation.py`

Largest inspected files:

- `apps/web/src/app/analyses/[analysisId]/workspace.tsx` - 5,511 lines
- `apps/web/src/app/price-monitoring/[analysisId]/workspace.tsx` - 3,534 lines
- `apps/api/src/rci_api/price_monitoring.py` - 2,215 lines
- `apps/api/src/rci_api/competitive_leadership.py` - 2,136 lines
- `apps/web/src/app/analyses/[analysisId]/product-leadership-workspace.tsx` - 1,717 lines
- `packages/python/rci-analytics/src/rci_analytics/result_v2.py` - 1,091 lines
- `apps/api/src/rci_api/report_publication.py` - 996 lines
- `apps/web/src/lib/report-presentation.ts` - 840 lines
- `packages/python/rci-analytics/src/rci_analytics/product_location.py` - 722 lines

This supports the redesign hypothesis: complexity is concentrated in a few very large frontend workspaces and backend projection/publication services. The first implementation should not start by changing matching, recollecting data, or polishing PDFs. It should start by extracting a canonical report dataset and a simpler app shell that can sit in front of the existing machinery while old surfaces are hidden from the primary workflow.

Initial removal/consolidation map:

- Keep Product Packs, matching certification, normalized evidence, and retained artifacts as core infrastructure.
- Convert Price Intelligence into a product evidence/drilldown surface under the redesigned report.
- Convert Competitive Intelligence/Product Leadership into the unified report experience.
- Move Report Publishing out of the normal user path and into an admin pipeline/status surface.
- Merge Data Quality and Methodology into Evidence & QA.
- Replace separate Store Review/Geographic Coverage concepts with Distribution & Assortment.
- Remove previous-version commentary from report outputs.
- Replace ambiguous empty states with blocker-specific report status.

Current tab labels found in code/docs that should be consolidated:

- Legacy analysis tabs: Executive Summary, Geographic Coverage, Price Position, Segment Analysis, Product Matches, Assortment, Data Quality / QA, Methodology.
- Competitive report tabs: Retailer Scorecards, Cohort Scorecards, Competitive Footprint, Matched Price Matrix, Match Summary, Price Ladders, Store Comparisons, Competitive History, Assortment Scorecards.
- Price Intelligence tabs: Home, Price Architecture Matrix, Product Overview, Price Architecture, Store Review, Product History.

Target consolidation:

- Executive Summary keeps the buyer-facing overview.
- Product Wins & Losses absorbs Product Matches, Match Summary, Matched Price Matrix, and most Product Leadership/Competitive Footprint evidence.
- Distribution & Assortment absorbs Geographic Coverage, Store Comparisons, Store Review, Assortment, and Assortment Scorecards when those views are distribution/footprint questions.
- Price Architecture absorbs Price Position, Segment Analysis, Cohort Scorecards, Price Ladders, and the current Price Architecture Matrix when those views explain price structure rather than product-level wins/losses.
- Evidence & QA absorbs Data Quality / QA, Methodology, certification evidence, seller governance, blocker details, and source lineage.

## Out-of-scope until explicitly authorized

- Deleting raw collected evidence.
- Dropping production database tables.
- Recollecting provider data when retained evidence is sufficient.
- Changing Product Pack matching rules for a specific category inside generic code.
- Letting LLMs compute authoritative metrics.
- Publishing/share-linking externally before the app report is validated.

## Recommended next action

Start Phase A immediately in the active development repo. The first concrete implementation task should be a route/page/API inventory with a removal map, followed by the canonical report dataset schema. Do not begin with visual polish or PDF export; those should follow once the report facts and app structure are stable.

## Progress updates

### 2026-09-09

- Phase A started in `docs/140_PHASE_13_86_REPORTING_SURFACE_INVENTORY_AND_REMOVAL_MAP.md`.
- Phase B started in `docs/141_PHASE_13_87_CANONICAL_REPORT_DATASET_CONTRACT.md`.
- Added `schemas/canonical-report-dataset.schema.json` as the first canonical app/PDF report dataset contract.
- Added `examples/canonical-report-dataset.bananas.json` as the first bananas-shaped contract fixture.
- Added contract validator/test wiring and TypeScript contract export scaffolding.
- Added a read-only app-layer adapter that projects current report-view evidence into the canonical report dataset and excludes unsafe/incomplete product relationships.
- Corrected misleading Price Intelligence UI copy from retailer-master location source to positive-price store Search distribution source.
- No route removal, raw evidence mutation, database deletion, provider call, AI call, report publication, or PDF export behavior change has been made.

### 2026-09-10

- Phase 13.94 made empty canonical report datasets fail closed instead of presenting as buyer-ready.
- Production checks then showed milk and eggs had matching-v2 certified relationships and governed candidate rows, but empty `product_decisions`.
- Phase 13.95 adds a narrow canonical report adapter fallback: when `product_decisions` is empty, use governed, QA-ready, positive-price `match_candidates`, deduped by relationship/pair and ranked by preferred Product Pack comparison basis.
- No Product Pack rules, matching certification, immutable analysis results, prices, distribution counts, seller rules, provider collection, PDP calls, AI calls, report publication records, or PDF export behavior are changed by this fallback.
