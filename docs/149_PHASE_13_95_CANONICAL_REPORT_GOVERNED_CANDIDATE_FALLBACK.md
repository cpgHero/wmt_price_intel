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

Status: merged, deployed, and production-verified.

- PR: `#11`
- Merge commit: `ac85ab3b6f075ad933d2e52c4fb249a453f50035`
- Main CI: run `34511375262` passed documentation, Python, TypeScript, and container jobs.
- Railway production web deployment: `81a554bd-ad18-4a77-9fd4-1a81fadca721` completed with status `SUCCESS`.
- Production health: `/health/ready` returned `{"status":"ready","service":"web","dependencies":{"api":"ok"}}`.
- Live canonical dataset checks after deployment:
  - Milk analysis `fresh_fluid_milk-19a350ee-90d7-4ec5-92f9-467a15c116b4-match-v2-43c67b88-r2` returned `ready` with 764 included product relationships, 262 Walmart wins, 486 competitor wins, 16 parity relationships, 3 excluded relationships, and price normalization `passed`.
  - Egg analysis `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-93bf1a76-r3` returned `ready` with 112 included product relationships, 87 Walmart wins, 24 competitor wins, 1 parity relationship, 0 excluded relationships, and price normalization `passed`.
  - Banana analysis `fresh_bananas-3db3e46c-8a89-4519-9936-5e0c48161a5d-match-v2-7d95499f-r2` remained `ready` with 5 included product relationships, 2 Walmart wins, 3 competitor wins, 0 parity relationships, 0 excluded relationships, and price normalization `passed`.

Follow-up verification found that milk had 3 seller-governance exclusions while retaining 764 reportable relationships. The dataset is correctly ready because the unqualified seller rows are excluded, but the seller-governance status should be a warning state rather than `blocked` when valid included relationships remain.
