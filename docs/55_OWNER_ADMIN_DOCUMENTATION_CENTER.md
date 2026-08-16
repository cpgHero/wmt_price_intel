# Phase 13.6 — Owner and Administrator Documentation Center

## Outcome

`/admin/docs` is the maintained, protected operating manual for the platform owner and platform
administrators. It consolidates current implementation behavior into plain-language, task-oriented
guides without replacing the detailed architecture, phase, schema, API, migration, and testing
records elsewhere in the repository.

The page documents the complete path from category discovery and collection design through paid
provider work, immutable evidence, normalization, product-location projection, PDP enrichment,
brand governance, matching, local comparisons, deterministic analytics, governed AI, readiness,
reporting, schedules, release, and rollback.

## Information architecture

The documentation is grouped into:

1. **Start here** — product purpose, trust rules, and the application map.
2. **Workflows** — data lifecycle, study/collection setup, evidence, matching, and reporting.
3. **Trust & governance** — administrator playbooks plus security, spending, and metric controls.
4. **Operations** — Railway topology, troubleshooting, schedules, alerts, testing, release, and
   rollback.
5. **Reference** — metric/evidence dictionary, honest limitations, and the append-only change-order
   log.

The user-facing source is `apps/web/src/lib/platform-docs.ts`. The protected same-origin endpoint
`GET /api/admin/docs` returns it only when the existing eight-hour administrator session is valid.
The client provides full-text guide search, grouped navigation, related application links, current
status, audience, reading time, and last-verification metadata.

## Authority and security

- The docs describe current implementation and explicitly label shadow/certification or deferred
  behavior.
- No secret value, raw private URI, credential, or administrator password is included.
- The browser receives the content only after the protected administrator session is verified.
- The same administrator password/session used by Product Packs, Study Discovery, and Match
  Certification grants access. Full individual accounts and RBAC remain a documented limitation.
- Detailed engineering documents remain authoritative for code-level contracts. If a conflict is
  found, treat it as a documentation defect and resolve the code/contract/current-behavior question
  before updating the operating manual.

## Maintenance contract

A workflow, metric, authority, cost, security, API, service, administrator, testing, or presentation
change is not done until all of the following are complete:

1. Record the requested outcome, reason, approval, and authoritative-behavior impact.
2. Inventory schema, persistence, API, worker, scheduler, UI, metric, cost, secret, audit, fixture,
   golden, and historical-compatibility effects.
3. Update implementation, detailed phase/architecture docs, affected Platform Docs guides, metric
   definitions, links, and limitations together.
4. Run proportional contract, unit, integration, concurrency, golden, browser, migration, build,
   container, and production checks.
5. Append a dated change-order entry with status, operational effect, compatibility decision, and
   verification evidence. Existing entries are immutable historical context.
6. Update `lastVerified` only after the described behavior is verified.
7. Read the production guide as an administrator and correct any statement that describes intent
   rather than reality.

This contract is also part of the repository `AGENTS.md` Definition of Done so it applies to future
development and polishing phases.

## Verification

The web unit tests verify unique guide IDs, required lifecycle/governance content, valid internal
links, current certification language, and the presence of a change-order log. Navigation tests
verify the page is exposed in Administration. Browser tests verify protected access, guide
rendering, search, and guide selection. The Product Pack abstraction audit explicitly classifies
the canonical Platform Docs content file as non-executable content while continuing to scan every
executable Python, TypeScript, and TSX core path for product-category branching.

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

## Change-order baseline

The first in-app baseline is version `1.0.0`, verified August 16, 2026, and describes the production
implementation through Matching Architecture v2 Phase 13.5. The in-app change-order guide is the
append-only owner-facing log for subsequent behavior changes.
