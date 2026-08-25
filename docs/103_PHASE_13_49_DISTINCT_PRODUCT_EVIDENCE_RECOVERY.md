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

The read-only Spring Valley coverage shadow contains 648 pair cases but only 533 distinct
products: 130 Walmart products and 403 competitor products. Two hundred fifty products appear
in more than one case, and one product appears in 38 cases. Pair-by-pair review would therefore
reinspect the same labels unnecessarily.

All 533 products have at least one image. The evidence audit found:

- 321 products with a substantive missing hard attribute other than inferred standard release;
- 206 products whose only unresolved provenance is the inferred `Standard` release profile;
- recurring strength and strength-unit gaps caused in part by formatted labels such as
  `2,500 mcg` and `10 Billion CFU`; and
- non-oral Search noise including smoothies, patches, juice beverages, and cosmetic eye
  treatments that must never enter supplement matching.

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

### Product Pack 1.2.4 deterministic repair

The Vitamins & Supplements Product Pack now:

- recognizes governed active-ingredient evidence when a valid oral supplement title does not
  literally contain `vitamin`, `supplement`, `mineral`, or `amino acid`;
- uses plural-aware target terms;
- parses comma-formatted strengths and Billion-CFU labels deterministically;
- excludes additional non-oral smoothie, patch, juice-beverage, and cosmetic-eye-treatment
  noise; and
- retains the zero-automatic-approval, fail-closed life-stage, ingredient/formulation,
  strength, unit, dosage-form, and release-profile boundaries.

Brand remains descriptive. A private-label or national-brand competitor can match Spring Valley
only when the governed specifications agree. A brand name cannot rescue a specification
conflict.

## Boundaries

- The 74 Spring Valley catalog anchors without a positive-price Search observation remain
  explicit catalog coverage gaps; no product or price is fabricated.
- A multivitamin or complex formula does not always have one meaningful scalar strength.
  Formulation-aware conditional attribute applicability requires a separate governed design and
  gold set. This phase does not relax global strength requirements to manufacture recall.
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

## Verification status

Source implementation is complete and focused tests are green. Deployment, retained-evidence
shadow rebuild, semantic audit, pricing, and production import remain pending in this phase until
the corresponding gates are completed.
