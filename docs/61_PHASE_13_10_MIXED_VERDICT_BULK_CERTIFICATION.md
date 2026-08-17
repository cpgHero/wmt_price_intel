# Phase 13.10 — Mixed-Verdict Bulk AI Certification

Status: deployed and production-verified

## Outcome

Match Certification can prepare one checksum-bound administrator batch containing both AI
recommendations that a pair is comparable and recommendations that it is not comparable. The AI is
still advisory: nothing becomes final until the administrator reads the preview and confirms the
exact displayed set.

## Verdict rules

- `comparable` requires one supported governed match tier. The final submission records that tier.
- `not_comparable` must not carry a match tier. The final submission records an empty tier list.
- `insufficient_evidence` is not a final conclusion and cannot be bulk-certified. It remains in the
  review workflow for more evidence or individual handling.
- A final decision, invalid AI output, known third-party seller, or missing immutable evidence is a
  blocking exclusion.
- Deterministic disagreement, incomplete coverage, Product Pack conflicts, AI conflicts, and lower
  confidence remain explicit advisory warnings that the administrator must acknowledge.

For a not-comparable AI recommendation, a deterministic rejection supports rather than conflicts
with that result. If the deterministic engine proposes a positive match, the preview displays a
specific verdict-disagreement warning.

## Audit and transaction integrity

Policy `guarded_ai_recommendation_bulk_certification` v1.2.0 binds the following into the
confirmation checksum:

- queue ID and version;
- server policy checksum;
- case and AI-output checksums;
- AI task ID;
- recommended verdict; and
- recommended tier, when applicable.

On confirmation, the API locks and re-evaluates every case and stops the entire transaction if the
preview is stale or a case is no longer eligible. One immutable bulk action is written with action
type `certify_ai_recommendations`, plus one normal final review submission per case. Every final
comment identifies the certified outcome, copies advisory warnings, and preserves the complete AI
evidence rationale. The response reports total, comparable, and not-comparable counts. Legacy
`approved_case_*` response aliases remain temporarily available so web and API replicas can roll
without breaking an in-flight request.

Migration `0037_bulk_ai_verdicts` retains the historical `approve_ai_matches` action
type and permits the new, outcome-neutral action type. Its downgrade restores the historical
constraint and is safe before new mixed-verdict actions are written, which is the expected boundary
for a data-bearing operational downgrade.

## Administrator experience

The queue-wide action now finds completed comparable and not-comparable recommendations under the
active retailer filter. The preview visibly states `matches` or `is not comparable with` for each
product pair, labels the proposed tier only for matches, lists warnings and exclusions, and asks the
administrator to finalize recommendations rather than “approve matches.” The completion message
separately reports comparable and not-comparable totals. Reporting does not rerun automatically;
all resulting decisions remain final until flagged.

## Verification gates

- policy tests for comparable, not comparable, insufficient evidence, invalid verdict/tier
  combinations, advisory warnings, and verdict-bound checksums;
- repository tests for dynamic verdict writes, empty tiers on not-comparable decisions, rationale
  preservation, and immutable action attribution;
- browser coverage for a mixed preview, explicit final confirmation, separate completion counts,
  and queue-wide discovery of a not-comparable recommendation beyond the visible page;
- web typecheck, lint, unit tests, Python lint/tests, reversible migrations, container builds, and
  preview-only production verification before deployment is marked complete.

## Production verification

- Commit `fd5a48a` passed GitHub Actions run `31988362130`: 487 Python tests, 57 web unit
  tests, 11 browser tests, contract/format/lint/type/build gates, migration
  upgrade/downgrade/re-upgrade, and all four service container builds.
- Railway deployed the compatible API and web revisions successfully. The API reports ready with
  Postgres available, and production Alembic revision `0037_bulk_ai_verdicts` is at head.
- The live Ground Beef pending queue exposed policy v1.2.0 with both allowed final verdicts. It
  contained five completed `not_comparable` recommendations and one `insufficient_evidence`
  recommendation.
- A protected, preview-only request submitted the five not-comparable case IDs. All five were
  eligible, none was excluded, every preview row preserved the `not_comparable` verdict, and the
  server returned a confirmation checksum. Conflict and Product Pack hard-blocker warnings appeared
  on all five; four also carried a lower-confidence attribute warning.
- The insufficient-evidence recommendation was not included in the finalizable set. The deployment
  check did not call the commit endpoint and did not accept, reject, flag, reopen, or otherwise
  change any live match decision.
