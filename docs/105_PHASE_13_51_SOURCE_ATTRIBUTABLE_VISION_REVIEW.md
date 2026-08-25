# Phase 13.51 — Source-Attributable Vision Review

## Problem found in production evidence

The production differential audit of vitamin queue
`2026.08.25-spring-valley-luna-shadow-9` found 105 attribute proposals in the latest successful
Luna drafts. Only two cited a retained product image; 103 repeated structured facts. Those
structured suggestions correctly could not enter governed reconciliation, so another large paid
run under the same contract would add cost without resolving certification evidence.

Image delivery was not the primary failure: only three of the latest 19 reviewed cases recorded an
image-download fallback. The main defect was that the response schema allowed the model to choose
a structured proposal even when label images were available.

## Governed correction

Prompt `matching_v2_evidence_review@1.3.0` and its request-specific Structured Output schema now:

- allow attribute proposals only when at least one retained product image is in the request;
- allow only attributes defined by the active Product Pack certification policy;
- use the Product Pack data type for each proposed value, including number, array, and enum;
- exclude Product Pack-declared unknown enum values;
- require `evidence_source=image`, an exact URL from the images sent to the model, and non-empty
  visible label text;
- bind each allowed image URL to the exact listing side and only the governed attributes whose
  value is actually missing or declared unknown on that side;
- treat a conflict between two known product values as comparison evidence—not permission to
  rewrite either value; and
- set the proposal limit to zero when images are absent or unavailable.

Post-response validation independently rejects structured proposals, inactive attributes,
uncited images, missing visible evidence, ambiguous cross-listing image references, and attempts
to replace an already resolved attribute. The API reconciliation lane repeats the resolved-value
check, which also makes pre-1.3.0 drafts fail closed. Search and PDP facts remain deterministic
governed inputs; AI cannot re-label them as new evidence.

## Trust boundary

Image proposals remain advisory. They do not change attributes, matches, certification, or
reporting until an administrator verifies the source-bound proposal. Verification triggers the
single derived certification recomputation defined in Phase 13.50. Normalized-unit eligibility is
recalculated only after product comparability exists; it never creates a relationship.

## Release sequence

1. Pass focused provider, API, reconciliation, and certification tests.
2. Pass the complete repository release gate and container builds.
3. Deploy the new prompt and provider contract.
4. Run a bounded, disclosed Luna pilot on cases with retained images and unresolved governed
   attributes.
5. Audit proposal source attribution, Product Pack validity, download warnings, spend, and derived
   certification impact before any scaled review.

No proposal is bulk verified or certified as part of the pilot.

## Bounded production pilot — 2026-08-25

Batch `dd810008-8a36-42fe-b382-882f039210b9` submitted 25 image-backed, distinct-evidence
coverage cases to `gpt-5.6-luna`. Twenty succeeded and five returned empty or truncated JSON after
their automatic retry. Recorded successful-call cost was `$0.1758222`. The successful drafts
produced 31 attribute proposals: all 31 were image-sourced, all 31 resolved to exactly one retained
listing image with visible text, all 31 were active Product Pack attributes, and all 31 passed the
server reconciliation eligibility checks. There were zero structured proposals, zero proposal
blockers, zero human decisions, and zero certification or reporting changes.

The failed responses exposed an execution-envelope issue rather than an evidence-governance issue.
OpenAI's Responses API counts reasoning tokens inside `max_output_tokens`. The matching worker now
uses medium reasoning and a 6,000-token response envelope for Luna, and provider errors record the
response status, incomplete reason, and output-token count instead of surfacing a generic JSON
decoder message. The five failed cases were retried once under that envelope and all five
succeeded for an additional recorded `$0.0467164`, with no warnings.

Across the final 25 successful pilot cases, recorded model cost was `$0.2225386` and the drafts
contained 67 source-attributable image proposals covering 65 distinct listing-attribute claims.
All had visible text, confidence was at least 0.90 (median 0.99), and no listing-attribute claim
conflicted across cases. The semantic audit then found that 8 of the 67 proposals attempted to
restate or replace values already marked resolved, including materially different dosage-form and
life-stage values. This is why structural source attribution alone was not accepted as sufficient.
Prompt/schema 1.3.0 and the independent API guard now restrict reconciliation to the remaining 59
genuinely unresolved side-attribute claims. The eight legacy claims are retained for lineage but
are ineligible; none changed certification or reporting.

The next production expansion, if approved after administrator review of the pilot evidence,
targets the 883 distinct-evidence coverage cases that cover all 1,020 unresolved product
identities—not all 2,316 pair-level cases. This avoids paying repeatedly for the same product label
evidence across different candidate pairs.
