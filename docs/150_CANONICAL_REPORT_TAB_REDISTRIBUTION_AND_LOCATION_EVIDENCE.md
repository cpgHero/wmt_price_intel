# Phase 13.96 - Canonical report tab redistribution and location evidence

Date: 2026-09-10

Status: Production verified on Railway web deployment ff22d777-a00d-4ea1-a8ef-bd8a0adb248b after PR #13 merged.

## Context

The canonical report had become simpler, but the tab experience repeated the same product relationship cards across multiple sections. That made the app easier to navigate but not meaningfully more insightful. The user also identified that the report did not expose location detail or map context even though distribution is a critical trust boundary.

## Decision

Keep the canonical report app-first, but give each tab a separate job:

- Executive Summary: executive triage and brand-role facts.
- Product Wins & Losses: the image-first action board with every governed relationship.
- Distribution & Assortment: deduplicated Walmart product footprints plus exact-product location evidence.
- Price Architecture: table-based reporting-price ladders by governed relationship and brand role.
- Evidence & QA: readiness, guardrails, and excluded relationships.

Distribution remains the owner-defined positive-price Search footprint: a distinct store counts only when the exact Walmart product appears in store-level Search with price greater than $0. This is not an in-stock indicator or inventory claim. Service-area presence remains separate.

## Implementation

- `apps/web/src/app/analyses/[analysisId]/canonical-report-workspace.tsx`
  - Removes repeated card sections from Executive Summary, Distribution & Assortment, and Price Architecture.
  - Adds an executive priority table for Walmart losses.
  - Groups Distribution & Assortment by exact Walmart product ID instead of repeated competitor-pair rows.
  - Adds exact-product map loading through the existing source-backed `/api/price-monitoring/{analysisId}/map` route.
  - Adds mapped-store sample rows and links to the full location view plus exact-product evidence CSV.
  - Adds a reporting-price ladder table for Price Architecture.
- `apps/web/src/app/styles.css`
  - Adds table, map, selector, evidence-link, and outcome-pill styling for the redesigned canonical tabs.
- `apps/web/src/lib/canonical-report-workspace-source.test.ts`
  - Guards against returning to repeated footprint cards across tabs.
  - Requires exact-product location evidence, map, mapped-store sample, and CSV links.
- `apps/web/src/lib/platform-docs.ts`
  - Documents the five tab responsibilities and the source-backed map boundary.

## Verification

Local verification completed:

- `git diff --check`
- Direct Node source-contract assertions for canonical report workspace and Platform Docs
- TypeScript TSX parse/transpile check for `canonical-report-workspace.tsx`

Local full Vitest, TypeScript, and ESLint runs were blocked by incomplete package symlinks after the clean worktree's pnpm install stalled. GitHub CI is the release gate for full install, format, lint, typecheck, test, build, and browser coverage.

## Non-goals

This change does not alter source data, Matching v2 certification, canonical dataset calculations, price normalization, seller governance, distribution definitions, provider collection, PDP calls, AI calls, report replay, PDF export, or historical artifacts.
