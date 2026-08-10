# Primary Application UX Cohesion

## Objective

Turn the primary application shell into an operational workspace for leadership, pricing,
merchandising, competitive-intelligence, and collection-operations users without changing the
underlying analytical contracts or building RBAC prematurely.

## Scope

- Replace the marketing-led Dashboard with an operational home for attention items, recent
  reports, collection activity, schedules, and credit usage.
- Make Collections a discoverable workspace containing recent runs, saved definitions, and the
  existing cost-controlled launch wizard.
- Improve collection monitoring with human-readable collection context, breadcrumbs, plain status,
  and expandable retailer/task diagnostics.
- Make the Reports index searchable and decision-oriented while keeping immutable identifiers in
  secondary audit details.
- Reframe Automation as user-facing schedules, alerts, and deliveries with raw configuration behind
  technical disclosures.
- Reframe portfolio Data Quality as a prioritized work queue with plain-language issue impact,
  counts, rates, and direct investigation links.
- Add active primary navigation and responsive navigation behavior.

## Audience and future access model

- Viewer: Dashboard and Reports, plus future read-only alert visibility.
- Analyst: Viewer capabilities plus Collections, Data Quality, and Automation.
- Admin: Analyst capabilities plus future users, integrations, locations, Product Packs, budgets,
  audit logs, and system health.

This phase does not enforce those roles. Shared routes and components remain capability-ready so a
future authentication layer can hide pages or actions without duplicating application experiences.

## Interaction rules

- Cards and counts must answer a user question and link to the relevant work.
- Zero-value vanity cards are replaced with explanatory empty states or omitted.
- Business-facing pages use named retailers and plain language; UUIDs and raw JSON live in audit or
  technical disclosures.
- Drawers/disclosures retain context for investigation. Modals are reserved for paid, destructive,
  or otherwise consequential confirmations.
- Hover content is supplemental only. Critical evidence and actions remain keyboard accessible.
- Primary navigation shows the active location and remains usable at tablet/mobile widths.

## API addition

`GET /api/v1/collection-runs?limit=<1..200>` returns recent immutable collection-run records ordered
newest first. It is read-only and requires no migration.

## Explicitly deferred

- Report workspace, leadership HTML, email, workbook, and export synchronization.
- Publication regeneration or historical artifact replacement.
- Authentication, user accounts, RBAC enforcement, and platform-admin pages.
- Dynamic geography construction and map approval.
- Product Pack builder.
- New MetricsCart, PDP, or OpenAI calls.

## Acceptance criteria

1. A user can identify urgent work, recent intelligence, current collection activity, upcoming
   schedules, and recent credit usage from the Dashboard.
2. Collections exposes recent runs and saved definitions before the launch wizard.
3. Every stored run is reachable from the Collections workspace and shows a human-readable name
   when its definition is available.
4. Reports can be searched and filtered by retailer/readiness without exposing the analysis UUID as
   primary content.
5. Data Quality never presents raw JSON as the default explanation and never labels warning-bearing
   work simply as ready.
6. Automation hides internal acceptance fixtures from the business view and renders configuration
   in plain language with technical details disclosed on demand.
7. Primary navigation identifies the active page and remains visible below 1050 pixels.
8. Existing report and export routes remain unchanged.
