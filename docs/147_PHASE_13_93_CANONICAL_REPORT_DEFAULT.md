# Phase 13.93 - Canonical report default

Date: 2026-09-10

Release status: merged in PR #7 as `502cce5`, passed main CI, deployed to Railway production, and production-verified on 2026-09-10.

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

Make the simplified canonical report workspace the default report experience for AnalysisResult v2 reports, while preserving an explicit legacy workspace escape hatch for audit and comparison.

## Scope

- The Reports library now exposes a single `Open report` action.
- `/analyses/{analysis_id}` renders the canonical five-tab report by default when the analysis has an AnalysisResult v2 report view.
- The old report workspace remains available through explicit legacy query flags:
  - `?experience=legacy`
  - `?experience=current`
  - `?reportExperience=legacy`
  - `?reportExperience=current`
  - `?canonical=0`
  - `?canonical=false`
- The canonical report header no longer describes itself as a preview.
- The canonical report keeps a `Legacy workspace` link for operator comparison.

## Non-goals

This phase does not change report calculations, prices, distribution rules, matching, Product Packs, retained evidence, provider calls, PDP calls, AI calls, reprocessing, publication gates, PDF export, or database contents.

## Acceptance criteria

- Default report route renders the canonical report for AnalysisResult v2.
- Explicit legacy query flags still render the old workspace.
- Reports library no longer presents separate current/simplified actions.
- Source-contract tests protect the canonical five-tab structure, product-card trust language, image-first relationship cards, Evidence & QA checklist, and absence of preview/version-change commentary.

## Production verification

- Railway web deployment `3c29157c-c8d4-4174-8ec8-a9a8e6d9137c` completed successfully from commit `502cce5b5755b5698e18847be60717c599c63d64`.
- `https://web-production-ee2a4.up.railway.app/health/ready` returned ready with API dependency OK.
- The production Reports library exposed five report links, showed the single `Open report` action, and did not show `Open simplified preview`.
- The production default milk report route rendered canonical report markers including `Product-level report`, `Canonical dataset`, and `Legacy workspace`.
