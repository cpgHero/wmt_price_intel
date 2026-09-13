# Phase 14.00 — CPGHero platform vision and operating blueprint

## Purpose

This document aligns the product, architecture, security, data, and user-experience direction before additional page-level development continues. It is a planning and governance artifact, not a claim that every capability below is already implemented.

The product should be treated as a secure, multi-tenant retailer data and intelligence platform. Walmart price intelligence remains an important advanced analytics module, but it is not the full product boundary.

## North-star product definition

CPGHero is a retailer data platform that lets brands, brokers, agencies, and internal operators collect, govern, deliver, analyze, and visualize retailer data at scale. The platform is powered by upstream retailer-data APIs, but customers experience the service as CPGHero.

The platform has three commercial surfaces:

1. **Live APIs** — CPGHero-branded customer API access for teams that want to self-manage ingestion and downstream use. Customer traffic is authenticated, metered, rate-limited, permissioned, billed, and routed through CPGHero-controlled provider credentials.
2. **Bulk Projects** — scheduled collection projects where customers define inputs, geography, source retailers, cadence, and delivery destinations. Outputs can be delivered as files, retrieved by API, or downloaded inside the app.
3. **CPGHero App Analytics** — premium analytics and reporting experiences powered by collected project data and CPGHero-governed intelligence layers such as discovery, Product Packs, matching, proximity, share of search, price intelligence, and review analysis.

The same collected evidence can power more than one commercial surface when the account has the right entitlement. A customer may only buy bulk files, only use app analytics, or use both.

## Product principles

- **Provider masking is mandatory.** Customer-facing UI, docs, URLs, browser bundles, exported files, API responses, webhook payloads, email content, support screenshots, and customer-visible logs must not expose the upstream provider brand, credentials, endpoints, request schema, or billing mechanics. Customer-facing language should use CPGHero names such as CPGHero Live API, CPGHero Search, CPGHero Product Detail, CPGHero Reviews, and CPGHero Collection Credits.
- **Raw evidence is immutable.** Every successful provider response is stored as a raw snapshot with tenant, project, request, source, timestamp, billing, and lineage metadata. Corrections, normalization, exports, and reporting create derived versions; they do not mutate raw evidence.
- **Store-level context is foundational.** PDP and SERP evidence should preserve retailer, store or service-area context, geography input, query/product input, timestamp, and raw-response lineage. Store-level presence, price, rank, sponsorship, and review context must never be generalized without explicit methodology.
- **Backend-first performance.** The browser should explore prepared summaries, indexes, pages, tiles, and drill-down records. It should not compute large joins, brute-force pairings, or load complete raw datasets just to render one view.
- **Multi-tenancy and security are product foundations, not future polish.** Tenant isolation, role-based access, audit trails, usage limits, encryption, and secret containment must be designed into every workflow.
- **Internal IP remains internal.** Discovery, Product Packs, matching governance, Product Pack normalization, certification, and advanced report-generation logic are CPGHero-owned IP. Customers can benefit from these systems through entitled app experiences, but ordinary customers should not directly administer them.
- **Every metric must disclose its denominator and source authority.** The platform must make it obvious what is counted, what is excluded, what evidence source owns the value, and whether a metric is product, store, ZIP/service-area, geography, tenant, or project scoped.
- **Reprocessing should be simple.** If data has already been collected, the platform should be able to regenerate normalized datasets, exports, and reports from retained evidence without new paid collection unless the user explicitly asks to recollect.

## Commercial surfaces

### 1. Live APIs

The Live API surface serves customers who want direct, programmatic access to retailer data but do not want to manage the upstream provider contract or credentials.

Required capabilities:

- Customer API-key creation, rotation, revocation, and scoped permissions.
- Account-level quotas, per-key quotas, rate limits, cooldowns, and budget ceilings.
- Request validation and cost estimation before execution when practical.
- Internal routing to provider APIs using CPGHero-owned provider credentials only.
- Provider response normalization into CPGHero response contracts.
- Customer-facing errors that never expose provider names, credentials, or raw upstream implementation details.
- Usage ledger by account, user, API key, endpoint family, retailer, request type, geography, timestamp, credits, estimated cost, actual cost, and billable disposition.
- Developer docs and playground for CPGHero-branded endpoints.
- Webhook or polling support for asynchronous request families when latency is too high for synchronous response.

Baseline endpoint families:

