# Phase 13.29 — Certified Relationship Profile Eligibility

## Status

Implemented, deployed, replayed, semantically audited, and production-verified
on August 21, 2026. The corrected generation is the sole active Milk report.

## Problem caught before release

The completed Milk certification produced one immutable gold set with 1,064
final labels: 887 comparable and 177 not comparable. The first governed replay
correctly disabled automatic fallback and passed AnalysisResult formula and
lineage checks. Its nine radius-native portfolio documents were internally
consistent, but a cross-profile population audit found that All Brand, Private
Label, and Same Brand Exact contained identical relationships and outcomes.

That result was not trustworthy. Certification says whether a pair is a valid
product comparison; it does not say that the pair belongs in every analytical
brand view. The replay had assigned each certified rule to every exact-location
profile. Governed rules then correctly bypassed automatic matching, but also
bypassed the profile-specific brand policy. The comparison-basis selector was
therefore changing its label without changing its population.

The first replay generation remains immutable audit evidence. It was briefly
visible while acceptance was in progress, but it was never accepted as the
governed release. After the semantic defect was confirmed, its exact
AnalysisResult was recoverably archived and its portfolio materializations
were rejected as release artifacts.

## Generic correction

The worker now segments each certified-comparable relationship after Search,
PDP, brand, and seller evidence have been normalized and before comparisons are
calculated:

- an `ignore_brand` profile includes every certified-comparable relationship;
- a `private_label_equivalent` profile includes a pair only when both products
  have governed strict-private-label evidence;
- a `same_brand` profile includes a pair only when both normalized brand
  identities are known and equal, including governed Product Pack aliases; and
- missing or ambiguous brand evidence fails closed for restrictive profiles but
  remains eligible for the inclusive profile.

Certified not-comparable decisions remain rejected across all profiles. The
correction does not rematch products, weaken human authority, or infer a new
decision. It only determines where an already-certified relationship may be
reported. The behavior is driven by each Product Pack's `brand_policy`; no Milk
category branch was added.

Every certified-comparable relationship must remain eligible for at least one
exact-location profile. A Product Pack that offers only restrictive brand views
without enough governed brand evidence now fails replay instead of silently
dropping the relationship.

## Release gates

The corrected Milk generation may become active only when all of the following
hold:

1. the gold-set checksum and 1,064-case coverage remain unchanged;
2. all 887 certified-comparable relationships are retained in the inclusive
   identity ledger and all 177 not-comparable decisions remain excluded;
3. automatic match fallback remains disabled;
4. All Brand, Private Label, and Same Brand Exact populations reflect their
   configured brand policies and are not an accidental duplicate;
5. all nine comparison-basis × 1/3/5-mile portfolio documents exist;
6. count partitions, rates, denominators, relationship/product rollups, retailer
   scope, and radius monotonicity pass the semantic release audit;
7. the AnalysisResult is ready to share with full metric-reference coverage and
   no unsupported numeric claims; and
8. production Competitive Intelligence and Price Intelligence routes pass
   live acceptance.

Only after those gates pass may the replacement become active and the exact
obsolete Milk report be recoverably archived. Search data, raw objects, PDP
evidence, certification decisions, immutable releases, failed or superseded
replays, portfolio documents, and audit lineage are never deleted.

## Completed release evidence

- focused analytics, worker, and portfolio suites: 43 passed;
- complete Python release gate in GitHub Actions: passed;
- Ruff formatting and lint: passed;
- mypy: passed across 148 source files;
- contracts and reversible database migrations: passed;
- TypeScript lint, typecheck, tests, production build, and 13 browser tests:
  passed;
- all four service containers: built successfully;
- GitHub Actions run `32485954699`: passed;
- Railway API, worker, and scheduler run commit
  `ab897839070befb1fae14e2f2eba6db33bb5b35a`;
- immutable Milk gold-set release:
  `28e0850f-6b1b-4a33-bc0e-fc77ef2f6579`;
- gold-set checksum:
  `f7c2ec2e7c5a83c8d09108cadd332ee75c6d77e4c7bdb226f57410eb6b7a0716`;
- corrected replay generation two run:
  `45ab5aba-c993-4f47-bcf1-b70e4d1982eb`;
- active AnalysisResult:
  `d643df96-4686-4e29-8479-374d13b823a2`;
- active analysis:
  `fresh_fluid_milk-19a350ee-90d7-4ec5-92f9-467a15c116b4-match-v2-28e0850f-r2`;
- AnalysisResult checksum:
  `d9c286813ef6fb3f4bfeb428c4071c643abcd063f7baf1d4eebf8b2d48080c71`;
- ready-to-share publication:
  `6e495333-5b74-4a09-a303-865b4156fd7d` with checksum
  `4283c92749fa2630d313e60667fe14ffb97537cb4a2904d827e8bb7d7747ecf0`;
- metric-reference coverage: 100%; unsupported numeric claims: zero;
- automatic match fallback: disabled; and
- no MetricsCart or OpenAI call was made.

## Profile and evidence reconciliation

The corrected publication retains all 887 certified-comparable relationships
in the inclusive identity ledger and segments them as follows:

| Competitor | All Brand | Private Label | Same Brand Exact |
| --- | ---: | ---: | ---: |
| ALDI | 239 | 17 | 0 |
| Amazon Same Day | 648 | 70 | 49 |
| Total | 887 | 87 | 49 |

The exact-location evidence inputs are also distinct: ALDI contributes 25,874
All Brand rows and 16,353 Private Label rows; Amazon Same Day contributes
28,832 All Brand rows, 6,379 Private Label rows, and 4,875 Same Brand Exact
rows. Classified Search evidence reconciles to 222,532 Walmart, 39,142 ALDI,
and 66,880 Amazon rows inside the unchanged 348,980-row source manifest.

All nine profile-by-radius documents materialized from the exact active
AnalysisResult revision. The semantic portfolio audit passed with zero errors.
Its three warnings are intentional ALDI Same Brand Exact no-relationship states
at 1, 3, and 5 miles. ALDI physical-store evidence grows monotonically with
radius; Amazon Same Day remains constant because it is governed as a same-ZIP
service area rather than a physical-store radius.

## Production acceptance and archival

Live browser acceptance confirmed that:

- the comparison-basis selector changes the population from 887 All Brand to
  87 Private Label to 49 Same Brand Exact relationships;
- the 3-to-5-mile change increases ALDI Private Label scored locations from
  23,130 to 27,197 while Amazon Same Day remains at 7,321;
- ALDI Same Brand Exact renders an explicit zero state instead of borrowing
  All Brand evidence;
- Competitive Intelligence and Price Intelligence load the corrected source,
  with no browser errors or warnings; and
- exactly one unarchived Milk AnalysisResult remains in production.

The rejected first-generation AnalysisResult
`8ba65584-a11d-453b-bafb-d32ce1fa5cc1` was recoverably archived at
`2026-08-21T13:26:00.874349Z`. The audit event
`analysis_result_archived_after_semantic_rejection` records why. No Search
data, raw object, PDP evidence, certification decision, immutable release,
materialization, superseded report, or audit lineage was deleted.
