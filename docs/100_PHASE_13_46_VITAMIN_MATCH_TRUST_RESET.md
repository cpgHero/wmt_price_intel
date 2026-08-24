# Phase 13.46 — Vitamin Match Trust Reset

## Outcome

The former Spring Valley vitamin certification queue is not safe for reporting. Its decisions are quarantined and were not carried into the clean successor queue. The retained Search, PDP, AI, and human-review records remain immutable audit evidence; they are not authoritative product relationships.

Production queue `2026.08.24-spring-valley-7` is the clean successor. It contains 203 pending, unresolved candidates and zero inherited decisions, AI drafts, or active AI tasks. It remains non-authoritative until its cases receive new evidence review and human certification under Product Pack 1.1.2.

## Confirmed defect

The `vitamins_supplements@1.0.5` policy treated `active_ingredient` and `life_stage` as soft comparison evidence and allowed `comparable_substitute`. That policy permitted relationships such as an Adult 50+ multivitamin versus a children's multivitamin. The issue is systematic rather than an isolated model response:

- 315 completed AI drafts proposed a comparable relationship;
- 76 of those proposals contained a life-stage conflict;
- 47 contained an active-ingredient conflict;
- only 19 had complete critical deterministic evidence; and
- 300 AI recommendations had already received a final bulk human decision, including three adult-to-children relationships.

No current vitamin decision is eligible for successor carry-forward, gold-set release, analysis replay, or reporting.

## Corrected policy

`vitamins_supplements@1.1.2` is fail-closed:

1. active ingredient or governed formulation, strength, strength unit, dosage form, release profile, and life-stage/audience are hard blockers;
2. those attributes must be known before a comparable relationship can be certified;
3. adult, children, prenatal, men, women, senior, and general-audience conflicts are non-comparable;
4. broad `comparable_substitute` relationships are prohibited;
5. complete critical evidence is required for an equivalent product;
6. a package-count difference may support normalized-unit comparison only after all identity attributes agree; and
7. candidate retrieval retains audience, dosage-form, release, and strength-unit identity words instead of discarding them as stop words.

Candidate discovery and certification are deliberately separate gates. A lexical candidate may enter evidence review when a critical value is missing on either side, but the missing value remains a release blocker. Known critical conflicts are excluded from the candidate funnel. This preserves recall for PDP/vision-assisted review without allowing incomplete evidence to become a certified match.

Brand remains non-authoritative because Spring Valley will normally compare with a competitor brand or private label. Brand disagreement cannot override a specification match and brand agreement cannot rescue an identity conflict.

## Generic certification safeguard

The certification API now derives allowed relationship tiers from the active Product Pack. Individual certification, adjudication, administrator bulk acceptance, and gold-set export reject a tier prohibited by the current Product Pack. Applying a stricter Product Pack to a historical immutable queue creates a derived certification view; it never edits the older queue or its submissions.

## Successor requirements

The replacement queue was required to:

- be generated from retained Search and PDP evidence under Product Pack 1.1.2;
- set `carry_forward_certified=false` and begin with zero final decisions;
- contain no adult/children, prenatal/non-prenatal, sex-specific, senior/children, active-ingredient, strength, strength-unit, dosage-form, or release-profile conflicts among comparable proposals;
- keep unknown required identity evidence unresolved;
- demonstrate package-count-only equivalent products separately from exact-package matches;
- pass deterministic regression, schema, queue checksum, seller-governance, observation-footprint, and representative case audits before any new paid AI review; and
- remain non-authoritative until complete human certification and a new checksum-bound gold-set release.

## Clean successor audit and import

The final retained-evidence dry run passed the deterministic queue gate and was imported on August 24, 2026:

