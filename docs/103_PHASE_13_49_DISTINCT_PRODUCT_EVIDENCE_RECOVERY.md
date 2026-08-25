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

The final read-only Spring Valley coverage shadow uses all three retained collection runs and
Product Pack `1.2.7`. It contains 2,398 pair cases spanning 152 observed Walmart products and
1,335 competitor products. Seven hundred thirty-three products recur across cases, so
pair-by-pair evidence review would repeatedly inspect the same labels.

The source boundary is explicit and reproducible:

- 23,716 successful Search rows across Walmart and nine competitors;
- 2,324 retained PDP snapshots;
- 2,398 cases where both products have a positive Search-derived observed-location footprint;
- zero cases excluded for a known third-party seller because no admitted candidate carried
  known third-party evidence; and
- 74 configured Spring Valley anchors retained as catalog gaps because they had no
  positive-price Search observation.

The final evidence audit found 1,067 distinct products with unresolved hard evidence, all with
at least one image. Seven hundred eighty-four still have a substantive gap when release profile
is excluded. The unresolved population is not converted into matches by assumptions.

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

### Product Pack 1.2.7 deterministic and certification repair

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
  rather than positive evidence at the certification boundary.

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
- No additional MetricsCart or OpenAI call is authorized by this phase.
- The new shadow must be rebuilt and audited before any production queue import. Import, AI
  launch, certification, and reporting replay remain separate explicit actions.

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
10. Production import remains blocked until the shadow and cost plan are accepted explicitly.

## Final shadow and semantic verification

Queue `2026.08.25-spring-valley-coverage-shadow-6` was rebuilt on Railway without importing it.
The result is deliberately conservative:

- 2,398 total cases;
- 2,392 unresolved cases;
- six deterministic candidates: one exact-specification and five equivalent-product proposals;
- all six are visibly coherent fast-dissolve melatonin or vitamin B12 relationships;
- zero known third-party cases;
- zero candidate hard-blocker violations;
- zero positive hard-blocker values sourced from `unresolved` or `product_pack_default`;
- zero prohibited non-oral/noise titles; and
- zero senior-versus-ordinary-adult mismatch.

The complete queue, evidence-gap audit, and product-evidence selection manifest are durably
archived at
`s3://artifacts-usb-pmrd1jcxsy9/matching-v2/shadows/vitamins_supplements/2026.08.25-spring-valley-coverage-shadow-6.tar.gz`.
The verified archive is 21,910,849 bytes with SHA-256
`a0ff58d16f32b0a82a6eaff4c3de06aed306fb8e00aa164065797c0238d8d992`.

The active-policy minimum set cover reduces 2,389 evidence-eligible pair cases to 928 pair-level
AI calls that collectively expose all 1,067 distinct products with unresolved hard evidence.
That defers 1,461 redundant pair calls while retaining every retailer:

| Competitor | Selected pair calls |
| --- | ---: |
| Amazon Same Day | 106 |
| BJ's | 39 |
| Costco | 31 |
| CVS | 88 |
| Kroger | 123 |
| Meijer | 178 |
| Sam's Club | 33 |
| Target | 136 |
| Walgreens | 194 |
| **Total** | **928** |

Historical successful Matching v2 usage averages about `$0.0413167863` per task, producing a
planning estimate of **$38.34** for 928 calls. A **$50 aggregate maximum** is proposed. This is
not authorization: the shadow remains unimported, no OpenAI task has been created, and both
production import and the paid AI launch require the owner's explicit acceptance of the final
shadow and cost ceiling.

Source implementation is deployed at commit `ad9cd2a`. GitHub CI run `32808802572` passed the
Python, TypeScript, contract, migration, container-build, and browser-test gates. Railway was
verified to serve Product Pack `1.2.7` before the final rebuild.
