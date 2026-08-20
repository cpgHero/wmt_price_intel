# Phase 13.25 — Focused Brand Breadth Drill-down

## Status

Deployed and production-verified on August 20, 2026.

## Change

The Assortment Scorecards Observed Brand Breadth drill-down no longer offers
the `Open product footprint` link on product records.

The drill-down continues to show every product assigned to the selected
governed Search brand, including product imagery, identity, and observed
location evidence. The change is intentionally limited to Brand Breadth;
other assortment evidence drawers retain their existing actions.

## Governance

This is an interaction-only change. It does not alter assortment metrics,
brand membership, Search or PDP evidence, match certification, provider
usage, AI usage, or audit lineage.

## Verification

The release passed TypeScript, lint, all 68 web tests, formatting, and a local
production Next.js build. GitHub Actions run `32424338633` passed the complete
release gate, including Python, contracts, reversible migrations, 13 browser
tests, and all four service-container builds.

Live verification opened Walmart Great Value from Observed Brand Breadth in
the governed Egg report. The drawer rendered all 43 governed product records
and contained zero `Open product footprint` links.
