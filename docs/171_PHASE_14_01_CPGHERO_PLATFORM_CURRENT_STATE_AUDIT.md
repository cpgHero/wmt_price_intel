# Phase 14.01 — CPGHero platform current-state audit and implementation plan

## Purpose

This audit converts the approved CPGHero platform vision into an implementation-ready current-state assessment. It is intentionally practical: what already exists, what is risky, what should be simplified, what should be retired or hidden, and what should be built next.

This is a planning and sequencing artifact. It does not claim that the target CPGHero platform capabilities are already live.

## Decision this audit supports

The next product decision is whether to continue polishing individual report pages or step back and harden the platform foundation first.

Recommendation: pause new page-level feature expansion except for critical fixes. The repo already has valuable collection, evidence, geography, matching, reporting, and proximity foundations. The highest-leverage next work is to turn those foundations into a clean, secure, multi-tenant CPGHero platform with explicit customer-facing surfaces, role-aware navigation, trusted data contracts, and automated masking/security gates.

## Executive finding

The current product is a strong internal competitive-intelligence workbench, not yet a customer-grade CPGHero platform.

The strongest foundations are:

- durable collection definitions, runs, queue tasks, raw artifact tracking, and usage accounting;
- immutable geography snapshots, location-master data, and proximity relationships;
- product packs, retailer packs, brand governance, matching/certification, and report materialization;
- analysis input sets and retained-evidence replay patterns that support reprocessing without recollection;
- early analytics surfaces for reports, price intelligence, price monitoring, data quality, and proximity.

The largest gaps are:

- customer-grade account, user, role, entitlement, API-key, billing, and audit experiences are not yet productized;
- the application still uses internal/admin session patterns rather than a full tenant-aware access model;
- provider-specific terminology remains in many repository files and must be gated away from customer-visible code, docs, responses, exports, logs, and bundles;
- navigation and page taxonomy are still organized around internal operations and prior development phases rather than the three commercial surfaces: Live APIs, Bulk Projects, and App Analytics;
- collection, reporting, and reprocessing are technically capable but not yet simple enough for a customer or internal operator to trust without developer involvement;
- old phase artifacts, reference outputs, fixtures, source material, duplicate docs, and historical implementation notes create substantial noise for AI coding agents and human maintainers.

## Scope reviewed

This pass reviewed the repository shape and representative implementation files, including:

- application navigation and routes under `apps/web/src/app`;
- FastAPI service assembly and representative routers under `apps/api/src/rci_api`;
- collection, location, provider, product, result, automation, analytics, and agent packages under `packages/python`;
- schema contracts under `schemas`;
- migration history under `database/migrations/versions`;
- current owner/admin docs and platform blueprint under `docs`;
- repository rules in `AGENTS.md`.

The audit is based on code and documentation inspection. It does not include a live production database query, penetration test, load test, or full end-to-end browser test.

## Important boundary update

`AGENTS.md` still describes the project as a standalone retailer competitive-intelligence product and says not to import CPGHero application assumptions unless explicitly provided later. The platform owner has now explicitly provided that later direction.

The product boundary should be updated in a future implementation PR:

- from: standalone retail competitive-intelligence product with Walmart as the initial benchmark;
- to: CPGHero, a secure multi-tenant retailer data and intelligence platform where Walmart competitive intelligence is one premium application module.

The old invariant should not be discarded entirely. The reusable engine still should not be hard-coded to Walmart, milk, bananas, eggs, strawberries, or any other category. The new boundary should say that CPGHero is the product shell and commercial platform, while the collection/analytics engine remains retailer- and category-extensible.

## Current route inventory

Current top-level app routes observed:

