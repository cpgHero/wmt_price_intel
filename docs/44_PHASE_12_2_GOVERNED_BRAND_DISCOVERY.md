# Phase 12.2 — Governed Brand Discovery and Canonical Mapping

## Outcome

Observed brand variants that fail exact Brand Foundation resolution can now be reviewed as
possible mappings to an existing canonical brand. The workflow closes the gap between preserving
the immutable approved foundation and recognizing retailer/PDP variants such as `Mayfield` versus
`Mayfield Dairy Farms`.

No candidate changes reporting by itself. A user must confirm the canonical identity, save an
immutable Brand Workbench revision, and explicitly re-evaluate the report. Re-evaluation reuses
persisted Search and PDP evidence and queues no provider or AI calls.

## Authority and safeguards

- Exact canonical and approved alias resolution remains the only automatic resolution path.
- Candidate generation is deterministic review evidence, not a new resolver fallback.
- Private-label candidates are restricted to their owning retailer and retain the existing strict
  retailer-owned eligibility test.
- Regional and national candidates are global identities; a suggestion does not claim retailer
  presence.
- Known alias conflicts remain ambiguous even when their text score is high.
- A confirmed mapping must name a candidate returned for that observed retailer/brand/category and
  must use the candidate's governed role.
- Role-only classification remains available when the observed brand is genuinely new and should
  not map to the existing foundation.

## Candidate evidence

Candidate scoring uses normalized name evidence only:

1. known quarantined alias conflicts;
2. equal core names after common corporate/category suffixes;
3. qualified prefix relationships;
4. token containment or overlap; and
5. normalized spelling similarity.

Category compatibility and priority-brand status may add only a small score adjustment. They
cannot turn a weak name into a confident candidate. Candidates below 75 are suppressed; candidates
below 80 remain ambiguous. The workbench exposes up to three candidates, their score, governed
brand bucket/class, role, scope, and rationale. Close scores and known conflicts are labeled
ambiguous and require an explicit choice.

## Persistence and reporting

The observed retailer/brand key remains the immutable rule key. A confirmed mapping stores the
canonical brand ID and name in the rule's evidence document. The governed resolver then projects
that canonical identity in Price Monitoring and Competitive Intelligence when the revision is
applied. Older role-only revisions continue to work unchanged.

The existing `brand_discovery_queue` remains the cross-study intake for unresolved identities.
Study profiling continues to seed it without altering the active foundation. Analysis-scoped Brand
Workbench decisions provide the audited review surface; promotion into a later Brand Foundation
version remains a separate publish action.

## Acceptance checks

- `Mayfield` proposes `Mayfield Dairy Farms` but remains unclassified before confirmation.
- `Prairie farms dairy` proposes `Prairie Farms` but remains unclassified before confirmation.
- the Whole Foods Market Kitchen conflict returns both supplied candidates as ambiguous;
- a canonical mapping with a mismatched ID or role is rejected server-side;
- a confirmed canonical mapping is reproduced by the worker and Price Monitoring resolver;
- the approved Brand Foundation file is never mutated; and
- saved decisions do not reanalyze until the user explicitly requests it.
