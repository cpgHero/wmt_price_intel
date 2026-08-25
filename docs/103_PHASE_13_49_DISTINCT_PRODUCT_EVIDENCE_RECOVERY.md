# Phase 13.49 — Distinct-Product Evidence Recovery

## Decision

Matching review must not repeatedly pay to inspect, or repeatedly ask an administrator to
verify, the same retailer product merely because that product appears in several candidate
pairs. Label-derived evidence belongs to the immutable retailer listing inside one review
queue. A human-verified value may therefore be reused across every case containing that exact
listing when the Product Pack policy checksum, listing identity, attribute, normalized value,
source image, and original AI output remain bound to the persisted decision.

This capability reduces duplicated evidence work. It does not certify a product relationship,
weaken a hard blocker, alter Search or PDP evidence, or authorize an AI call.

## Evidence audit

The final Spring Valley coverage shadow uses all three retained collection runs and Product Pack
`1.2.9`. It contains 2,316 pair cases. The reduction from the earlier 2,398-case shadow is an
intentional scope correction: Walmart products `631199053` and `240505739` are topical skin oils,
not oral supplements, and are now explicit catalog exclusions. Their 82 contaminated pairs were
removed before the replacement queue was imported.

The source boundary is explicit and reproducible:

- 23,716 successful Search rows across Walmart and nine competitors;
- 2,324 retained PDP snapshots;
- 2,316 cases where both products have a positive Search-derived observed-location footprint;
- zero admitted cases with a known third-party seller;
- zero admitted known topical/non-oral products; and
- 74 configured Spring Valley anchors retained as catalog gaps because they had no
  positive-price Search observation.

The active-policy audit found 1,020 distinct products with unresolved hard evidence. A greedy,
deterministic minimum-coverage scope selects 883 pair cases that collectively expose every one
of those products. The unresolved population is not converted into matches by assumptions.

The audit is reproducible with `scripts/audit_matching_v2_evidence_gaps.py`. It is read-only and
produces product-, retailer-, attribute-, and reuse-level counts without mutating a queue.

## Implemented controls

### Queue-wide product evidence reuse

The certification view, individual submission path, legacy adjudication path, and bulk
certification snapshot now reconcile verified product evidence against all cases in the same
queue. Reuse is allowed only when:

1. the prior decision is `verified`;
2. its full proposal document is retained;
3. the proposal is eligible and image-source attributable;
4. the proposal policy checksum equals the current Product Pack policy checksum;
5. the listing ID is exactly one side of the current case;
6. the attribute still exists in the current Product Pack; and
7. the value passes current normalization again.

Two verified values for the same listing and attribute fail closed as a conflict. A new Product
Pack policy checksum prevents silent reuse. Raw evidence is never rewritten.

### Minimum-coverage AI scope

Match Certification exposes a separate **Review distinct product evidence** action. The server
uses deterministic greedy set coverage to choose pair cases that collectively expose the most
distinct products with unresolved hard evidence. Cases already carrying a final relationship
decision, an existing AI task, known third-party seller evidence, incomplete Search footprint,
or reusable verified evidence remain excluded under the existing gates.

The confirmation panel reports pair cases selected, distinct products covered, deferred pair
cases, model, per-case ceiling, and maximum exposure. It still requires explicit administrator
confirmation before creating paid AI work. The existing all-eligible and manually selected modes
remain available.

### Product Pack 1.2.9 deterministic and certification repair

The Vitamins & Supplements Product Pack and certification boundary now:

- recognizes governed active-ingredient evidence when a valid oral supplement title does not
  literally contain `vitamin`, `supplement`, `mineral`, or `amino acid`;
- uses plural-aware target terms;
- parses comma-formatted strengths and Billion-CFU labels deterministically;
- excludes additional non-oral smoothie, patch, juice-beverage, and cosmetic-eye-treatment
  noise; and
- treats scalar strength and unit as conditionally inapplicable only when both products are
  governed members of the approved multi-ingredient formula family;
- prevents PDP warning language such as “keep out of reach of children” and ambiguous
  comma-separated age-group values from becoming product life-stage evidence;
- distinguishes senior `50+` formulations from ordinary adult formulations; and
- treats unresolved values, Product Pack defaults, and zero-reliability inferences as unknown
  rather than positive evidence at the certification boundary; and
- prevents explicit catalog membership from overriding an explicit product-ID exclusion, which
  is how the two known Spring Valley topical products are now removed generically.

Zero automatic approval remains the policy. Life stage, ingredient/formulation, strength,
strength unit, dosage form, and named release profile still fail closed when applicable.

Brand remains descriptive. A private-label or national-brand competitor can match Spring Valley
only when the governed specifications agree. A brand name cannot rescue a specification
conflict.

## Boundaries

- The 74 Spring Valley catalog anchors without a positive-price Search observation remain
  explicit catalog coverage gaps; no product or price is fabricated.
- A multivitamin or complex formula does not always have one meaningful scalar strength. The
  conditional rule is limited to the governed multi-ingredient formula family and cannot make
  an exact-specification proposal; it only makes the pair eligible for evidence review.