| Current area | Representative routes | Assessment |
| --- | --- | --- |
| Home | `/` | Useful landing surface, but currently mixes decision, activity, and operational health. Needs role-specific home dashboards. |
| Analytics | `/analyses`, `/price-intelligence`, `/price-monitoring`, `/proximity`, `/data-quality` | Valuable analytics work exists, but the taxonomy needs to become module-based and user-role aware. |
| Collections | `/collections`, `/collections/new`, `/collections/runs/[runId]` | Strong start for Bulk Projects, but naming and workflow should become customer-facing project management rather than internal collection mechanics. |
| Automation | `/automation` | Useful for schedules and alerts, but should be subordinate to projects unless exposed as an advanced workspace. |
| Admin | `/admin/operations`, `/admin/docs`, `/admin/matching-v2`, `/admin/product-packs`, `/admin/report-publishing`, `/admin/studies` | Correct as internal CPGHero system-admin surfaces; not suitable as ordinary customer navigation. |
| Workbench redirects | `/workspace/brands`, `/workspace/matches` | Useful governance tools, but should live under internal Intelligence Governance or System Admin, not customer workspace by default. |
| API proxies | `/api/admin/*`, `/api/collections/*`, `/api/proximity/*`, `/api/price-monitoring/*` | Functional for current app integration; customer-facing APIs need a separate branded contract and auth layer. |

Missing or immature customer-facing routes:

- `/account` or `/settings` for customer profile, users, roles, entitlements, billing, security, and audit logs;
- `/developers` for Live API docs, API keys, usage, playground, and integration diagnostics;
- `/bulk-projects` for data-feed project creation, scheduling, delivery destinations, and run history;
- `/data` or `/my-data` for delivered files, retrieval links, manifests, schemas, and download history;
- `/geographies` for saved location sets;
- `/comp-groups` for reusable retailer proximity relationships;
- `/review-radar` for review projects and AI insight outputs;
- `/share-of-search` or `/keyword-performance` for SERP ranking and sponsored/organic visibility.

## Current navigation assessment

The current simplified navigation groups are:

- Analytics: Reports, Proximity;
- Operations: Collections, Schedules & Alerts, Pipeline Status;
- Administration: Match Certification, Product Packs, Brand Governance, Study Discovery, System Operations, Platform Docs.

This is a meaningful simplification versus the previous internal nav, but it still exposes the implementation model rather than the customer mental model.

Recommended target navigation:

| Target group | Customer-facing items | Internal/system-admin items |
| --- | --- | --- |
| Home | Executive dashboard, recent projects, alerts, data freshness | System health for system admins only |
| Live APIs | API keys, docs, playground, usage, errors | Provider routing, global rate limits, credential health |
| Bulk Projects | Projects, runs, schedules, delivery destinations, My Data | Recovery, spend authorization, blocked tasks, raw evidence |
| Analytics | Price Intelligence, Competitive Intelligence, Share of Search, Review Radar, Proximity, Data Quality | Report publication gates and artifact materialization |
| Geography | Location sets, comp groups, proximity explorer | Location master imports, eligibility reconciliation |
| Account | Users, roles, entitlements, billing, security, audit logs | Tenant administration, plan templates, support impersonation controls |
| Intelligence Governance | Not customer-visible by default | Product Packs, Retailer Packs, Brand Governance, Study Discovery, Match Certification |

## Backend and data-plane inventory

The backend already has many core primitives:

| Foundation | Evidence in repo | Keep / change |
| --- | --- | --- |
| Organization/user seed | `organization`, `app_user`, `organization_id` in migrations | Keep concept; replace single default organization assumptions with real tenant/account/workspace model. |
| Collection definitions and versions | `collection_definition`, `collection_definition_version` | Keep; rename product language around Bulk Projects and make drafts/estimates/approvals customer-grade. |
| Durable queue | `collection_run`, `collection_task`, lease fields, retry fields | Keep; harden tenant scoping, usage ledger, and customer-safe status messages. |
| Raw artifact tracking | `dataset_artifact`, `raw_artifact_id`, checksums, immutable metadata | Keep; make the data lifecycle visible as raw, normalized, data product, analytics mart, report artifact. |
| Usage and billing primitives | `billable_credits`, run actual/estimated credits, AI usage fields | Keep; expand into account/key/project/endpoint/customer billing ledger. |
| Geography snapshots | `collection_geography_resolution`, `collection_geography_location`, `collection_geography_edge`, estimates | Keep; expose as saved Geographies and Comp Groups. |
| Scope projections | `collection_scope_projection` and related tables | Keep; explain clearly as governed footprint corrections/reprocessing, not generic availability. |
| Product Pack / Retailer Pack governance | product pack, retailer pack, brand foundation, study discovery, matching tables | Keep internal; make customer-facing outputs simple and entitled. |
| Report publication | `analysis_result`, `report_artifact`, `analysis_publication`, materialization jobs | Keep; reframe as report/artifact lifecycle with clear customer visibility. |
| Proximity API | `/api/v1/proximity` plus location repository nearest-pair computation | Keep; backend should own more precomputed metrics and drilldown slices. |

