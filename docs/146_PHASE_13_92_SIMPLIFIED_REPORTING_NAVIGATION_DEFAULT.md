# Phase 13.92 — Simplified reporting navigation default

Date: 2026-09-10

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

Make the simplified reporting information architecture the default active app experience without deleting the underlying evidence, data-quality, or compatibility routes.

This is a navigation and terminology cleanup. It does not change collection, matching, Product Pack rules, retained evidence, pricing calculations, distribution calculations, report materialization, publication gates, AI usage, provider calls, PDP calls, PDF export, or historical artifacts.

## Changes

- Defaulted primary navigation to the simplified Reports-first model.
- Kept legacy navigation available only through an explicit disable value for `NEXT_PUBLIC_RCI_SIMPLIFIED_NAV`: `0`, `false`, or `disabled`.
- Renamed the `/admin/report-publishing` page heading from Report Publishing to Pipeline Status.
- Updated Pipeline Status authentication and empty-state copy so operators see the page as readiness/materialization/publication diagnostics rather than a separate reporting destination.
- Updated Reports empty-state diagnostics to point to Pipeline Status instead of exposing “report materialization” as the primary user-facing concept.

## Why this simplifies the workflow

The active user path should be:

1. Collect data.
2. Certify/match and govern the category.
3. Review completed Reports.
4. Use Pipeline Status only when a report is missing, blocked, or being reprocessed.

Price Intelligence and Data Quality remain available as supporting evidence/status surfaces, but they should not compete with Reports as primary destinations.

## Acceptance

- The default navigation shows Reports as the only Analytics item.
- Price Intelligence and Data Quality are absent from the simplified primary navigation.
- Pipeline Status appears under Operations and links to the existing `/admin/report-publishing` route.
- The `/admin/report-publishing` page visibly reads as Pipeline Status.
- Reports empty-state diagnostics point operators to Pipeline Status and Collections without suggesting that missing jobs mean missing reports.
