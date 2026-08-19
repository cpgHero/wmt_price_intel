# Phase 13.18 — Flat Leadership Navigation and Governed Replay

Status: deployed and production-verified

## Outcome

Competitive Intelligence removes the nested Product Leadership workspace rail. Its eight views
become first-class report tabs so one tab selection always identifies the visible analytical
workspace.

## First-class report order

1. Executive Overview
2. Price Architecture
3. Leadership Overview
4. Competitive Footprint
5. Match Group Analysis
6. Price Ladders
7. Store Comparisons
8. Market Performance
9. Competitive Exceptions
10. Competitive History
11. Assortment & Whitespace
12. Data Integrity

The leadership tabs retain one shared context: competitor retailer, comparison basis, benchmark
product, 1/3/5-mile radius, benchmark state, and benchmark city. Switching a leadership tab does
not reset that context.

After the report settles, it prewarms the current immutable leadership response. The visible
leadership tabs reuse that same in-flight or completed response so moving between them does not
repeat the expensive artifact reconstruction. API trust certification and immutable analysis
identity remain authoritative.

## Compatibility

Legacy links using `tab=product-leadership` and an optional `leadership` value are translated to
the corresponding first-class tab. The obsolete `leadership` query parameter is removed from the
normalized URL. No metric, relationship, location, or evidence contract is changed by the
navigation refactor.

## Governed Egg replay

After the navigation deployment passes CI, the current complete Egg certification gold set will
be replayed from its immutable source analysis. The replay must:

- disable automatic match fallback;
- include certified comparable relationships only in price comparisons;
- preserve certified not-comparable decisions as exclusions;
- reconcile certified and unresolved counts to the release coverage contract;
- regenerate retailer/cohort product evidence with current brand governance; and
- publish new immutable analysis and report identifiers instead of mutating the prior report.

The ordinary replay operation remains idempotent. A current-code rebuild of the same immutable
source result and gold-set release must set `force_rebuild`, include a non-empty audit reason, and
allocate the next serialized `replay_generation`. Generation 2 and later append `-rN` to the
analysis ID. Source, release, checksum, certification coverage, and decisions remain unchanged.
Only a forced, reason-bearing rebuild may resolve an archived immutable source result; ordinary
replays continue to require an active source. This supports recoverable report-library cleanup
without unarchiving or copying the source and without weakening the audit trail.

The radius-based Product Leadership API remains authoritative for physical-store 1/3/5-mile
reporting and same-ZIP service-area reporting. Legacy exact-ZIP scorecards may be retired only when
their replacement portfolio/cohort read models have equivalent certification and reconciliation
tests; a replay must not merely relabel old ZIP metrics as radius metrics.

## Trust gates

1. Exactly one main report tab is selected and no nested Product Leadership tab rail is rendered.
2. All eight leadership tabs retain the selected product, competitor, basis, radius, state, and
   city.
3. Legacy Product Leadership URLs resolve to the intended first-class tab.
4. Replay certification coverage reconciles exactly to the immutable queue and gold set.
5. Known third-party products remain excluded under Retailer Pack seller policy.
6. Brand-type summaries are sourced from governed product identity; unresolved types stay labeled
   rather than inferred.
7. For physical retailers, comparable-store counts are monotonic across 1, 3, and 5 miles for an
   unchanged relationship and benchmark footprint.
8. First-load latency and cached-load latency are measured separately; a slow request may not
   yield a partial or stale result.

## Production verification

- CI run `32290777122` passed Python, contracts, migration round trips, TypeScript, unit tests,
  thirteen browser tests, and the API, web, worker, and scheduler container builds.
- Generation 2 run `7ff16d97-8fb4-4d26-8698-a59339343ac2` succeeded on its first attempt and
  produced result `82e98dbb-5c9e-465e-af1a-cd029ae65d45` / analysis
  `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-de5fc82e-r2`.
- The result preserves release `de5fc82e-27e9-40c4-a284-ffea2989f261`, checksum
  `970b02be6e171c5649b3c9c6e66be138fdcbf01d2fce7b80f6f62fc21e9fbc35`, all 185 selected
  candidates, 183 certified-comparable decisions, one certified-not-comparable decision, and one
  unresolved exclusion. Automatic fallback is disabled.
- Compatible-spec renders evidence for 11 of 13 retailers and 11,062 matched observations;
  strict exact-spec independently renders three of 13 retailers and 537 matched observations.
- A Target physical-store check for benchmark product `10449724` reconciles monotonically from
  496 scored stores at one mile to 1,255 at three miles and 1,743 at five miles, against the same
  3,068 observed benchmark-store denominator.
- All twelve first-class report tabs render populated or explicit capability-bounded states. No
  nested Product Leadership rail remains.