The architecture is promising because it already separates control-plane tables from object-storage artifacts. The cleanup should preserve that direction.

## Provider masking audit

Provider masking is a release blocker for any customer-facing CPGHero surface.

Preliminary scan results:

| Scan category | Count observed | Files observed | Interpretation |
| --- | ---: | ---: | --- |
| Upstream provider brand string | 861 | 200 | Too broad for a customer-ready codebase. Some are acceptable historical/internal references, but the build needs customer-visible leak gates. |
| Provider API-key query parameter string | 46 | 15 | Expected in internal adapter/tests, but unacceptable in customer docs, client bundles, logs, or exported artifacts. |
| Default standalone organization UUID | 26 | 18 | Useful for internal history/tests, but risky if production behavior depends on it. |
| Admin-session environment/cookie patterns | 35 | 21 | Adequate for owner-admin tools; not adequate for multi-tenant customer auth. |
| Generic provider/internal adapter terms | 392 | 72 | Many are legitimate internal abstractions. They need visibility classification, not blind removal. |

Masking should not be implemented as a naive rename. The right approach is classification plus enforcement:

1. **Customer-visible forbidden list.** The upstream provider brand, endpoint hostnames, credential names, request-specific secrets, raw provider billing mechanics, and provider-facing parameter names are forbidden in customer UI, browser bundles, public docs, exported files, share links, customer API responses, customer logs, and error messages.
2. **Internal-allowed list.** Adapter modules, private migrations, internal fixtures, internal source-material manifests, and private operations docs may retain provider-specific implementation details when necessary.
3. **Automated gates.** Build-time and CI checks should scan:
   - compiled browser assets;
   - customer route source;
   - generated API docs/OpenAPI intended for customers;
   - customer-facing Platform Docs sections;
   - exported report/sample artifacts;
   - email templates and webhook payloads;
   - representative logs after redaction.
4. **Contract aliases.** Customer APIs and docs should use CPGHero endpoint-family names: CPGHero Search, CPGHero Product Detail, CPGHero Reviews, CPGHero Collection Credits, CPGHero Live API, CPGHero Bulk Projects.
5. **Safe error mapping.** Upstream failures should map to CPGHero-safe classes such as `source_unavailable`, `rate_limited`, `invalid_request`, `schema_change_detected`, and `collection_temporarily_unavailable`.

## Multi-tenant readiness

The database already includes `organization_id` on many key tables, but the product is not yet multi-tenant in the way the platform vision requires.

Current risks:

- a default standalone organization appears in code and tests;
- current web admin surfaces use an eight-hour administrator session pattern rather than tenant-aware user identity;
- role modeling is currently coarse (`admin`, `analyst`, `viewer`) rather than composable permissions;
- customer-facing account, workspace, entitlement, API-key, billing, and audit-log experiences are missing;
- row-level access boundaries need to be proven route-by-route and query-by-query before customer use.

Required target:

- every persistent domain row must have tenant/account ownership or explicit system scope;
- every API must resolve an authenticated principal before data access;
- every query touching customer-owned data must include account/workspace/project scoping;
- system-admin access must be explicit, audited, and separated from customer access;
- support/impersonation-style workflows, if ever added, must be narrow, time-bound, and logged.

## Data lifecycle simplification

The platform should make this lifecycle obvious:

1. **Request ledger** — what the platform planned to collect, with project, account, endpoint family, retailer, geography, cadence, and estimated cost.
2. **Raw snapshots** — immutable source payloads and response metadata.
3. **Normalized observations** — CPGHero-standard SERP/PDP/REVI records.
4. **Project datasets** — customer-deliverable files/API data products.
5. **Analytics marts** — backend-prepared report/dashboard tables, indexes, and tiles.
6. **Reports/dashboards** — app and PDF/shareable artifacts that only render prepared data.

