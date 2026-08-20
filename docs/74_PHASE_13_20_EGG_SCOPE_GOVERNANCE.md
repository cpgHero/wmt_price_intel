# Phase 13.20 — Egg Scope Governance and Certified-Decision Continuity

Status: implemented and locally verified; production activation and replay pending

## Purpose

Remove demonstrable non-shell-Egg products before PDP planning, matching, Price Intelligence,
Price Architecture Matrix construction, and Competitive Intelligence. Preserve immutable source
evidence and historical reports, and avoid asking an administrator to repeat a certified match
decision when only additive Product Pack scope exclusions changed.

## Source audit

The deterministic audit rebuilt the full Egg candidate graph from
`CCF_Search_Data_08.17.2026_v1.csv` (393,110 rows; 365,723 unique normalized observations) and the
retained Egg PDP archive. Product Pack 1.2.3 removes 47 distinct products and 5,651
product-location observations that Product Pack 1.2.2 admitted. The excluded classes include egg
salad, prepared breakfast foods, plant-based substitutes, scramble kits, noodles and bakery
products, appliances, and personal-care cleansers.

The change does not alter seller governance. Known third-party marketplace sellers remain a
Retailer Pack exclusion; this phase corrects category admission among otherwise eligible 1P or
seller-unverified products.

## Product Pack revision

- `fresh_shell_eggs` advances from 1.2.2 to 1.2.3.
- The report blueprint advances in lockstep to 1.2.3.
- New scope phrases are title/URL rules only. PDP descriptions are not scanned for exclusions,
  because a legitimate shell-Egg description may mention recipes such as egg salad or omelets.
- A broad `egg free` rule is forbidden: the generic plural-aware term matcher could interpret
  `Eggs Free Range` as that phrase. The production rule is the precise `egg free mayo` phrase.
- Regression fixtures retain difficult legitimate titles including `Happy Egg ...`, singular
  `Eggland's Best ... Egg`, and `Individually Wrapped Eggs`.

## Exhaustive candidate reconciliation

The complete 14-retailer Matching v2 build retains exactly 185 governed listing pairs with the
same retailer distribution as version 1.2.2. No listing pair was removed or added. Case and edge
identifiers change because they are derived from the immutable Product Pack checksum, which is
expected.

## Scope-only certification continuity

Queue import adds an explicit `scope_only_pack_revision` mode. It remains fail-closed and may be
used only with `carry_forward_certified` and an exact predecessor version. The database transaction
must prove all of the following:

1. Product Pack identity is unchanged.
2. The successor adds hard exclusion patterns and removes none.
3. Every other Product Pack field—including attributes, extraction, normalization, matching
   policy, profiles, retailer overrides, and reporting behavior—is identical after version
   references are removed.
4. Every finalized predecessor listing pair exists in the successor.
5. Each pair's listings, governed attributes, proposal, source evidence, and matching policy are
   identical after only revision-derived case/edge IDs and Product Pack checksum/version are
   removed.
6. Prior image evidence remains present; additive image evidence is allowed.

Compatible comparable and not-comparable submissions retain reviewer, rationale, tiers, evidence,
and a supersession link. New successor evidence references are added. Unresolved cases remain
unresolved. Import and carry-forward start no AI, PDP, or MetricsCart calls and never trigger
analysis automatically.

## Trust gates

- 47 product identities are removed from the current full source population; Walmart remains at
  174 in-scope product identities.
- The exhaustive candidate graph remains 185/185 listing pairs across all 13 competitors.
- Added-exclusion compatibility passes; removed exclusions or any matching-policy change fail.
- A changed governed attribute fails case continuity.
- Free Range Egg regression titles remain in scope.
- Known prepared, substitute, appliance, bakery, and cleanser titles remain out of scope.

## Production sequence

1. Deploy and immutably seed Product Pack/report blueprint 1.2.3.
2. Activate 1.2.3 for new Egg work.
3. Import exhaustive queue 4.0.0 as a scope-only successor of queue 3.0.0.
4. Verify 184 finalized decisions carry with provenance and one unresolved case remains pending.
5. Create a new checksum-bound gold-set release and immutable Egg replay.
6. Verify Price Intelligence, the Price Architecture Matrix, and Competitive Intelligence against
   the 1.2.3 scope. Pre-materialize all three default matrix methods during publication.

