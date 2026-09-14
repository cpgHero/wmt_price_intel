# Phase 14.17 — Customer report UX hardening

Date: 2026-09-14
Status: merged, deployed, and production-smoked

## Purpose

Make customer report access feel intentional and trustworthy now that the
report detail workspace is backed by customer-gated data routes.

## Changes

- Customer report responses present clean report titles. Curated report metadata
  wins when present; otherwise stable Product Pack identifiers are converted
  into customer-facing report names.
- Customer report responses also present customer-facing category labels when
  older reports only carry technical Product Pack-style category identifiers.
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

Continue with the next customer portal foundation slice: account/workspace
administration, report-grant management UX, or customer-auth hardening depending
on priority.

## Production verification

- `/customer` returned 200.
- `/customer/reports/{accessId}` returned 200.
- Anonymous `/api/customer/reports/{accessId}/report` returned 401.
- The GHRetail production report list returned 5 granted reports, 5 ready
  reports, customer-facing report titles, and customer-facing category labels.