This directly addresses the prior frustration about reprocessing. If retained evidence exists, reprocessing should rebuild layers 3–6 without new paid collection unless the user explicitly chooses recollection.

Recommended operational rule:

- “Reprocess” means rebuild normalized observations, data products, marts, and report artifacts from retained raw snapshots and approved governance inputs.
- “Recollect” means make new paid upstream calls.
- The UI should never blur those two actions.

## Proximity module assessment

The proximity work is strategically important because location intelligence will power:

- geography creation;
- comp-group creation;
- Bulk Project scoping;
- Competitive Price Intelligence;
- market/white-space views;
- store-pair exports and downstream analytics.

Current backend strengths:

- default Walmart benchmark selection by country;
- nearest competitor relationships from location-master coordinates;
- radius summaries at 1, 3, 5, and 10 miles;
- forward Walmart-to-competitor pairs and reverse competitor-to-Walmart pairs;
- state, market, competitor-network, distance, and map-cluster summaries;
- clear methodology that distances are straight-line Haversine miles, not drive time or product distribution.

Current gaps:

- metrics still need stricter business framing: Walmart coverage, competitor-footprint opportunity, overlap, gap, and state/market denominators should be separate and clickable;
- white-space metrics should be competitor-footprint aware for regional retailers so H-E-B does not make non-Texas Walmart stores look like irrelevant gaps;
- map rendering/performance should rely on backend-prepared tiles/clusters/slices instead of pushing too much computation and too many points into the browser;
- controls, details, saved networks, notes, and exports should be consolidated into drawers/modals so the map remains primary;
- every metric card needs a top-right info control with calculation, denominator, source authority, freshness, and caveats.

Recommended proximity metric framework:

| Metric family | Primary question | Unit / denominator |
| --- | --- | --- |
| Walmart network coverage | What percent of Walmart stores have the selected competitor within the selected radius? | Walmart stores in active analysis scope. |
| Competitor-footprint coverage | Within the competitor’s operating footprint, how much Walmart overlap exists? | Walmart stores in states/markets where the competitor has mappable stores, or a governed competitor footprint definition. |
| Competitor-site adjacency | What percent of competitor sites have a Walmart within the selected radius? | Competitor stores in active analysis scope. |
| White-space from Walmart view | Which Walmart stores are outside the selected competitor radius? | Walmart stores in active scope, optionally competitor-footprint scoped. |
| White-space from competitor view | Which competitor stores do not have a Walmart within the selected radius? | Competitor stores in active scope. |
| Market concentration | Which states, markets, cities, ZIPs, or future DMA/CBSA groups concentrate overlap or gaps? | Store counts by selected geographic dimension. |
| Distance profile | What is the distribution of nearest-store distance? | Paired nearest relationships, with p50/p75/p90/max and outlier disclosure. |
| Network influence | Which competitor locations are nearest to the most Walmart stores? | Competitor stores and assigned Walmart nearest pairs. |

Recommendation on regional competitors: yes, competitor-footprint-aware white-space is worth it if the label is precise. For a regional retailer, the default white-space card should use “Walmart stores in competitor footprint outside radius” rather than “all Walmart stores outside radius.” The full national Walmart denominator can remain available as a secondary context metric, but it should not be the primary executive metric because it creates false alarm and damages trust.

## Reporting and analytics assessment

Current reporting has strong pieces but should be reorganized around durable data products and decision workflows.

Observed strengths:

- validated AnalysisResult and report artifacts exist;
- report materialization gates and publication lifecycle exist;
- canonical report workspaces include product, geography, brand, match, and data-quality drilldowns;
- evidence lineage and downloadable artifacts are already concepts in the system.

Observed risks:

