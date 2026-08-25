# Phase 13.47 — Governed Attribute-Evidence Reconciliation

## Outcome

Matching v2 now has a separate, append-only reconciliation step between advisory AI review and final relationship certification. Validated PDP/image evidence may resolve a missing or conflicting Product Pack attribute, but it never rewrites Search, PDP, AI, or review-queue source evidence.

## Eligibility gate

The server—not the browser—reconstructs every candidate attribute proposal from the latest successful AI task. A proposal is eligible only when all of the following are true:

1. the attribute exists in the currently active Product Pack;
2. the proposal is sourced from an image rather than an unattributed structured assertion;
3. the cited image URL is attached to exactly one side of the immutable pair;
4. the proposal quotes visible label text;
5. confidence is at least 0.85; and
6. the value normalizes under the Product Pack's declared number, enum, string, or array contract.

The proposal checksum binds the case checksum, AI task ID, AI output checksum, active Product Pack policy checksum, listing side and identity, attribute, raw and normalized values, source image, visible text, confidence, and eligibility reasons.

## Human decision and audit history

An identified administrator records `verified` or `rejected` plus a rationale. The database preserves the complete proposal snapshot, AI task, proposal checksum, reviewer, rationale, decision checksum, optional superseded decision, and timestamp. Decisions are immutable. A correction appends a superseding decision; it does not edit history.

Reconciliation is permitted only before a final match decision. Once a case has been certified, it must follow the existing explicit flag/reopen workflow rather than silently changing its evidence basis.

## Derived certification view

Only the latest verified proposal for the latest AI output is applied. It overlays the appropriate benchmark or competitor attribute in a derived view, records `human_verified_ai_vision` as the source, recomputes the attribute outcome under current Product Pack tolerance, and then runs the normal active-policy certification blockers.

If two active verified proposals disagree for the same product and attribute, neither value is selected and the case fails closed with a reconciliation conflict. Rejected, ineligible, stale-output, or structured-only proposals do not change certification evidence.

Individual approval and administrator bulk preview/commit consume this same derived evidence view. No reconciliation decision runs reporting automatically. Reporting still requires completion of the certification queue, a checksum-bound gold-set release, an explicit governed replay, and publication trust gates.

Phase 13.50 closes the remaining implementation gap: after this overlay, the generic deterministic
engine reruns under the named active Product Pack profile and recalculates the tier, evidence
coverage, and eligible price bases. The resulting certification-view checksum is shared by paid AI
input and every certification path. See
`docs/104_PHASE_13_50_DERIVED_CERTIFICATION_RECOMPUTATION.md`.

## Administrator experience

The Match Certification evidence drawer shows eligible and ineligible proposals separately. Each proposal identifies the product side, normalized value, visible label text, confidence, exact cited image, current decision, and ineligibility reasons. Verify/reject controls require reviewer identity and a written note. The attribute evidence table and blocker summary refresh after the decision so the administrator can see exactly what certification will use.

## Verification requirements

- schema/example validation;
- forward and reverse migration validation;
- unit tests proving raw evidence remains unchanged;
- unit tests proving verified image evidence can resolve a blocker;
- unit tests proving structured AI assertions cannot enter the lane;
- Matching v2 API and browser regression tests;
- Python and TypeScript type/lint checks;
- production migration, protected UI, and Spring Valley case audit before any certification proceeds.

No MetricsCart or OpenAI call is required by this phase. It uses already retained PDP, image, and AI evidence.

## Production verification — 2026-08-24

- Commit `904edf4` passed GitHub Actions run `32757946235`, including Python, TypeScript, migration round-trip, contract, browser, and all four container-build jobs.
- Railway production is at Alembic head `0047_attribute_reconcile`.
- The protected Match Certification route and web health route respond successfully.
- The active Spring Valley queue remains `2026.08.24-spring-valley-7` with 203 pending, uncertified cases and 203 successful advisory AI drafts.
- The server reconstructed 745 checksum-bound attribute proposals from retained evidence. Of those, 374 passed the Product Pack, source-attribution, visible-text, confidence, and normalization gates and are available for human verification; 371 remain advisory-only or ineligible.
- No evidence decision was created during deployment verification, no verified overlay was applied automatically, and no certification or reporting replay was triggered.
