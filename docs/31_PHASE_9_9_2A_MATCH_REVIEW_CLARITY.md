# Phase 9.9.2a — Match Review clarity and evidence

## Outcome

Make one-to-one product governance understandable without requiring the analyst to infer what the
two workbench sections mean. The default surface is an evidence-ranked pair-review queue. Manual
matching is a secondary workflow containing only genuinely unmatched products for the selected
competitor and comparison lens.

## Relationship and lens contract

- A product relationship is approved once per reference retailer, competitor retailer, Product
  Pack version, and stable pair of retailer product IDs.
- `product_match_rule.profile_id` remains the stored source lens from which the human decision
  originated; the API projects it as `source_profile_id` for clarity.
- `product_match_rule.eligible_profile_ids` records every exact-geography comparison profile for
  which the relationship is valid.
- Confirmed one-to-one uniqueness is global across the eligible profiles for that competitor. A
  product cannot be paired with one product for package price and a different product for unit
  price.
- An exact-package automatic relationship may be eligible for package and normalized-unit lenses.
  A size-normalized relationship may be eligible only for the normalized-unit lens.
- Automatic candidate eligibility is projected only from Product Pack matches already admitted by
  the deterministic analytics engine. The UI, API, and LLM do not create analytical eligibility.
- A manually created relationship begins with the selected comparison lens. Reanalysis still
  validates positive Search prices, availability, geography, and the configured comparison metric.

Migration `0018_match_lens_eligibility` preserves existing decisions by treating their previous
profile as their initial eligible profile. It replaces profile-scoped pair indexes with global
one-to-one indexes inside a revision and competitor scope.

## Review projection

The worker and historical publication-context replay project match candidates for every configured
exact-ZIP comparison profile. Candidate rows include:

- profile ID, label, comparison metric, and match basis;
- stable retailer product IDs and retained Search-backed product identity;
- observation and market counts;
- persisted median competitor-minus-reference price difference;
- deterministic Product Pack match attributes and a plain-language rationale.

The Match Review API combines identical product pairs into one connection with
`eligible_profile_ids` and `profile_evidence`. PDP-backed product highlights supply descriptions,
identifiers, specifications, physical properties, variants, URLs, and imagery. Search remains the
only authoritative source for store-specific price and location.

## Workbench behavior

- The named primary retailer is always on the left; the selected competitor is on the right.
- The main review queue contains suggested, confirmed, and rejected pairs, ranked by retained
  Search evidence.
- “Suggested” means the automatic Product Pack relationship is used by the current ungoverned
  analysis but has not been human-approved.
- Counts are recomputed for the selected competitor and comparison lens.
- Relationship cards include both product images, named retailer roles, IDs, evidence volume,
  plain-language price position, eligible-lens labels, and decision controls.
- Selecting either product opens an evidence drawer with side-by-side PDP identity, deterministic
  match attributes, Search observation/market counts, and explicit source roles.
- The manual builder is collapsed below the review queue and contains only products that have no
  suggested or confirmed relationship in the selected scope. Its alphabetical order is explicitly
  non-significant.
- Saving a decision creates a new immutable revision. Updating the analysis reuses persisted input
  artifacts and queues no MetricsCart Search, PDP, or OpenAI calls.

## Acceptance tests

1. The same automatic pair from package-price and unit-price profiles is projected as one
   relationship with both eligible profile IDs.
2. A confirmed relationship applies to every recorded eligible profile during governed reanalysis.
3. Database and repository enforcement reject a second confirmed relationship using either product,
   even when the attempted decision originates from a different lens.
4. Selecting a competitor and lens scopes suggested, confirmed, rejected, and unmatched counts.
5. Products in an active suggested or confirmed pair do not appear in the manual unmatched builder.
6. A rejected pair returns its products to the unmatched pool unless another active relationship
   uses them.
7. The evidence drawer distinguishes Search price/location authority from PDP identity enrichment.
8. Existing product-category abstraction tests remain unchanged; no category branch is introduced.

## Verification commands

```bash
.venv/bin/ruff check packages/python/rci-analytics packages/python/rci-results apps/worker
.venv/bin/pytest packages/python/rci-analytics/tests/test_presentation.py \
  packages/python/rci-analytics/tests/test_matching.py \
  packages/python/rci-results/tests/test_match_review.py \
  apps/api/tests/test_analyses.py -q
pnpm --filter @rci/contracts check
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web test
pnpm --filter @rci/web build
```