- queue ID: `vitamins_supplements-matching-v2-operational-certification`;
- queue version: `2026.08.24-spring-valley-7`;
- Product Pack: `vitamins_supplements@1.1.2`;
- queue checksum: `3597c4d11b4c42e81bba2cc63c5da14b232de77cd2aa463f5c47ea8ca268f439`;
- 203 cases, all `pending`, `unresolved`, and without an engine-assigned comparable tier;
- zero carried-forward decisions, final submissions, AI drafts, active AI tasks, known hard-blocker conflicts, known seller-ineligible listings, or zero-observation listings; and
- coverage across Amazon Same Day (23), BJ's (7), Costco (7), CVS (44), Kroger (35), Meijer (23), Sam's Club (8), Target (8), and Walgreens (48).

The audit also searched product titles for adult/children and prenatal/non-prenatal audience conflicts. One substantively related prenatal-iron versus general-iron candidate remains in the evidence-review funnel. It is not a match: the engine leaves it unresolved, and missing governed ingredient, strength, and life-stage evidence blocks comparable certification. That case must be explicitly resolved from authoritative evidence or rejected.

The production queue view confirms Product Pack 1.1.2 is active, the old queue's quarantine is not inherited by the new queue, and every incomplete case exposes certification blockers. No old vitamin approval or rejection was preserved.

## Cost boundary

This reset uses existing evidence. It made no MetricsCart or OpenAI call. The deterministic successor audit now passes. Any paid AI review of the 203 clean cases still requires a separate owner approval after the exact model and maximum spend are disclosed.

The first fail-closed dry run under Product Pack 1.1.0 produced zero candidates because unknown critical evidence was being treated as both a certification blocker and a candidate-discovery blocker. It was not imported. Product Pack 1.1.2 keeps the certification blocker but permits bounded lexical evidence-review candidates when a critical value is unknown; this is a generic policy switch and does not weaken final certification. A second dry run at the original 0.05 lexical threshold produced 2,045 unresolved candidates and 50 obvious audience-conflict pairs. It was also withheld. Version 1.1.2 raises the review-funnel similarity floor to 0.15; the retained-evidence audit showed this removes 49 of those 50 conflicts while preserving the one substantively related prenatal-iron versus iron pair for explicit rejection review.

## Owner-approved AI evidence review

The owner subsequently approved a paid `gpt-5.6-terra` evidence review of all 203 clean successor cases. Billing-limit and prepaid-balance failures were retained as immutable, zero-cost retry history. After credits were restored, every case completed successfully:

- 203 of 203 cases have a latest successful advisory draft;
- zero cases remain queued, running, or failed;
- all 203 drafts explicitly require human review;
- successful draft usage totals `$16.4078975`;
- 81 drafts recommend `not_comparable`;
- 114 recommend `insufficient_evidence` and therefore cannot become a final decision;
- eight recommend a comparable relationship: six `equivalent_product` and two `exact_specification`; and
- zero drafts propose the prohibited `comparable_substitute` tier.

The initial server-owned bulk-certification preview exposed a further trust defect: it offered 50 `not_comparable` recommendations even when the deterministic record had no known hard-blocker conflict. One reviewed case labeled identical melatonin products not comparable because a structured PDP ingredient value contradicted both the title and supplied product image. Policy 1.4.0 therefore requires a known deterministic Product Pack hard-blocker conflict before an AI rejection is bulk-eligible. AI-only conflicts, unknown required values, and internally contradictory evidence remain individual-review cases. The server continues to block all 114 insufficient-evidence drafts and all eight positive match proposals because the current deterministic evidence contains unresolved Product Pack hard blockers. Image-derived assertions never silently rewrite governed listing evidence or bypass certification.

A semantic audit found no AI-proposed comparable relationship whose product titles conflict on adult, children, senior, prenatal, men, or women audience markers. The previously certified adult-to-children relationships are absent from the clean successor queue. All 203 cases remain unresolved and no AI recommendation was automatically certified or released to reporting. Until policy 1.4.0 is deployed and the preview is rerun, administrators must not bulk-certify the vitamin queue.
