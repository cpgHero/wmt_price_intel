# Product Pack Abstraction Audit

## Result

The core analytics engine has zero product-specific code paths. Fresh shell eggs, fresh fluid milk,
and fresh bananas/plantains use the same normalization, classification, formula, matching, and
summary implementation already used by strawberries.

The executable guard is
`packages/python/rci-analytics/tests/test_product_pack_abstraction.py::test_core_engine_contains_no_product_specific_code_paths`.
It scans every Python source file under `packages/python/rci-analytics/src` and fails if a supported
product name appears in core code.

## Core-path inventory

| Core path | Product-specific branches | Category-neutral responsibility |
| --- | ---: | --- |
| `rci_analytics/normalization.py` | 0 | Canonical retailer identity, price, ZIP, store, stock, and offer identity |
| `rci_analytics/classification.py` | 0 | Scope terms, exclusions, six extraction primitives, formulas, review reasons |
| `rci_analytics/matching.py` | 0 | Exact ZIP/radius matching, unknown handling, brand policy, price selection, metrics |
| `rci_analytics/product_pack.py` | 0 | Schema/semantic validation, formula safety, immutable pack persistence |
| `rci_analytics/parquet.py` | 0 | Canonical Parquet serialization |
| `rci_analytics/cli.py` | 0 | Product Pack selection and generic compact-run orchestration |

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
| Golden evidence | `fixtures/golden/strawberries/`, `eggs/`, `milk/`, `bananas/` | Human-validated summaries, tolerances, and attached-source reconciliation fixtures |
| Reference deliverables | `reference_outputs/*_analysis.xlsx`, `reference_outputs/*_report.html` | Audit provenance only; never runtime inputs |
| Tests | `packages/python/rci-analytics/tests/` | Category examples and golden assertions against the generic engine |

No API, worker, scheduler, result renderer, database, or web route contains a supported-category
branch.

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