- report pages have accumulated many tabs, special cases, and old phase-driven UX decisions;
- reports have previously shown technically accurate but misleading values when normalization context was not displayed intelligently;
- store-level “distribution” must be defined as product present in store-level search results with price greater than zero, not as a store-level in-stock indicator;
- broad summary rollups are less important to the user than comprehensive product-level wins/losses, Walmart broad-distribution products, and downloadable supporting evidence;
- the current report library and app sections do not yet make it obvious whether missing reports are a collection problem, reprocessing problem, publication gate problem, or entitlement/visibility problem.

Required reporting principles:

- report renderers consume prepared analytics; they do not calculate authoritative metrics;
- every price normalization must show pack/unit basis and suppress misleading normalized prices when the comparison is not valid for decision use;
- every comprehensive win/loss list should be complete within current filters, not just illustrative;
- every drilldown must expose source rows and downloadable CSV/XLSX/JSON when allowed;
- every metric must declare denominator, scope, calculation, source, freshness, and caveat.

## Bulk Projects assessment

The current Collections area is close to the technical foundation for Bulk Projects, but not yet the customer product.

What exists:

- definitions, versions, estimates, launch controls, run monitoring, geography resolution, queues, spend authorization, and recovery patterns.

What is missing for the customer product:

- plain-language project wizard organized around “what data do you need?” rather than implementation mechanics;
- saved input sets for keywords, product IDs, product URLs, geographies, and retailer groups;
- delivery destination management for email, SFTP, S3, Azure Blob, retrieval API, and in-app downloads;
- customer-visible run history and data manifests;
- entitlement-aware cadence, retailer, endpoint, and geography limits;
- clear “reprocess from retained evidence” versus “recollect” controls;
- reliable My Bulk Data page with generated files, schemas, checksums, expiration, and access logs.

## Live APIs assessment

The current repo has internal API routes and provider adapters, but no customer-grade CPGHero Live API surface yet.

Needed before Live API launch:

- account-scoped customer API keys with hashed storage, rotation, revocation, labels, scopes, and last-used metadata;
- per-key and per-account rate limits;
- endpoint-family entitlements;
- usage ledger tied to account, user/API key, endpoint, retailer, geography, credits, estimated cost, actual cost, and billable disposition;
- CPGHero-branded request/response contracts;
- public developer docs and playground that never reveal internal provider names, endpoints, credentials, or implementation details;
- async job pattern for high-latency or high-volume requests;
- customer-safe errors and support correlation IDs.

## Review Radar and Share of Search assessment

These modules are part of the approved north-star but not yet first-class customer experiences.

Recommended sequencing:

1. Build the shared platform foundation first: tenant/account model, projects, data products, entitlements, usage, and provider masking.
2. Productize Bulk Projects for SERP/PDP/REVI data feeds.
3. Expose app modules that consume those governed project datasets:
   - Share of Search from SERP observations;
   - Price Intelligence from SERP/PDP observations and matching;
   - Review Radar from REVI observations plus governed AI insight pipelines.

This prevents each module from inventing its own project, schedule, billing, export, and lineage model.

## Codebase cleanup assessment

The repo contains substantial historical material: phase docs, prompts, fixtures, reference outputs, source material, generated outputs, scripts, and old implementation notes. Some are valuable audit evidence; some are noise.

Do not delete broadly. Cleanup should be controlled by classification:

| Class | Examples | Action |
| --- | --- | --- |
| Active product code | `apps`, `packages`, `schemas`, `database`, `config`, current packs | Keep; refactor behind tests. |
| Active operational docs | current Platform Docs, current phase docs, architecture docs | Keep; consolidate and update. |
| Historical audit evidence | old phase records, retained validation docs, source manifests | Move to archive namespace or documentation vault if not needed in active developer context. |
| Reference outputs | sample HTML/XLSX reports | Keep only canonical examples; archive or delete duplicates after checksum inventory. |
| Scratch/obsolete artifacts | local generated files, duplicates, stale one-off scripts | Delete only after explicit inventory, owner review when material, and CI pass. |
| Generated contracts | TypeScript generated schemas | Keep generated by documented command; avoid hand edits. |

Recommended cleanup method:

1. create an inventory with file path, class, last modified commit, size, and references;
2. mark active versus archive candidates;
3. add repo structure rules so AI agents know where to work;
4. archive or remove only after tests and owner approval for material deletion;
5. add CI checks to prevent new scratch artifacts in active roots.

