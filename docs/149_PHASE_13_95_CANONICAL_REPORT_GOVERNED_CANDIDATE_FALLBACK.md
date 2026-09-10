# Phase 13.95 - Canonical report governed candidate fallback

Date: 2026-09-10

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

Allow the canonical buyer-facing report dataset to use already-governed product-level match candidate evidence when a publication has certified relationships but an empty `product_decisions` array.

## Trigger

Production read-only checks showed that the active milk and egg reports had matching-v2 certified comparable relationships and ready aggregate scorecards, but their publication context contained zero product decisions. The same publications contained governed, QA-ready, positive-price `match_candidates` rows with product IDs, images, URLs, relationship IDs, prices, matched observations, and geography counts.

That made the Phase 13.94 fail-closed guardrail correctly block the canonical milk and egg report datasets, but it also exposed that the report adapter was ignoring retained product-level evidence already present in the report view.

## Scope

- Preserve `product_decisions` as the primary reportable product source when present.
- If `product_decisions` is empty, project only `match_candidates` that are:
  - `relationship_status` of `suggested` or `confirmed`;
  - `qa_status` of `ready`;
  - backed by at least one positive-price matched observation;
  - carrying positive benchmark and competitor median prices.
- Deduplicate fallback rows by governed relationship ID when present, otherwise by benchmark/competitor product pair.
- Prefer the Product Pack's preferred comparison basis when duplicate candidate rows exist across multiple lenses.
- Continue running the existing canonical seller, price, distribution, and readiness guardrails after the fallback source is selected.

## Non-goals

This phase does not change Product Pack matching rules, matching-v2 certification, immutable `AnalysisResult` contents, publication records, price calculations, distribution calculations, seller rules, provider collection, PDP calls, AI behavior, report materialization, PDF export, or historical artifacts.

## Acceptance criteria

- A production-shaped report view with empty `product_decisions` and governed candidate evidence produces reportable canonical product relationships.
- Duplicate governed candidate rows across profiles produce one canonical relationship, not double-counted rows.
- The selected fallback row prefers the report's preferred comparison basis.
- Existing product-decision-driven canonical reports continue to render from `product_decisions`.
- Reports with no product decisions and no admissible candidate evidence still fail closed with `no_reportable_product_relationships`.

## Production verification

Status: pending release.