- Search/SERP collection.
- Product detail/PDP collection.
- Reviews/ratings collection.
- Collection status and retrieval.
- Optional future analytics endpoints, only after governance and entitlements are mature.

### 2. Bulk Projects

Bulk Projects serve customers who want CPGHero to manage repeatable collection and delivery.

Required capabilities:

- Project creation wizard with validated inputs:
  - retailers/sources;
  - endpoint family: SERP, PDP, REVI, or combined workflows;
  - keywords, product IDs, product URLs, or review targets;
  - geography/location sets;
  - collection cadence;
  - schedule window, timezone, and recurrence;
  - output schema and file format;
  - delivery destination;
  - budget and rate-limit guardrails.
- Project drafts, estimates, approvals, launches, pauses, resumes, cancellations, and revisions.
- Immutable project versions so old runs remain reproducible.
- Run monitoring with queued, running, completed, failed, skipped, retried, billable, and non-billable counts.
- Delivery targets:
  - app download;
  - retrieval API;
  - email attachment or link;
  - SFTP;
  - S3;
  - Azure Blob;
  - future destinations through connector-style adapters.
- Customer-visible delivery logs and system-admin-visible provider logs.
- File manifests with schema version, source, project, run, row count, checksum, generated time, and expiration.
- Optional enablement of the same project data for app analytics if the account has that entitlement.

### 3. CPGHero App Analytics

The app analytics surface turns collected project data into decision-grade workflows.

Core analytics modules:

- **Price Intelligence** — one-retailer pricing, product architecture, store-level observed distribution, product mix, and pricing exceptions.
- **Competitive Price Intelligence** — Walmart or future benchmark retailer versus competitor price position, store/radius comparisons, product matching, cohort views, assortment context, and executive reporting.
- **Keyword Performance and Share of Search** — SERP rank, organic/sponsored visibility, share of search, competitor sponsorship, price position within search, and keyword/store/retailer trend monitoring.
- **Review Radar** — review and rating collection transformed into sentiment, aspect analysis, issue detection, opportunity detection, and Voice-of-Customer narration.
- **Proximity and Comp Groups** — location-master workflows for defining retailer geography, Walmart-versus-competitor proximity, competitive radius, white-space, and project-ready store relationships.
- **Data Quality and Trust** — readiness, source freshness, collection failure reasons, schema drift, provider anomalies, evidence lineage, and blocked-publication issues.

App analytics should not be implemented as one-off reports. It should consume governed project data assets, reporting marts, and reusable drill-down APIs.

## User and account model

### Tenant hierarchy

The platform should use a strict tenant hierarchy:

- **System** — CPGHero-owned operational tenant with system-wide administration.
- **Account** — customer organization, agency, broker, or internal team.
- **Workspace** — optional account subdivision for teams, brands, clients, or business units.
- **Project** — collection and/or analytics configuration.
- **Artifact** — raw snapshots, normalized datasets, exports, reports, dashboards, notebooks, and share links.

Every persisted row, object, export, audit event, and asynchronous job must have tenant/account ownership or an explicit system-admin scope.

### Role families

Suggested initial roles:

| Role | Primary user | Key permissions |
| --- | --- | --- |
| System owner | CPGHero owner | Full platform configuration, tenant management, provider credentials, billing policy, Product Pack governance, emergency controls. |
| System admin | CPGHero operator | Customer support, account setup, run monitoring, recovery, data-quality triage, selected governance workflows. |
| System analyst | CPGHero analyst | Internal analytics, Product Pack/matching review if granted, report validation, read-only operational evidence. |
| Account owner | Customer executive/admin | Contract-level settings, users, API keys, entitlements, billing reports, all account projects. |
| Account admin | Customer admin | User management, project management, delivery settings, API-key management if granted. |
| Project owner | Customer operator | Create/manage assigned projects, approve estimates, view outputs and analytics for assigned projects. |
| Analyst | Customer analyst | Explore reports, download permitted evidence, create saved views, no budget-affecting actions unless granted. |
| Viewer | Customer reader | View shared reports/dashboards, limited export if granted. |
| Developer | Customer engineer | API keys, playground, docs, usage logs, integration diagnostics. |
| Billing user | Customer finance/admin | Usage, invoices, credit consumption, billing exports, no data-content access unless separately granted. |

Role design should support composable permissions rather than only hard-coded role names. Example permission groups: `users.manage`, `api_keys.manage`, `projects.create`, `projects.approve_paid_run`, `exports.download`, `analytics.view`, `analytics.share`, `system.provider_admin`, `system.product_pack_admin`.