- The 269 terminal PDP failures remain retained evidence. Billable 404s are not blindly retried.
- No new MetricsCart call was made for the evidence review; it uses retained Search, PDP, and
  label-image evidence.
- The owner authorized an aggregate OpenAI ceiling of `$50.00`. Recorded usage is
  `$41.7666525`; unused authority is `$8.2333475`.
- AI output is advisory evidence only. Source-attributable image proposals require an explicit
  human verification or rejection before they can influence certification.
- Queue import, AI evidence review, evidence verification, relationship certification, and
  reporting replay remain separate explicit actions.

## Release gates

1. API and Product Pack regression suites pass.
2. Web type checking, linting, and relevant UI tests pass.
3. The rebuilt shadow excludes known non-oral products and known third-party sellers.
4. All 74 unobserved anchors remain explicitly represented as catalog gaps.
5. Target and every other retailer retain governed private-label and non-private-label lanes.
6. Known adult/children, ingredient/formulation, strength/unit, dosage-form, and named-release
   conflicts produce zero certifiable relationships.
7. The distinct-product evidence scope selects no product whose current verified evidence is
   already reusable.
8. Every positive deterministic proposal receives a semantic audit.
9. The owner receives an estimated and maximum OpenAI cost before any paid review is launched.
10. Production import and paid AI work require explicit owner acceptance of the replacement
    shadow and aggregate cost ceiling.
11. Every paid output requires `requires_human_review=true`; comparable output may not coexist
    with a known or AI-declared hard conflict.
12. No AI proposal automatically mutates Product Pack evidence, certifies a relationship, or
    triggers reporting replay.

## Final shadow, import, and semantic verification

Queue `2026.08.25-spring-valley-coverage-shadow-8` was rebuilt and audited on Railway, then
imported as the operational certification replacement with carry-forward disabled. Its database
queue ID is `d0eac24f-574e-40ce-b44f-b00a33f5888f`. The result is deliberately conservative:

- 2,316 total cases;
- 2,310 unresolved cases;
- six deterministic candidates: one exact-specification and five equivalent-product proposals;
- zero inherited decisions or certifications;
- zero known third-party cases;
- zero candidate hard-blocker violations;
- zero positive hard-blocker values sourced from `unresolved` or `product_pack_default`;
- zero prohibited non-oral/noise titles; and
- zero senior-versus-ordinary-adult mismatch.

The complete queue, evidence-gap audit, and product-evidence selection manifest are durably
archived at
`s3://artifacts-usb-pmrd1jcxsy9/matching-v2/shadows/vitamins_supplements/2026.08.25-spring-valley-coverage-shadow-8.tar.gz`.
The verified archive is 21,713,581 bytes with SHA-256
`d39f23b0f72915b23511dfc58c40b72b9506ee65dd7f5827edbb113428e834e2`.

The active-policy minimum set cover reduces the eligible population to 883 pair-level calls that
collectively expose all 1,020 distinct products with unresolved hard evidence. It retains every
retailer:

| Competitor | Selected pair calls |
| --- | ---: |
| Amazon Same Day | 106 |
| BJ's | 38 |
| Costco | 31 |
| CVS | 83 |
| Kroger | 123 |
| Meijer | 171 |
| Sam's Club | 32 |
| Target | 131 |
| Walgreens | 168 |
| **Total** | **883** |

## Paid evidence-review ledger

The owner accepted a `$50.00` aggregate maximum. The governed execution stopped at
`$41.7666525`, leaving `$8.2333475` unused. Credit-balance and project-limit failures recorded
zero usage and were retried only after the owner restored the corresponding OpenAI control. Each
retry created a new linked task; no successful task was repeated and failure history was not
rewritten.

Across the clean Product Pack `1.2.9` queue:

- 366 unique pair cases completed AI evidence review;
- 499 of the 1,020 unresolved products were exposed in those completed cases;
- 167 drafts proposed `not_comparable`;
- 199 drafts proposed `insufficient_evidence`;
- zero drafts proposed a certifiable relationship;
- 1,224 attribute proposals were advisory;
- 610 proposals met the source-image, visible-label, confidence, active-attribute, and
  normalization eligibility gates; and
- the full semantic audit found zero hard guardrail failures.

The remaining 521 products have not received AI evidence review. They remain unresolved rather
than being inferred. The 610 eligible image proposals are also unresolved until a human verifies
or rejects them in Match Certification.

The evidence-gap audit, set-cover manifest, per-wave audits, complete paid-task ledger, per-case
results, cost reconciliation, and semantic audit are durably archived at
`s3://artifacts-usb-pmrd1jcxsy9/matching-v2/audits/vitamins_supplements/2026.08.25-spring-valley-shadow-8-ai-audit.tar.gz`.
The archive is 45,628 bytes with SHA-256
`2771c6c4ed75ff662d44e64005b36daa6153f8d29a69926b170c981b481d58ae`.

No AI draft or image proposal has automatically certified a match or changed reporting. The next
governed action is human attribute-evidence reconciliation, followed by relationship
certification and an explicit reporting replay.