## Security assessment

Security is foundational, not a later polish phase.

Priority gaps:

- replace admin-password/session patterns with real identity, tenant membership, roles, and permissions;
- ensure all customer data queries are tenant-scoped;
- hash all customer API keys and show secret values only once;
- ensure upstream and AI provider secrets never enter prompts, browser bundles, logs, or artifacts;
- add customer-safe error handling and correlation IDs;
- separate internal/system-admin routes from customer routes at the API, UI, and navigation layers;
- audit exports, signed URLs, delivery connectors, and share links for entitlement and expiration controls;
- add provider-masking leak tests and secret redaction tests to CI.

## Performance assessment

Large datasets require backend-first product design.

Required performance direction:

- precompute report-ready marts and proximity/network slices in backend jobs;
- paginate every high-cardinality table and drawer;
- support CSV/XLSX/JSON exports from backend jobs, not browser-side full-data serialization;
- use map tiles/vector layers/clusters or precomputed viewport slices for location-heavy pages;
- cache immutable artifact reads by checksum;
- make filters server-addressable and URL-preservable;
- measure p50/p95 API latency and render latency for each major page.

Proximity-specific performance target:

- initial page should load summary cards and map shell quickly;
- map should request prepared clusters/tiles for the selected retailer, radius, scope, and viewport;
- detailed relationship rows should load on click or drawer open;
- radius change should not reset selected retailer, filters, or saved view state.

## Recommended implementation sequence

### Phase 14.02 — Platform terminology and visibility boundary

Goal: define the CPGHero-facing product language and provider-masking enforcement model.

Deliverables:

- update product boundary in `AGENTS.md`;
- classify routes/docs/contracts as customer-visible, internal-admin, or private implementation;
- add a customer-visible forbidden-term scan;
- add safe CPGHero names for endpoint families, credits, errors, and developer docs;
- document what internal provider-specific files are allowed and why.

Acceptance gates:

- provider brand does not appear in customer-visible route source, browser bundle, customer docs, exports, or API examples;
- internal adapter files remain functional;
- CI blocks future customer-visible leaks.

### Phase 14.03 — Tenant, account, role, and entitlement foundation

Goal: replace single-organization assumptions with a real access model.

Deliverables:

- account/workspace/user/membership/role/permission/entitlement schemas;
- auth principal resolution for customer and system-admin contexts;
- API dependency that enforces tenant scope;
- role-aware navigation model;
- audit log for security-sensitive actions;
- migration plan for the existing standalone organization.

Acceptance gates:

- route-level tests prove cross-account isolation;
- customer users cannot access system-admin routes;
- system-admin actions are audited;
- existing internal workflows still work under explicit system tenant scope.

### Phase 14.04 — Data product lifecycle and reprocessing UX

Goal: make collection, reprocessing, and reporting understandable and reliable.

Deliverables:

- explicit data lifecycle model in UI and API: request ledger, raw snapshots, normalized observations, project datasets, marts, reports;
- “Reprocess retained evidence” workflow;
- “Recollect new data” workflow with separate approval and cost estimate;
- run status explanations that show whether a problem is collection, normalization, analysis, publication, or entitlement;
- My Data / artifact library backend contract.

Acceptance gates:

- retained evidence can regenerate reports without paid collection;
- UI never labels retained-evidence reprocessing as new collection;
- report library explains empty states with actionable root cause.

### Phase 14.05 — Bulk Projects v2

Goal: turn Collections into a customer-grade Bulk Projects product.

Deliverables:

- project wizard for SERP/PDP/REVI inputs;
- saved inputs, geographies, comp groups, schedules, estimates, approvals;
- delivery-destination model and app-download destination;
- run history, file manifests, schema versions, checksums;
- account usage and billing views.

Acceptance gates:

- customer can create, estimate, approve, launch, monitor, and download a small project without developer help;
- all usage is account/project/key attributable;
- delivery logs are customer-safe.

### Phase 14.06 — Live API façade

Goal: expose CPGHero-branded APIs without exposing the upstream provider.

Deliverables:

