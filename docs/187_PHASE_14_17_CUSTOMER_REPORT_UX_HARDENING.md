# Phase 14.17 — Customer report UX hardening

Date: 2026-09-14
Status: local verification passed; CI verification pending

## Purpose

Make customer report access feel intentional and trustworthy now that the
report detail workspace is backed by customer-gated data routes.

## Changes

- Customer report responses present clean report titles. Curated report metadata
  wins when present; otherwise stable Product Pack identifiers are converted
  into customer-facing report names.
- The customer workspace adds granted-report summary cards, ready-report counts,
  latest-grant context, and explicit grant-gated trust language.
- Raw analysis IDs, result IDs, and checksums remain available in collapsed
  audit details instead of being primary customer labels.
- Customer report detail pages add a compact access-summary strip before the
  canonical report workspace.

## Non-goals

This phase does not change immutable report results, report calculations,
matching, price normalization, source evidence, grants, roles, customer API
keys, billing workflows, collection requests, source-provider calls, PDP calls,
AI calls, PDFs, proximity metrics, or historical artifacts.

## Local verification

- API focused tests for cleaned customer report titles.
- Web source-contract tests for customer report UX.
- Web lint, typecheck, and production build.
- Repo-wide Python format and lint checks.

## Next step

Run CI, merge, deploy, and smoke-check the customer workspace/report pages in
production.
