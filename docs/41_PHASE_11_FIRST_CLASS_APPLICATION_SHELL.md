# Phase 11 — First-Class Application Shell and Intelligence Navigation

## Objective

Move the working application from a horizontal website-style header into a responsive,
dashboard-style application shell without changing analytical calculations, evidence contracts,
queue behavior, paid-provider behavior, or existing deep links.

The navigation prototype is inspiration for visual hierarchy and interaction patterns. The live
repository remains the source of truth for which destinations are operational.

## Intelligence module boundary

Price Monitoring and Competitive Intelligence are separate user workflows over a shared
product/location foundation.

### Price Monitoring / Price Intelligence

Answers questions about a retailer's own products across its location distribution and over time:

- What price is this product selling for at each location?
- How broad is each observed price point?
- Where does the same product vary in price?
- What changed since the prior observation?
- Where are promotions, anomalies, or stale observations present?

Its primary grains are:

- retailer product × retailer location × observation time;
- product × geographic rollup × period;
- retailer/location distribution × price state.

It does not require a cross-retailer product match to be useful.

### Competitive Product Intelligence

Answers questions about comparable benchmark and competitor products at corresponding store
footprints:

- Which products are the same or sufficiently similar under a governed comparison basis?
- At which benchmark stores is the competitor lower, at parity, or higher?
- Which assortments, brands, cohorts, or geographies drive the result?
- Which matches need human review and which source evidence supports the conclusion?

Its primary grains are:

- governed product relationship × comparison basis;
- product relationship × overlapping store footprint;
- benchmark store × eligible competitor location × observed price evidence.

### Shared foundation, separate experiences

Both modules reuse:

- retailer/product identity;
- Product Packs and Retailer Packs where applicable;
- canonical location/store identity;
- immutable Search price observations;
- PDP identity and attribute enrichment;
- price normalization and unit economics;
- time/freshness semantics;
- maps, product cards, tables, evidence drawers, and exports;
- data-quality, provenance, permission, entitlement, and usage primitives.

They must not share authoritative comparison outputs. Price Monitoring owns observed price/location
facts and time-series summaries. Competitive Intelligence consumes those facts plus governed
matching and store-correspondence rules to create comparative outcomes.

## Navigation policy

The shell shows only usable destinations. Future module names are not rendered as disabled or empty
sidebar links.

Initial navigation:

```text
Workspace
└── Dashboard

Intelligence
└── Competitive Intelligence

Operations
├── Collections
├── Schedules & Alerts
└── Data Quality

Administration
├── Study Discovery
└── Product Packs
```

Price Monitoring becomes visible only after its first governed vertical slice has a useful landing
view, product/location drill-through, freshness and quality treatment, and stable API contracts.
Search Intelligence, Review Intelligence, Account, Organization, and Platform Admin follow the same
rule.

## Shell contract

- Persistent collapsible desktop sidebar.
- Compact rail at intermediate laptop widths.
- Modal slide-over navigation on mobile with focus containment and Escape dismissal.
- Sticky top context bar with current destination, environment state, and theme control.
- Report routes replace the destination label with a persistent context rail. Competitive View and
  Comparison Basis open application-width selection drawers; choosing an option updates the
  existing URL-governed report scope immediately and closes the drawer. Decision Readiness opens a
  read-only evidence and governance drawer.
- Label-only accordion navigation on the expanded sidebar. Descriptions belong in page context and
  help surfaces, not under every destination name.
- Expanded accordion groups participate in normal document flow and push later groups downward.
  The compact rail exposes grouped destination flyouts on hover, focus, or activation.
- Compact report mastheads and dense tab rails preserve vertical space for decision content.
- The report route owns the single page masthead. Specialist tabs may add compact context strips,
  but not a second hero or page masthead.
- Light/dark theme and reduced-motion support.
- URL and route continuity for all existing pages.
- Presentation preferences may use browser storage; analytical scope never does.
- Client navigation visibility is a UX concern, never authorization.

## Explicitly unchanged

- Existing `/analyses`, `/collections`, `/automation`, `/data-quality`, and `/admin` routes.
- `AnalysisResult`, report-view, artifact, match-review, and brand-workbench contracts.
- Deterministic metric ownership and renderer non-recalculation rules.
- Collection cost estimation, paid launch approval, queues, retries, and rate limiting.
- Existing temporary admin authentication.

## Acceptance criteria

1. Every currently implemented application destination is reachable from the new sidebar.
2. The active destination remains correct on nested detail routes.
3. No future/empty module link appears in production navigation.
4. Sidebar preference survives navigation and degrades safely when storage is unavailable.
5. Mobile navigation contains focus, closes with Escape/backdrop/navigation, and restores focus.
6. Existing page actions, report tabs, match decisions, collection flows, and admin sign-in remain
   operational.
7. Existing deep links and artifact routes are unchanged.
8. Unit, type, lint, build, and browser interaction checks pass.

## Subsequent slices

1. Migrate current pages into the new shell without redesigning page bodies.
2. Tighten Dashboard information density and page mastheads.
3. Decompose the Competitive Intelligence workspace into reusable tab and drawer components.
4. Implement Price Monitoring as the first additional intelligence module on the shared foundation.
5. Add Search and Review Intelligence only after their governed semantic layers and decision
   workflows exist.
6. Add Account/Organization/Platform surfaces only after server-enforced identity, tenant scope,
   RBAC, entitlements, usage, and budgets.
