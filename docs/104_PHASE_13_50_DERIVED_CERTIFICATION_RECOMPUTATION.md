# Phase 13.50 — Derived Certification Recomputation

## Outcome

Matching v2 now has one fail-closed derived certification view for queue display, paid AI input,
AI re-analysis, individual certification, bulk preview/commit, and gold-set release. Human-verified
PDP/image evidence cannot change only the screen while leaving the deterministic engine tier or
price-basis decision stale.

## Processing order

For every pending pair, the server:

1. starts from the immutable queue case and its checksum;
2. applies only current, source-bound, human-verified attribute decisions;
3. applies the active Product Pack's stricter roles and conditional applicability rules;
4. reconstructs both listing-evidence records from the derived attribute rows;
5. reruns the generic deterministic Matching v2 engine under the queue's named Product Pack
   profile;
6. replaces only the in-memory certification tier, status, evidence coverage, attribute outcomes,
   and eligible price bases;
7. runs the active certification blockers again; and
8. creates a certification-view checksum binding the queue case, active Product Pack, derived
   engine result, attribute evidence, price bases, reconciliation references, and recomputation.

The original queue edge and engine proposal remain immutable and are retained in the derived view
as `queue_engine_proposal`. A recomputation error, unknown Product Pack profile, verified-evidence
conflict, or policy-checksum mismatch removes the derived tier and price bases and blocks release.

## AI and certification consistency

- Paid AI task creation now consumes the same derived view shown to the administrator and used by
  certification. The earlier path applied active roles but omitted verified-evidence reconciliation.
- A pending case becomes eligible for AI re-analysis only when it has no active task and its latest
  stored AI-input checksum differs from the current derived input. Unchanged cases are not charged
  again.
- Bulk policy `guarded_ai_recommendation_bulk_certification@1.7.0` requires a successful
  recomputation and a valid certification-view checksum.
- Bulk confirmation and its immutable action audit bind the certification-view checksum. A change
  to verified evidence, deterministic tier, or eligible price bases invalidates the preview.
- Individual and bulk submissions retain a certification-view evidence reference plus every
  verified reconciliation decision reference used by the derived result.

## Evidence boundary

AI suggestions remain advisory. Structured AI attribute assertions cannot enter reconciliation.
Image proposals require an exact retained image, visible label text, at least 0.85 confidence,
Product Pack normalization, and a human verify decision. Values declared as Product Pack unknowns
cannot resolve missing evidence. Raw Search, PDP, image, AI output, queue cases, and prior decisions
are never rewritten.

## Production verification and audit — 2026-08-25

The latest vitamin queue is
`2026.08.25-spring-valley-luna-shadow-9` with 2,316 immutable candidates. It has 19 successful
latest Luna drafts containing 105 attribute proposals: 2 image-sourced and 103 structured. It has
zero attribute-evidence decisions, so this change did not silently alter a current human decision
or certification. All 2,316 cases recomputed successfully, with zero recomputation errors and zero
invalid certification-view checksums. The resulting distribution remained 2,310 unresolved, five
equivalent-product candidates, and one exact-specification candidate because no human-verified
attribute decision exists yet. No MetricsCart or OpenAI call was made for the audit.

GitHub Actions run `32897486492` passed Python tests, mypy, contract checks, migration
upgrade/downgrade/upgrade, TypeScript checks, production builds, 14 browser tests, and all four
container builds. Railway API and scheduler deployed commit `30d49d6` successfully.

## Verification requirements

- verified evidence changes an unresolved deterministic edge only in the derived view;
- package and normalized-unit price bases are recalculated by Product Pack rules;
- raw cases remain unchanged;
- declared unknown, structured-only, rejected, stale, and conflicting evidence fails closed;
- paid AI input, retry, queue display, individual certification, bulk certification, and gold-set
  export use the same helper;
- bulk checksums change whenever the derived certification view changes;
- Python tests, Ruff, mypy, TypeScript tests, browser tests, CI container builds, and production
  read-only differential audits pass before scaled AI work or certification resumes.
