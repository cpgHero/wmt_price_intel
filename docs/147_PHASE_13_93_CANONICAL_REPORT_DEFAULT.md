# Phase 13.93 - Canonical report default

Date: 2026-09-10

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