### Entitlements

Accounts should have explicit entitlements by commercial surface and feature:

- Live API access.
- Bulk Project access.
- App Analytics access.
- Endpoint families: SERP, PDP, REVI.
- Retailer/source access.
- Delivery destinations.
- Advanced IP modules: Product Packs, matching/certification, Review Radar, Share of Search, Competitive Intelligence.
- Maximum frequency, maximum monthly credits, max locations per project, max retained history, max users, max API keys.

Entitlements should be checked before both UI rendering and API execution.

## Data domain model

The target model should make data flow simple and auditable.

### Core entities

- **Account / user / role / entitlement / API key.**
- **Retailer source** — CPGHero-facing retailer definition, endpoint support, country support, location behavior, rate-limit class, and visible customer capabilities.
- **Provider adapter** — internal-only implementation that maps CPGHero request contracts to upstream provider requests and maps responses back into CPGHero raw/normalized contracts.
- **Location master** — retailer locations, store IDs, ZIP/postal codes, country, state/province, city, coordinates, source lineage, active/catalogued flags, and version.
- **Geography** — a reusable customer- or system-defined list of locations or service areas for collection.
- **Comp group** — reusable relationship set between a benchmark retailer and competitor retailers, usually generated from proximity rules and location master evidence.
- **Project** — customer-defined or system-defined collection/reporting configuration.
- **Collection definition** — immutable project version containing inputs, cadence, geography, endpoint family, retailer set, destination, and budget policy.
- **Run** — execution instance of a collection definition.
- **Task/request** — atomic provider-call unit with request hash, provider adapter, store/geography context, endpoint type, retry lineage, and billing outcome.
- **Raw snapshot** — immutable upstream response payload plus request, timing, status, cost, and lineage.
- **Normalized observation** — typed row derived from a raw snapshot, such as product offer, search result, rank, sponsorship, review, rating, or product attribute.
- **Data product** — packaged dataset, API feed, analytical mart, report-ready document, or export.
- **Analytics artifact** — app dashboard, report, PDF, share link, saved view, drill-down, or downloadable evidence file.

### Evidence layers

| Layer | Purpose | Mutability |
| --- | --- | --- |
| Request ledger | Planned and executed API calls, billable accounting, retry lineage. | Append-only. |
| Raw snapshots | Exact source payloads and provider response metadata. | Immutable. |
| Normalized observations | CPGHero-standard SERP/PDP/REVI records. | Versioned derivation. |
| Project datasets | Customer-ready data products and delivery files. | Versioned output. |
| Analytics marts | Backend-prepared summaries for app modules. | Rebuildable from retained evidence. |
| Reports/dashboards | Reader-facing narratives and visualizations. | Versioned artifact. |

## Collection workflows

### SERP / Search

Inputs:

- retailer/source;
- keyword;
- store/location or service-area geography;
- page/depth options if supported;
- collection timestamp and recurrence.

Must preserve:

- keyword;
- rank/order;
- sponsored/organic status when available;
- product identifiers and URLs;
- listed price and promotion fields;
- store/location context;
- raw response lineage;
- provider error and retry metadata.

Primary analytics:

- keyword performance;
- share of search;
- sponsor visibility;
- pricing in search context;
- product discovery/noise filtering;
- observed store-level product distribution when exact product appears with positive price in store-level search results.

### PDP / Product Detail

Inputs:

- retailer/source;
- product ID or URL;
- store/location or service-area geography when supported;
- recurrence.

Must preserve:

- product identity;
- title, brand, images, package details, price, seller, fulfillment, badges, and availability-like fields with source caveats;
- store/location context;
- raw response lineage.

Primary analytics:

- catalog monitoring;
- PDP enrichment;
- seller governance;
- product attribute extraction;
- price monitoring;
- Product Pack support.

### REVI / Reviews

Inputs:

- retailer/source;
- product ID or URL;
- review depth/date/rating filters when supported;
- recurrence.

Must preserve:

- review ID or stable hash;
- rating;
- title/body;
- date;
- verified/badge fields if available;
- helpfulness;
- variant/product context;
- raw response lineage.

Primary analytics:

- rating trends;
- review volume;
- sentiment;
- aspect extraction;
- issue/opportunity detection;
- Voice-of-Customer narration through Review Radar.

## Geography and comp groups

