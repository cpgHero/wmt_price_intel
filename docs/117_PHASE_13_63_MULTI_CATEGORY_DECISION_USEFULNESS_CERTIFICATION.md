# Phase 13.63 — Multi-Category Decision-Usefulness Certification

Status: deployed, rematerialized, and production-verified

Date: 2026-08-27

## Objective

Apply the Phase 13.62 decision-quality model to every active Competitive
Intelligence publication, repair shared evidence or audit defects rather than
category symptoms, and classify each report for decision use.

This phase uses retained reporting evidence only. It does not collect Search or
PDP data, call an AI model, change a match certification, or delete source data,
PDP evidence, certification history, superseded publications, or audit lineage.

## Active publication certification

| Category | Active analysis | Documents | Contexts | Scored | Local evidence limited | No selected-basis relationship | Errors | Warnings | Decision-use classification |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Vitamins & Supplements | `vitamins_supplements-aee8a9d6-33e5-4bac-903c-2570d869db52-match-v2-71792d31` | 6 | 54 | 28 | 17 | 9 | 0 | 65 | Share with caveats |
| Fresh Fluid Milk | `fresh_fluid_milk-19a350ee-90d7-4ec5-92f9-467a15c116b4-match-v2-28e0850f-r5` | 9 | 18 | 15 | 3 | 0 | 0 | 21 | Share with caveats |
| Fresh Strawberries | `fresh_strawberries-81e1dd0d-450d-49bb-a28c-b32de48ea51c-match-v2-4e6bddc0-r4` | 6 | 12 | 12 | 0 | 0 | 0 | 0 | Ready |
| Fresh Shell Eggs | `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-3c967ecc-r3` | 6 | 78 | 66 | 12 | 0 | 0 | 24 | Share with caveats |
| Fresh Bananas & Plantains | `fresh_bananas-3db3e46c-8a89-4519-9936-5e0c48161a5d-match-v2-00a5061c-r3` | 15 | 30 | 21 | 3 | 6 | 0 | 9 | Share with caveats |
| Fresh Ground Beef | `fresh_ground_beef-b01158a0-6ac5-4d8d-9d57-6978cfd61d17-match-v2-a7fb8453-r4` | 6 | 12 | 12 | 0 | 0 | 0 | 0 | Ready |

Across the six publications, all 204 mandatory retailer × comparison basis ×
radius contexts are present. All 48 materialized documents pass with zero
blocking errors. The 119 warnings are explicit evidence limitations rather than
failed calculations or silent zeros.

## Cross-category mathematical certification

Every decision context passed these invariants:

- `catalog >= in_scope >= observed >= certified >= selected >= locally_scored`;
- scored product-locations never exceed observed benchmark product-locations;
- displayed local coverage exactly recomputes from its numerator and
  denominator to the published precision;
- physical-retailer scored products and local evidence are nondecreasing from
  one to three to five miles;
- Amazon Same Day evidence remains constant across radius selections because it
  uses the governed delivery-ZIP service-area rule; and
- the scored, local-evidence-limited, and no-selected-relationship partitions
  reconcile exactly to the required context population.

## Shared defects corrected

### Governed evidence generation

Selective product-observation reads now use only the exact classified artifact
generation named by the immutable AnalysisResult evidence manifest. Historical
artifact generations cannot be mixed into current report materialization. The
object-storage connection pool is sized for the bounded selective workload.

### Strictly nested evidence funnels

Certified and selected identity counts are now restricted to products observed
in the current Search evidence before locally scored products are derived. A
certified relationship whose benchmark product was not observed remains visible
in the complete relationship ledger, but cannot inflate the observed evidence
funnel.

### Correct audit relationship between ledger and funnel

The publication audit now requires the selected observed-basis population to be
a subset of the complete included-product ledger. It no longer incorrectly
requires equality when the complete ledger intentionally preserves an
unobserved certified relationship for transparency.

## Durable rematerialization

Large publications were rebuilt through leased, retryable Postgres
materialization jobs and atomically finalized only after their semantic gates
passed. Existing live publications remained available while replacements were
staged.

- Milk: `33feab16-d305-43ed-ab87-89d26e19996e` — 13/13 stages succeeded.
- Strawberries: `ebaafd6d-334c-4af5-95ef-5064f6afa181` — 10/10 stages succeeded.
- Eggs: `379a3d82-a62d-4f1f-9358-922272f87d14` — 10/10 stages succeeded.
- Bananas: `37846469-272a-4c7e-a8a9-396afdd4b6fb` — 19/19 stages succeeded.
- Ground Beef: `f6698460-746e-4217-a9ae-537d87766efb` — 10/10 stages succeeded.

The current Vitamin publication had already been rebuilt and certified in
Phase 13.62.

## Decision-use caveats

- Vitamins is a two-Walmart-location pilot. Its price conclusions are valid for
  those observed product-stores, not a national Spring Valley conclusion.
  Seventeen contexts lack local scored evidence, nine lack a relationship under
  the selected basis, and 39 warnings identify incomplete cohort attributes.
  Strength values whose source omits a unit remain unlabeled; the application
  does not invent a unit.
- Milk has three local-evidence-limited contexts and 18 disclosed cohort
  attribute-coverage gaps. Its scored contexts remain mathematically certified.
- Eggs has 12 local-evidence-limited contexts and 12 cohort attribute-coverage
  warnings. A retailer zero is therefore distinguishable from missing data.
- Bananas has three local-evidence-limited contexts and six governed
  no-selected-basis contexts. Those views are not price-performance claims.
- Strawberries and Ground Beef have complete active context matrices with no
  semantic warnings and are ready for their stated populations and periods.

## Production presentation acceptance

All six live Retailer Scorecards load without an application error, server
error, non-finite value, unresolved placeholder, or stale loading state. The
top bar displays the selected physical-store radius and separately labels the
same-delivery-ZIP service-area rule. Retailer names, Product Pack comparison
bases, evidence funnels, and current readiness states are visible. Assortment
cards describe observed stores rather than presenting ZIP counts as the
physical-store comparison grain.

## Verification

- 778 Python tests pass; 16 environment- or fixture-dependent tests skip with
  their documented prerequisites.
- 73 web tests and one TypeScript contract-package test pass.
- Formatting, Ruff, ESLint, TypeScript, contracts, and 91 normative JSON
  documents pass.
- GitHub Actions runs `33040753435`, `33041986464`, and `33042654180` pass for
  commits `a945004`, `28c6399`, and `5b5ec7a`.
- Railway API deployments `087a50f3-bc3f-4ed5-87b6-4a5cd8bcb102`,
  `2894d5b1-6a3e-4ef2-a2bf-af7ad74a14ef`, and
  `fc374037-a9b8-4118-bea6-4c560d40b53f` succeeded. Web deployment
  `4d6b906b-5ab5-41d2-88b9-01a1fe81acc4` succeeded.

Provider spend: `$0.00`.

AI spend: `$0.00`.
