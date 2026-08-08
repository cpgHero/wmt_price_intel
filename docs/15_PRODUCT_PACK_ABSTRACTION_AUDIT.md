# Product Pack Abstraction Audit

## Result

The core analytics engine has zero product-specific code paths. Fresh shell eggs, fresh fluid milk,
and fresh bananas/plantains use the same normalization, classification, formula, matching, and
summary implementation already used by strawberries.

The executable guard is
`packages/python/rci-analytics/tests/test_product_pack_abstraction.py::test_core_engine_contains_no_product_specific_code_paths`.
It scans Python and TypeScript runtime sources for API, worker, scheduler, web, contracts, core,
locations, collection, provider, analytics, automation, database, and result delivery code. It
fails if a supported product name appears outside tests. This makes the zero-branch claim
executable instead of relying on code review alone.

## Core-path inventory

| Core path | Product-specific branches | Category-neutral responsibility |
| --- | ---: | --- |
| `rci_analytics/normalization.py` | 0 | Canonical retailer identity, price, ZIP, store, stock, and offer identity |
| `rci_analytics/classification.py` | 0 | Scope terms, exclusions, six extraction primitives, formulas, review reasons |
| `rci_analytics/matching.py` | 0 | Exact ZIP/radius matching, unknown handling, brand policy, price selection, metrics |
| `rci_analytics/product_pack.py` | 0 | Schema/semantic validation, formula safety, immutable pack persistence |
| `rci_analytics/parquet.py` | 0 | Canonical Parquet serialization |
| `rci_analytics/cli.py` | 0 | Product Pack selection and generic compact-run orchestration |
| `apps/api/src`, `apps/worker/src`, `apps/scheduler/src` | 0 | Generic control, collection, analysis, and scheduling orchestration |
| `apps/web/src` | 0 | Catalog-driven Product Pack selection and generic run/analysis views |
| `rci_collections`, `rci_providers`, `rci_results`, `rci_automation` | 0 | Queueing, adapters, immutable results/delivery, and automation |
| `rci_contracts`, `rci_core`, `rci_db`, `rci_locations` | 0 | Generic contracts, settings, persistence, and geography |

## Generic capabilities added in Phase 8

1. Explicit `scope.target_terms` and `scope.hard_exclusion_patterns`.
2. Ordered declarative extraction rules:
   - `constant`,
   - `field`,
   - `measurement`,
   - `number_pattern`,
   - `term_map`,
   - `boolean_terms`.
3. Configured unit aliases and conversion factors for any numeric attribute.
4. Safe multi-input arithmetic formulas using existing AST validation.
5. Explicit `matching_profiles[].comparison_metric` when heuristic selection is ambiguous.
6. Enforced same-brand and private-label-equivalent policies with configured aliases/retailer sets.
7. Profile-scoped, one-sided unknown wildcard matching using configured attribute unknown values;
   unknown-to-unknown remains non-comparable.

Every capability is exercised without inspecting a category ID, Product Pack ID, product name, or
category-specific attribute name.

## Product-specific inventory

Product-specific behavior exists only in these intended data/test surfaces:

| Surface | Paths | Purpose |
| --- | --- | --- |
| Product Pack configuration | `product-packs/fresh_strawberries.json`, `fresh_shell_eggs.json`, `fresh_fluid_milk.json`, `fresh_bananas.json` | Scope, vocabularies, attributes, formulas, profiles, brands, QA, reporting |
| Catalog and safe examples | `product-packs/index.json`, `examples/collection-definition.*.json`, `examples/analysis-result.*.json` | User-selectable pack metadata and schema-valid demonstrations; no runtime branching |
| Golden evidence | `fixtures/golden/strawberries/`, `eggs/`, `milk/`, `bananas/` | Human-validated summaries, tolerances, and attached-source reconciliation fixtures |
| Reference deliverables | `reference_outputs/*_analysis.xlsx`, `reference_outputs/*_report.html` | Audit provenance only; never runtime inputs |
| Tests and validation tools | `apps/*/tests/`, `packages/python/*/tests/`, `apps/web/src/**/*.test.ts`, `scripts/validate_handoff.py` | Category examples and golden assertions against generic runtime behavior |
| Handoff provenance | `.env.example`, `README.md`, `START_HERE.md`, `AGENTS.md`, `docs/`, `prompts/`, `source_material/`, `MANIFEST.json`, `VALIDATION_RECEIPT.txt`, `diagrams/` | Operator instructions, supplied evidence, and original package inventory |