### Geography

A geography is a reusable list of retailer locations or service areas used to define collection scope. It should support:

- upload/import from CSV, spreadsheet, app selection, API, or location master filters;
- validation against retailer location master;
- de-duplication without converting IDs to numbers;
- versioning and checksum;
- preview of location counts by retailer, country, state/province, DMA/CBSA when governed sources are available, and location type;
- export in provider-ready and customer-readable forms;
- permissioning by account/workspace/project.

### Comp groups

A comp group is a reusable relationship set used to drive competitive collection and reporting. For Walmart competitive intelligence, it usually represents Walmart locations matched to nearby competitor locations by retailer and radius.

It should support:

- benchmark retailer, competitor retailer(s), country, radius, and scope;
- state/province footprint and future DMA/CBSA/trade-area scopes only when the source is governed;
- nearest-neighbor relationships;
- all-competitors-within-radius relationships;
- relationship version, source location-master version, and distance methodology;
- downloadable store-pair details;
- reuse by Bulk Projects and Analytics.

Important boundary: Proximity and comp groups are location-network evidence. They do not prove inventory, assortment, price, product availability, or sales opportunity until joined to collected product/search/review evidence.

## Reporting and analytics architecture

The app should move toward a reusable analytics architecture:

1. Project data is collected and retained.
2. Raw snapshots are normalized into typed observations.
3. Project datasets are materialized for delivery and retrieval.
4. Analytics marts are prepared by backend workers for large-scale views.
5. App pages query thin APIs for summaries, paginated details, map tiles, and drill-downs.
6. Reports/PDFs consume immutable report datasets; they do not recalculate metrics in renderers.

### Reporting modules

| Module | Main job | Data required |
| --- | --- | --- |
| Price Intelligence | Understand retailer product price architecture and store-level observed distribution. | SERP and/or PDP observations, product identity, Product Pack rules. |
| Competitive Price Intelligence | Compare benchmark and competitor products by governed product relationship and local geography. | SERP/PDP observations, Product Packs, certified/derived matches, comp groups. |
| Keyword Performance | Track rank, paid/organic visibility, sponsor activity, and price position in search. | SERP observations by keyword/store/time. |
| Share of Search | Quantify brand/product visibility across keyword sets and geography. | SERP observations, brand/product identity, keyword groups. |
| Review Radar | Convert reviews into customer sentiment, issues, praise, and emerging themes. | REVI observations, AI analysis, product taxonomy. |
| Proximity | Define and explore retailer location relationships and competitive footprints. | Location master and comp group relationships. |
| Data Quality | Show readiness, gaps, source anomalies, collection failures, and lineage. | Request ledger, raw snapshot metadata, normalization results, readiness checks. |

## User experience vision

The UX should feel like a modern intelligence command center, not a collection of admin tables.

### UX principles

- **One clear job per page.** Avoid tabs that exist because data exists. Pages should map to user decisions.
- **Progressive disclosure.** Show the executive answer first, then allow drill-down to evidence, store lists, products, raw rows, and methodology.
- **Fast first paint.** Use backend-prepared summaries so pages become useful quickly even when details are still loading.
- **Drawers over deep scrolling.** Use modals/drawers for filters, store lists, method notes, exports, and row evidence when they would otherwise push core analysis off screen.
- **Filters must be trustworthy.** Every filter should update the same row set, charts, KPIs, downloads, and share links.
- **Every clickable analytical card needs reset.** Drill-down views should show the active selection and provide an obvious return path.
- **Downloadable evidence accompanies important metrics.** If a KPI references stores, products, reviews, keywords, or competitor relationships, a permitted user should be able to inspect and export the underlying list.
- **Definitions live where confusion occurs.** Info icons should explain calculations, denominators, data source, caveats, and what the metric is not.
- **Role-specific navigation.** Bulk-only customers should not see internal Product Pack governance; analytics users should not be forced through provider-oriented setup; system admins need operational detail ordinary users should never see.

### Recommended navigation model

Top-level product areas:

- Home
- Live APIs
- Bulk Projects
- Analytics
- Data Library
- Geography & Comp Groups
- Developer Docs
- Account Admin
- System Admin

Analytics subareas:

- Price Intelligence
- Competitive Intelligence
- Keyword Performance
- Share of Search
- Review Radar
- Proximity
- Data Quality

System-admin-only subareas:

