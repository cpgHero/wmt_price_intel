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

Prompt `matching_v2_evidence_review@1.2.0` and its request-specific Structured Output schema now:

- allow attribute proposals only when at least one retained product image is in the request;
- allow only attributes defined by the active Product Pack certification policy;
- use the Product Pack data type for each proposed value, including number, array, and enum;
- exclude Product Pack-declared unknown enum values;
- require `evidence_source=image`, an exact URL from the images sent to the model, and non-empty
  visible label text;
- instruct the model to inspect every supplied image on both products and report every reliably
  visible unresolved or conflicting governed attribute; and
- set the proposal limit to zero when images are absent or unavailable.

Post-response validation independently rejects structured proposals, inactive attributes,
uncited images, and missing visible evidence. Search and PDP facts remain deterministic governed
inputs; AI cannot re-label them as new evidence.

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
decoder message. Only the five failed pilot cases are retried after deployment.
