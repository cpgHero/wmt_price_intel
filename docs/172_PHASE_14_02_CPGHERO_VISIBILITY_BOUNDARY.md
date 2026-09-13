# Phase 14.02 — CPGHero platform terminology and visibility boundary

## Purpose

This phase starts the transition from an internal retailer competitive-intelligence workbench to the CPGHero platform by defining where customer-facing language begins and where private implementation details must stay private.

The phase adds the first automated customer-visible masking gate. It is not the full multi-tenant authentication, billing, Live API, Bulk Projects, or repo cleanup implementation.

## Owner-approved direction

The platform owner approved the Phase 14.00 platform vision and Phase 14.01 current-state audit. The controlling product direction is now:

- CPGHero is the product shell and commercial platform;
- Live APIs, Bulk Projects, and App Analytics are the three commercial surfaces;
- upstream provider brands, credentials, endpoints, provider-specific request parameters, and billing mechanics must not appear in customer-facing surfaces;
- internal adapters, private admin/operations workflows, tests, migrations, and historical evidence can retain implementation detail only when explicitly classified as internal.

## Changes made

### Repository product boundary

`AGENTS.md` now states that the repository is governed as the CPGHero retailer data and intelligence platform.

The updated boundary preserves the most important engineering invariant: the reusable engine remains retailer- and category-extensible. CPGHero is the product platform, but generic collection, normalization, matching, analytics, reporting, and geography code must not become hard-coded to Walmart or any specific product category.

### Customer-facing copy cleanup

Two collection UI messages were changed from provider-facing language to CPGHero/source-safe language:

- collection spend approval now says “collection spend” and “live source calls”;
- historical import context now says “live CPGHero collection tasks.”

This keeps the current UI direction aligned with the future Bulk Projects surface without changing runtime behavior.

### Customer-visible provider-masking gate

`scripts/check_customer_visible_provider_masking.py` scans currently classified customer-visible surfaces for hashed forbidden tokens. The checker does not embed the private provider brand or provider-specific credential parameter in its own source.

The first scan scope includes:

- non-admin routes under `apps/web/src/app`;
- the current CPGHero platform blueprint and audit phase records.

The first internal exclusions are:

- `apps/web/src/app/admin/`;
- `apps/web/src/app/api/admin/`.

These exclusions are intentional. The admin surfaces still contain private operator language and need a separate internal-admin cleanup plan. The gate prevents new customer-visible leaks while avoiding a risky blind rename of private adapter and historical evidence files.

### CI enforcement

The documentation CI job now runs the customer-visible provider-masking gate before the Platform Docs coverage gate.

## What this phase does not change

This phase does not:

- rename internal adapters or provider-specific runtime IDs;
- change collection request payloads;
- change upstream credentials, limits, retries, or billing formulas;
- change raw evidence, normalized observations, report metrics, Product Packs, Retailer Packs, matching logic, or Proximity calculations;
- add customer accounts, RBAC, entitlements, API keys, or billing;
- delete historical docs, fixtures, source material, or generated assets.

Those changes require subsequent phases because they can affect production behavior, evidence lineage, or customer access boundaries.

## Acceptance criteria

Local acceptance for this phase:

- customer-visible masking gate passes;
- Platform Docs coverage gate passes;
- TypeScript formatting/linting/typechecking/tests pass for affected files;
- Python formatting/linting/tests remain unaffected except for the new checker;
- no upstream provider brand or API-key query-parameter token is added to the new phase docs.

CI acceptance:

- documentation job passes the new masking gate;
- documentation, Python, TypeScript, and container jobs pass.

## Remaining work

The visibility boundary is only partially implemented. The next phases should expand it in this order:

1. classify every route, contract, schema, doc, and export as customer-visible, internal-admin, or private implementation;
2. move current owner/admin docs behind a clearly internal documentation scope;
3. add compiled browser-bundle scanning;
4. add export/report/email/webhook fixture scanning;
5. replace browser-visible adapter IDs with CPGHero-facing source definitions or server-resolved adapter selection;
6. define customer-safe API errors and support correlation IDs;
7. introduce account/user/RBAC/entitlement enforcement so visibility rules are enforced by identity, not just path convention.

## Risk notes

The biggest risk is mistaking this initial gate for complete masking. It is not complete. It is the first enforceable boundary that protects obvious customer-visible surfaces while preserving the working internal adapter architecture.

The second risk is overcorrecting with a blind rename. Internal provider-specific implementation details are still necessary for adapters, private operations, migration history, and source-material reconciliation. Those should be hidden and classified, not erased without a migration plan.