- Product Packs
- Retailer/source packs
- Discovery governance
- Matching/certification
- Provider operations
- Cost and usage reconciliation
- Platform docs

## Security and masking requirements

### Provider masking

The app should implement a provider-abstraction boundary:

- Customer-facing contract names are CPGHero-owned.
- Frontend code imports CPGHero concepts only.
- Browser bundles must not contain upstream provider URLs, keys, docs links, brand names, endpoint names, or error strings.
- Server logs exposed to customers must use CPGHero request IDs and normalized error codes.
- Internal provider details may exist only in backend adapter modules, internal configuration, restricted logs, and system-admin documentation.
- Customer exports should include CPGHero source names and lineage IDs, not upstream-provider implementation labels.

Suggested public naming:

- CPGHero Search API.
- CPGHero Product Detail API.
- CPGHero Reviews API.
- CPGHero Collection API.
- CPGHero Collection Credits.
- CPGHero Retailer Source.
- CPGHero Location ID, with optional retailer-native store ID when appropriate.

### Multi-tenant security

Minimum requirements:

- Row-level account/workspace/project scoping in every API and worker path.
- Object-storage keys partitioned by tenant/account/project with signed access generated only after authorization.
- Separate internal provider credential storage from customer API keys.
- API keys hashed at rest and shown only once.
- Per-key scope, expiration, and rotation.
- Audit events for login, user management, API-key changes, entitlement changes, project approvals, paid run launches, delivery changes, exports, report shares, and system-admin overrides.
- Principle-of-least-privilege service roles.
- No customer-visible stack traces.
- PII/secrets redaction in logs and AI prompts.
- Explicit data-retention and deletion policy by account and artifact type.
- Security review for any connector that delivers files outside the app.

## Performance architecture

Large datasets should be handled through prepared backend assets:

- Postgres for control plane, queueing, tenancy, identities, and audit.
- Object storage for raw snapshots and large immutable artifacts.
- Parquet for normalized analytical datasets and delivery-ready files.
- DuckDB/Polars workers for derivation, validation, and report marts.
- Precomputed summaries for dashboard KPIs, maps, rankings, and filters.
- Paginated and cursor-based APIs for row detail.
- Server-side search/filter indexes for large tables.
- Map tiles or bounded clusters for geospatial views.
- Async jobs for heavy exports and report regeneration.
- Cache keys tied to immutable project/run/report versions.

Browser payload budgets should be explicit. A page should not receive a full raw dataset when it only needs a summary plus a drill-down API.

## Billing, usage, and cost controls

Because CPGHero pays for upstream provider usage, cost control is a core platform feature.

Required ledgers:

- Customer request ledger.
- Internal provider request ledger.
- Credit/cost ledger.
- Estimate ledger.
- Approval ledger.
- Retry and recovery ledger.

Controls:

- pre-run estimates;
- customer approval for paid bulk launches;
- monthly account quota;
- project quota;
- API-key quota;
- endpoint-specific rate limits;
- max frequency;
- max locations per project;
- cooldowns after provider rate limits;
- automatic pausing on budget breach;
- billable/non-billable classification;
- administrator override with reason.

Customer-facing usage should expose CPGHero billing units. Internal reconciliation can map those units to provider cost.

## Trust and data quality model

Every project and report should have a trust status:

- Ready.
- Ready with caveats.
- Limited evidence.
- Needs attention.
- Blocked.

Common trust checks:

- request completion;
- raw response retention;
- schema validation;
- source freshness;
- geography completeness;
- duplicate identities;
- zero/missing price handling;
- seller eligibility;
- store versus service-area distinction;
- Product Pack classification;
- match/certification status;
- report denominator reconciliation;
- export row-count/checksum reconciliation.

AI may summarize, classify, draft, and narrate, but deterministic code must own authoritative counts, prices, medians, rankings, distances, denominators, rates, billing, and eligibility gates.

## KPI framework

### Platform-level KPIs

| KPI | Definition | Why it matters |
| --- | --- | --- |
| Trusted data delivery rate | Share of scheduled runs that complete, validate, and deliver within SLA. | Measures whether CPGHero can be relied on as a data feed. |
| Report-ready evidence rate | Share of analytics-enabled projects whose data passes readiness gates for the intended report. | Connects collection quality to app value. |
| Time to first value | Time from account setup to first successful API call, delivered file, or useful analytics view. | Measures onboarding and UX effectiveness. |
| Cost-to-serve per billable unit | Internal provider and infrastructure cost divided by customer-billable usage. | Protects margins and pricing. |
| Trust incident rate | Count of material metric, lineage, delivery, security, or tenant-isolation defects per period. | Protects credibility. |