No API, worker, scheduler, result renderer, database, or web route contains a supported-category
branch.

## Attached egg source-quality evidence

The attached consolidated export has 386,889 search-result rows across 14 retailer domains. Its
intended raw grain is one retailer/normalized ZIP/store/product/title observation. The golden gate
checks all rows before applying the human-validated fresh-shell-egg catalog and explicitly records
these source-shape conditions:

| Check | Evidence | Analytical handling | Severity |
| --- | ---: | --- | --- |
| Required identity completeness | 0 rows blank across date, retailer, keyword, ZIP, title, or product ID | Safe for source reconciliation | Pass |
| Keyword versions | 385,893 `fresh eggs`; 996 Kroger `eggs` | `fresh eggs` is the default V1 keyword; keyword remains user-configurable | Low |
| Leading-zero ZIP loss | 31,416 rows (8.12%) contain fewer than five digits; none are nonnumeric or longer than five | Country-aware ZIP normalization restores five-character strings before keys/matching | High if unnormalized; mitigated |
| Repeated candidate grain | 43,846 rows (11.33%) repeat retailer/ZIP/store/product/title | Deterministic deduplication occurs before coverage and comparison metrics | High if undeduped; mitigated |
| Nonpositive price | 30,895 rows (7.99%), concentrated in Target and Safeway | Lowest-positive price policy excludes them from authoritative price comparisons | Medium; mitigated |
| Timestamp shape drift | All 63,153 Amazon rows use scientific-notation epoch milliseconds; other sources use ISO strings | Golden price/coverage metrics do not use this field; historical ingestion must normalize it before Phase 9 comparisons | Medium; open for historical ingestion |
| Stock availability sparsity | 323,736 blank, 62,877 true, 276 false | Retailer-specific availability policy; explicit Amazon false rows are excluded | Medium; documented |

These counts are assertions in `test_full_egg_consolidated_source_profile`, so a replacement export
cannot silently change source grain, keyword mix, ZIP repair volume, duplicate exposure, price
validity, timestamp shape, or stock semantics.

## Architectural acceptance test

Fresh shell eggs were added primarily by Product Pack data. The only engine changes were reusable
primitives also required by milk/bananas: declarative extraction, explicit metric selection, brand
policy enforcement, and wildcard semantics. Adding another category does not require editing the
classifier or matcher unless it reveals a genuinely new category-neutral primitive with its own
tests.

## Golden status and requested raw files

- Full strawberries: passed all exact counts/rates over 297,443 attached rows after the abstraction
  refactor.
- Full eggs: passed the 386,889-row, 14-retailer source/coverage profile and all 5,155 classified
  strict price matches. Walmart-lower rate reconciles exactly to 0.7468477206595538 and ALDI's
  competitor-lower rate to 0.5525040387722132.
- Milk and bananas: compact benchmark selectors pass; full raw regressions remain pending because
  their source files are intentionally absent from the implementation package.

The egg source is a consolidated export, not a collection of direct MetricsCart API payloads. The
full gate therefore keeps two explicit evidence boundaries: `product_catalog.csv` reconciles
scope/coverage against every source row, while `strict_matches.csv` supplies the validated
classified offers consumed by the generic comparison engine. Retailer-specific live adapter tests
continue to use API response fixtures.

To enable full reconciliation, attach these exact validated keyword versions:

1. Milk: `Milk___Walmart_All_Stores_20260807_012630.csv`,
   `Milk___Aldi_All_Stores_20260807_012605.csv`, and `milk_amazon.csv` (348,980 rows total).
2. Bananas: `Bananas___Walmart_All_Stores_20260807_051626.csv`,
   `Bananas___Aldi_All_Stores_20260807_051549.csv`, and `bananas_amazon(1).csv` (168,440 rows total).

Newer collections may be tested separately, but they are not substitutes for these versions when
reconciling the supplied August 2026 headline benchmarks.
