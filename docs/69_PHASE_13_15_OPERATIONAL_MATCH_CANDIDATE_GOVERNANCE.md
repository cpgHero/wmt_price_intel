# Phase 13.15 — Operational Match Candidate Governance

Status: implementation and release validation

## Problem corrected

The first Egg Matching v2 reporting release treated a bounded validation queue as though it were
the complete operational relationship graph. A later exhaustive implementation over-corrected by
placing every unresolved Walmart-to-competitor cross-product into certification. Neither behavior
is acceptable:

- a validation sample cannot establish complete reporting coverage;
- an arbitrary cross-product is not a meaningful match candidate and creates an expensive,
  misleading human/AI review queue.

The prior release remains immutable audit evidence, but it must not be presented as the final Egg
comparison graph.

## Correct authority split

Matching v2 now distinguishes two queue purposes:

1. `human_gold_set_adjudication` is a bounded validation sample used to measure evaluator quality.
   It cannot drive a governed production replay.
2. `operational_match_certification` contains every pair that earned a governed Product Pack
   candidate tier. It is exhaustive within that declared candidate universe and is eligible for
   certification and replay.

Pairs with a hard incompatibility are deterministically excluded. Pairs that do not have enough
attribute evidence to earn any governed tier are also excluded from pair certification and counted
as `unresolved_without_governed_tier`. They belong in product-evidence remediation, where PDP,
brand, alias, and optional image-derived attributes can be improved once per distinct product.
After remediation the candidate graph is regenerated. This avoids paying AI to inspect thousands
of arbitrary product pairs while preserving an explicit account of missing evidence.

## Operational queue contract

An operational queue records:

- every admitted governed candidate in `cases`;
- admitted counts in both `available_counts` and `selected_counts` (these must be equal);
- unresolved, hard-blocked, and hard-block audit-sample counts in
  `sampling.excluded_counts`;
- immutable source, Product Pack, policy, and checksum provenance.

A zero-case operational queue is valid. It means no pair earned a governed candidate tier; it must
not be replaced by synthetic or automatic matches.

## Performance and grain

Search observations retain their location-specific price, availability, sponsorship, and time.
Classification work that depends only on product identity, PDP evidence, seller governance, brand
governance, and Product Pack attributes is cached by a conservative product-evidence signature.
The cached classification is then attached to each original location observation. Price-derived
metrics are never copied between locations.

## Egg release-candidate validation

Using `CCF_Search_Data_08.17.2026_v1.csv` and the raw Egg PDP archive:

- 393,110 source rows were read;
- 365,723 unique normalized observations were retained;
- normalization failures: 0;
- expected-retailer mismatches: 0;
- governed operational candidates: 226;
- generated review queue size: approximately 3.6 MB;
- the queue and evidence profile both pass their JSON Schemas.

The former diagnostic cross-product contained 61,328 cases and occupied approximately 884 MB. It
was deleted locally and was never imported into production.

## Release gates

- Validation-sample queues fail closed for governed replay.
- Operational admitted counts equal selected counts.
- No case without a governed candidate tier enters operational certification.
- Excluded counts reconcile by retailer and reason.
- Generated profile and queue validate against their JSON Schemas.
- Matching, Product Pack abstraction, contracts, and API tests pass.
- The corrected operational queue is imported only after CI and Railway deployment succeed.
- The prior Egg report is archived only after the replacement governed replay validates.

## Production AI review recovery — 2026-08-18

- Operational queue `fresh_shell_eggs-matching-v2-operational-certification` version `2.0.0`
  was imported with 226 cases and checksum
  `de53067c6fbf3e08d8b0550921b8a7330851985df121d8017b691acec152d261`.
- The first batch stopped at the OpenAI project's enforced spend limit without recorded model
  usage. After the platform owner raised the limit, all 226 cases were retried through linked,
  history-preserving tasks.
- 223 cases completed successfully for an estimated total of $6.041795.
- Three cases failed because retailer image hosts returned HTTP 403 when OpenAI attempted to fetch
  optional vision evidence.
- The matching-review provider now retries that specific failure once without images, constrains
  the response schema to structured evidence, and persists
  `vision_image_download_unavailable` in usage warnings. Other bad requests continue to fail
  closed.
- All 226 cases completed successfully after recovery. The platform owner certified 94 final
  decisions: 90 comparable relationships and 4 governed not-comparable decisions. The remaining
  132 insufficient-evidence cases remain explicitly uncertified and cannot enter price reporting.

## Governed replay identity

Every Matching v2 reporting replay is bound to an immutable gold-set release. The analysis-run
identity therefore includes `matching_v2_gold_set_release_id` in addition to the collection,
Product Pack, legacy match revision, and brand revision. This preserves legacy idempotency while
allowing a distinct, auditable analysis run for each certified Matching v2 release. A separate
source-result/release constraint makes retrying the same release idempotent.