### Driver metrics

- API success rate by endpoint family and retailer.
- Median and P95 API latency.
- Queue wait time.
- Collection task throughput.
- Delivery success rate by destination type.
- Reprocessing time from retained evidence.
- Percent of reports with complete denominator/source definitions.
- Percent of customer-visible errors mapped to safe CPGHero error codes.
- Percent of browser views under payload and render-time budgets.

### Guardrail metrics

- Provider credential exposure incidents: target zero.
- Cross-tenant access defects: target zero.
- Customer-visible provider-brand leakage: target zero.
- Unapproved paid-call execution: target zero.
- Raw snapshot mutation after successful collection: target zero.
- Reports with unsupported authoritative metrics: target zero.
- API-key requests exceeding contracted limits: blocked or throttled, not silently allowed.

## Recommended implementation sequence

### Required evaluation before implementation

Before new customer-facing development resumes, run a focused platform audit against the current codebase and data model. The audit should produce a keep/change/remove map rather than another broad narrative.

Audit workstreams:

1. **Customer-visible masking audit**
   - Search frontend code, browser bundles, API responses, OpenAPI docs, exported files, public documentation, logs visible through the app, and error messages for upstream-provider references.
   - Classify every finding as:
     - allowed internal-only reference;
     - must be renamed before customer exposure;
     - must be moved behind a backend adapter boundary;
     - must be removed.
   - Add an automated leakage check for customer-visible assets.

2. **Multi-tenant readiness audit**
   - Inventory every table, object-storage path, API route, worker job, export, report, and admin page.
   - Identify which entities already have account/project scope and which still assume global/system scope.
   - Define migration path for tenant/account/workspace/project ownership.
   - Add negative authorization tests for cross-tenant access.

3. **Data lifecycle audit**
   - Map current flows into request ledger, raw snapshot, normalized observation, project dataset, analytics mart, and report artifact layers.
   - Identify any renderer or browser path that recalculates authoritative metrics.
   - Identify any process that recollects when it should reprocess retained evidence.
   - Define canonical reprocessing jobs for normalized datasets, exports, and reports.

4. **Codebase simplification audit**
   - Identify obsolete branches, archive folders, superseded report builders, duplicated components, scratch files, and old fixtures.
   - Separate active product code from historical reference material.
   - Preserve audit-critical history through git and documented release records, not active runtime clutter.
   - Remove or quarantine noise only after target ownership and recovery path are clear.

5. **UX/navigation audit**
   - Re-map every current page to one of the target product areas: Live APIs, Bulk Projects, Analytics, Data Library, Geography & Comp Groups, Developer Docs, Account Admin, or System Admin.
   - Remove duplicate tabs and views that answer the same decision poorly.
   - Identify pages that should become drawers, admin-only workflows, or reusable components.
   - Define page payload budgets and performance targets.

6. **Security and delivery audit**
   - Review API-key storage, provider credential handling, signed URLs, file delivery destinations, export authorization, and log redaction.
   - Identify which delivery methods can safely launch first.
   - Define audit events required for every external data movement.

Audit deliverables:

- target information architecture;
- tenant/security migration plan;
- provider-masking leakage inventory;
- active versus obsolete code map;
- core domain model;
- implementation backlog with phases, acceptance criteria, and test gates.

Do not use the audit as a reason to stop all value delivery. Use it to prevent additional development from deepening the wrong architecture.

### Phase A — Foundation alignment and cleanup

Goal: remove ambiguity before new feature work.

- Establish target domain model and terminology.
- Define customer-facing CPGHero API names and internal provider adapter boundary.
- Inventory provider references in customer-visible frontend bundles, docs, exports, API responses, and logs.
- Inventory old/archive/confusing code and classify as keep, migrate, archive outside active tree, or delete after approval.
- Define account, tenant, role, entitlement, and API-key model.
- Define billing/usage ledger model.
- Create explicit current-state versus target-state docs.

Exit criteria:

- No new user-facing work starts without mapping to Live API, Bulk Project, App Analytics, Geography/Comp Group, Admin, or Data Quality.
- Provider masking policy is documented and testable.
- Security/tenant model has an implementation plan.

### Phase B — Control plane

Goal: create the platform skeleton all surfaces depend on.