- API-key management;
- endpoint-family auth and entitlement checks;
- CPGHero Search/Product Detail/Reviews endpoints;
- usage metering and rate limiting;
- customer-safe error and status contracts;
- docs/playground.

Acceptance gates:

- no provider names or implementation details in public docs/API responses;
- per-account and per-key quotas enforce correctly;
- usage ledger reconciles requests, credits, and billable outcomes.

### Phase 14.07 — Geography and Comp Groups productization

Goal: make location intelligence a reusable platform asset.

Deliverables:

- saved Geographies and Comp Groups;
- proximity explorer backed by reusable relationship sets;
- competitor-footprint-aware metrics;
- backend-prepared map clusters/tiles and relationship drawers;
- exportable store-pair and store-list details.

Acceptance gates:

- regional competitors use competitor-footprint-aware white-space by default;
- all proximity cards disclose calculation and denominator;
- radius and retailer changes preserve state correctly;
- map performance meets measured p95 target.

### Phase 14.08 — Analytics module rationalization

Goal: redesign reporting tabs/pages around decision workflows instead of accumulated report versions.

Deliverables:

- Price Intelligence and Competitive Intelligence module taxonomy;
- complete wins/losses lists under filters;
- product/store/location drilldowns with downloads;
- intelligent price-normalization presentation;
- module-level filter drawer and saved views;
- PDF/share export only after app reporting is trustworthy.

Acceptance gates:

- no misleading normalized values in executive views;
- every win/loss row can be traced to source evidence;
- broad-distribution Walmart products are easy to identify;
- drawer downloads reconcile with displayed counts.

### Phase 14.09 — Share of Search and Review Radar foundations

Goal: add the next premium app modules on top of the shared project/data lifecycle.

Deliverables:

- SERP keyword performance/share-of-search marts;
- sponsored/organic visibility metrics;
- review collection project type;
- Review Radar sentiment/aspect data model and AI governance;
- module-specific dashboards.

Acceptance gates:

- modules consume governed project datasets rather than bespoke raw imports;
- AI outputs are explainable, cited, and separated from deterministic metrics.

## Near-term work order

Recommended immediate sequence:

1. merge this audit artifact;
2. implement Phase 14.02 provider masking and product-boundary classification;
3. implement Phase 14.03 tenant/account/RBAC foundation before exposing customer surfaces;
4. continue Proximity only as part of Phase 14.07 so its metrics, backend data products, and UX align with the platform model;
5. then productize Bulk Projects and Live APIs.

This order may feel slower than page polishing, but it prevents the app from accumulating more mismatched surfaces.

## Questions that should remain explicit

These are not blockers for Phase 14.02, but they should be resolved before customer launch:

1. Which identity provider should back customer login: managed auth provider, custom auth, enterprise SSO later, or staged migration?
2. Are workspaces needed at launch, or can accounts own projects directly until larger agencies/brokers need workspace segmentation?
3. What are the first customer-visible delivery destinations: app download only, email link, SFTP, S3, Azure Blob?
4. Should CPGHero expose Live APIs before Bulk Projects, or should Live APIs stay internal until Bulk Projects and data lifecycle are stable?
5. What customer roles are required on day one beyond Account Owner, Account Admin, Project Owner, Analyst, Viewer, Developer, and Billing?
6. Which historical docs/artifacts are legally or operationally required to retain in the active repo versus archive storage?
7. What p95 page-load and API-latency targets should become release gates for each major module?

## Definition of done for Phase 14 platform foundation

The foundation should not be considered ready until:

- customer-visible surfaces consistently say CPGHero and never expose upstream provider implementation;
- tenant/account/user/role/entitlement checks are enforced by default;
- usage and billing are attributable to account, project, user/API key, endpoint, retailer, and run;
- retained-evidence reprocessing is a first-class workflow;
- Bulk Projects, Live APIs, and App Analytics share the same data lifecycle;
- internal IP surfaces are hidden from ordinary customer roles;
- every major metric has denominator, calculation, source, freshness, and caveat disclosure;
- reports and maps load quickly from backend-prepared data products;
- the active repo is materially quieter and has clear archive boundaries for old work.

