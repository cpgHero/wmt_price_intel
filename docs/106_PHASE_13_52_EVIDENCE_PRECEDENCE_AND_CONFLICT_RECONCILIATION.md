# Phase 13.52 — Evidence Precedence and Conflict Reconciliation

## Problem

The first source-attributable vitamin pilot proved that exact product-label images could recover
missing attributes. It also exposed an unsafe simplification: every non-empty current value was
treated as resolved. That made a corroborating label, a more complete formula, and a direct
contradiction all appear as `attribute_value_already_resolved`.

The production audit of the 25-case pilot found 67 image proposals. The administrator completed
all 29 proposals that targeted missing evidence: 28 were verified and one was rejected. The other
38 proposals were all retained under the same generic reason. Fifteen were equivalent to the
current value; 23 differed and included both useful refinements and material conflicts.

## Governed evidence relationships

The server now classifies every exact-image proposal independently for the cited listing and
attribute:

1. `fills_unknown` — the current value is absent, declared unknown, unresolved, or only a Product
   Pack default;
2. `corroborates_existing` — normalized current and proposed evidence agree;
3. `refines_existing` — the label adds material tokens to a lower-authority string/array value;
4. `conflicts_with_existing` — the exact label contradicts the current value; or
5. `invalid` — source attribution, Product Pack membership, confidence, visible text, or
   normalization failed.

Corroborating proposals require no administrator decision and do not rewrite evidence. Missing,
refining, and conflicting proposals are reviewable only when the current source is not locked.
Product Pack/configured constants, governed brand resolutions, manual overrides, and previously
human-verified evidence cannot be replaced through this lane.

## Human-verified correction behavior

A verified refinement or correction changes only the derived certification view. It records the
superseded value, superseded source, reconciliation relationship, decision ID, and
`human_verified_ai_vision` source before rerunning the deterministic engine. Raw Search, PDP, AI,
queue, and earlier decision evidence remains immutable.

When verified product evidence is reused for the identical listing elsewhere in the queue, the
target case repeats the source-authority check. A conflict with locked target evidence fails
closed instead of silently overwriting it.

## AI evidence boundary

Prompt `matching_v2_evidence_review@1.4.0` may cite a visible label fact that completes missing
evidence, corroborates a value, materially refines lower-authority Search/PDP extraction, or
identifies an exact-label contradiction. The request schema still binds each proposal to one
retained image, one listing side, one active Product Pack attribute, visible text, and a typed
value. Structured assertions remain prohibited. AI never chooses source precedence or applies a
correction; the server classifies the relationship and an identified administrator decides every
value-changing proposal.

## Brand and title evidence

Brand resolution remains deterministic and foundation-governed. The existing retailer/global
brand resolver uses exact canonical names and aliases, then an unambiguous token-boundary title
fallback. A title does not become a governed brand merely because an LLM recognizes it. The
forthcoming vitamins brand foundation update must be imported, schema-validated, and regression
tested before a successor queue is regenerated. This preserves extensibility without hard-coding
vitamin brands in matching or reconciliation code.

## Release gates

- existing checksum-bound decisions must remain attached after the classification change;
- verified conflict correction must retain superseded evidence and recompute deterministically;
- corroborating proposals must require no action;
- locked governed evidence must remain non-replaceable;
- prompt/schema validation must reject uncited, structured, cross-listing, and locked-source
  proposals;
- API, agent, web, browser, full Python, TypeScript, and container tests must pass;
- production must reconcile the pilot counts and report the new relationship distribution before
  another paid AI run or match certification.

No MetricsCart or OpenAI call is required to implement or validate this phase.

## Production verification

Commit `7f731ba` deployed successfully to the Railway web, API, worker, and scheduler services.
GitHub Actions run `32918348483` passed Python, TypeScript, all 15 browser tests, migrations,
contracts, and all four container builds. The local full Python suite passed 746 tests with 16
environment-dependent integrations skipped.

The read-only production differential audit reconciled the original pilot to 67 proposals and 65
distinct claims. All 29 administrator decisions retained their original checksum binding: 28
remain verified and one remains rejected. The corrected relationship distribution is 31 missing
values, 29 corroborations, two refinements, and five conflicts. The 29 corroborations now require
no action. Nine previously hidden source-attributable proposals are actionable: two missing-value
completions, two refinements, and five corrections to lower-authority Search/PDP extraction. No
locked governed source was exposed for replacement.

No MetricsCart or OpenAI call was made during implementation or the production audit.