- Tenant/account/workspace/user/role/permission schema.
- Account admin and system admin surfaces.
- API-key management.
- Entitlements.
- Audit log.
- Usage and budget policy.
- Safe customer-facing error catalog.

Exit criteria:

- Every request can be authorized by account/workspace/project.
- Every paid action can be attributed and audited.

### Phase C — Collection and delivery plane

Goal: make Bulk Projects and Live APIs reliable, masked, and billable.

- CPGHero-branded request contracts for Search, Product Detail, Reviews, and Collection.
- Internal provider adapters.
- Project definition/version model.
- Estimate/approval/run lifecycle.
- Delivery adapters.
- Data retrieval API and My Bulk Data page.
- Immutable raw snapshot and normalized observation storage.

Exit criteria:

- A customer can create a project, approve estimated usage, run collection, receive files, and view usage without seeing provider details.

### Phase D — Data products and analytics marts

Goal: make collected data reusable for app analytics.

- Normalize SERP/PDP/REVI into durable schemas.
- Materialize project-level data products.
- Build backend-prepared analytics marts.
- Create source/readiness gates.
- Support reprocessing from retained evidence without new provider calls.

Exit criteria:

- The same project run can produce customer files and power at least one analytics module.

### Phase E — Premium analytics modules

Goal: ship world-class app experiences on top of the foundation.

Suggested order:

1. Price Intelligence and Competitive Price Intelligence, because the current work is closest to production and proves store-level pricing value.
2. Geography and Comp Groups, because they are required inputs for competitive collection and many future location-aware workflows.
3. Keyword Performance and Share of Search, because SERP collection is already central and commercially intuitive.
4. Review Radar, because REVI plus AI insight is a differentiated but separate analysis lane.
5. Executive report/PDF/share workflows after app analytics are stable.

Exit criteria:

- App analytics pages are fast, drillable, downloadable, source-backed, and role-aware.

## Immediate next decisions

Before implementation resumes, the owner should approve or revise these decisions:

1. Should CPGHero be treated as the master public brand for all API, app, file, and report surfaces? Recommended: yes.
2. Should ordinary customers ever see or configure Product Packs, discovery, or matching? Recommended: no; expose outcomes and evidence, not governance internals.
3. Should Live APIs and Bulk Projects share the same usage ledger and billing units? Recommended: yes.
4. Should Bulk Project data be optionally enabled for App Analytics by entitlement? Recommended: yes.
5. Should provider names be allowed in internal system-admin docs and backend adapter names? Recommended: yes internally, but never in customer-visible assets or browser bundles.
6. Should Walmart remain the first benchmark retailer while preserving future benchmark-retailer support? Recommended: yes.
7. Should PDF/share exports wait until app views and data trust flows are stable? Recommended: yes.

## Risks to manage

- Existing code and docs contain historical assumptions from a Walmart-first competitive reporting product. Those assumptions must be separated from the broader CPGHero platform model.
- Provider masking will likely require both naming cleanup and build/runtime leakage checks.
- Multi-tenant access cannot be safely bolted on after analytics pages assume global data.
- Large analytics pages will regress if row-level payloads are sent to the browser without server-prepared summaries.
- Customer file delivery increases security risk because data leaves the app boundary.
- AI-generated insights can harm trust if deterministic metric authority and source lineage are not obvious.

## Open questions

- What account types and pricing packages should exist at launch?
- Which delivery destinations are required for the first commercial release?
- Which retailers and endpoint families are included in the first customer-facing Live API release?
- What are the initial default credit prices, quotas, and overage policies?
- What data-retention terms are promised by contract?
- Which authentication provider should own production login and enterprise SSO?
- What compliance posture is required for first customers?
- What customer-visible SLA should Bulk Projects promise?
- What is the minimum viable Review Radar release: sentiment only, aspect analysis, or narrated executive themes?
- What customer-facing brand terms should replace every provider-facing term?

## Working conclusion

The highest-quality path is to stop optimizing isolated report pages and instead build the platform around reusable governed project data. Live APIs, Bulk Projects, and App Analytics should share the same tenant, usage, collection, storage, normalization, delivery, and trust foundations. Advanced analytics should be a premium layer on top of those foundations, not a parallel implementation.

The next implementation plan should begin with control-plane and masking foundations, then collection/delivery, then analytics modules. That sequence protects trust, security, cost, and performance while preserving the value of the reporting work already developed.
