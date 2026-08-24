# Phase 13.46 — Vitamin Match Trust Reset

## Outcome

The Spring Valley vitamin certification queue is not safe for reporting. Its decisions are quarantined and will not be carried into a successor queue. The retained Search, PDP, AI, and human-review records remain immutable audit evidence; they are not authoritative product relationships.

## Confirmed defect

The `vitamins_supplements@1.0.5` policy treated `active_ingredient` and `life_stage` as soft comparison evidence and allowed `comparable_substitute`. That policy permitted relationships such as an Adult 50+ multivitamin versus a children's multivitamin. The issue is systematic rather than an isolated model response:

- 315 completed AI drafts proposed a comparable relationship;
- 76 of those proposals contained a life-stage conflict;
- 47 contained an active-ingredient conflict;
- only 19 had complete critical deterministic evidence; and
- 300 AI recommendations had already received a final bulk human decision, including three adult-to-children relationships.

No current vitamin decision is eligible for successor carry-forward, gold-set release, analysis replay, or reporting.

## Corrected policy

`vitamins_supplements@1.1.1` is fail-closed:

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

The replacement queue must:

- be generated from retained Search and PDP evidence under Product Pack 1.1.1;
- set `carry_forward_certified=false` and begin with zero final decisions;
- contain no adult/children, prenatal/non-prenatal, sex-specific, senior/children, active-ingredient, strength, strength-unit, dosage-form, or release-profile conflicts among comparable proposals;
- keep unknown required identity evidence unresolved;
- demonstrate package-count-only equivalent products separately from exact-package matches;
- pass deterministic regression, schema, queue checksum, seller-governance, observation-footprint, and representative case audits before any new paid AI review; and
- remain non-authoritative until complete human certification and a new checksum-bound gold-set release.

## Cost boundary

This reset uses existing evidence. It makes no MetricsCart or OpenAI call. Additional AI review is blocked until the deterministic successor audit passes and the owner separately approves the disclosed case count and spend.

The first fail-closed dry run under Product Pack 1.1.0 produced zero candidates because unknown critical evidence was being treated as both a certification blocker and a candidate-discovery blocker. It was not imported. Product Pack 1.1.1 keeps the certification blocker but permits bounded lexical evidence-review candidates when a critical value is unknown; this is a generic policy switch and does not weaken final certification.
