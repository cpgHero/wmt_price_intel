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

## Evidence-only queue succession — 2026-08-18

PDP evidence remediation creates a new immutable review-queue version; it never edits the
original case documents. A successor import may carry finalized `comparable` and
`not_comparable` submissions only when all of the following fail-closed checks pass inside the
same database transaction:

- the predecessor belongs to the same organization and external queue;
- the Product Pack ID/version and certification-policy checksum are unchanged;
- every certified predecessor case exists in the successor;
- every prior primary image remains present in the successor image set;
- each certified case is identical after removing only `image_url` and `image_urls` fields.

Each carried submission preserves the reviewer, verdict, allowed tiers, rationale, and evidence
references, adds an explicit reference to the predecessor submission, and records that submission
in `supersedes_submission_id`. Any changed governed attribute, pair identity, proposal, source
reference, or missing certified case aborts the complete import. The remaining successor cases stay
pending for bounded AI or human remediation. Queue import itself never starts a paid AI call.

Production queue `2.1.0` (checksum
`b3f2ff97503d1796d4550603c09b3008def2785f04448fffce379d65b7f357a1`) passed the
additive-evidence comparison for all 226 cases. The transactional import carried 90 comparable
and four not-comparable submissions from `2.0.0`, each with an immutable supersession link, and
left exactly 132 pending cases. Batch `4f5e9fbe-ea43-46d6-a8aa-493dd86c258f` then reviewed all
132 pending cases with `gpt-5.6-terra`: 132 succeeded, zero entered needs-attention, and recorded
cost was $8.2524. All 132 proposals remained `insufficient_evidence`; no human decision changed.
Eighty-four cited unresolved organic evidence, one cited unresolved housing evidence, and 34
cited shell-color differences; categories overlap. Two image-derived attributes were cited, and
one case used the recorded structured-only fallback because its retailer image host was
unavailable. This outcome is evidence about the current hard-blocker policy and source coverage,
not permission to relax either automatically.

## Egg policy calibration — 2026-08-18

Product Pack `fresh_shell_eggs` version `1.2.2` corrects the certification semantics exposed by
the evidence-remediation replay:

- a known shell-color difference is a hard conflict and the pair is not comparable;
- unknown organic evidence does not independently block a decision;
- a known organic-versus-non-organic conflict remains a hard conflict;
- other hard-blocker attributes continue to treat missing or unknown evidence as blocking unless
  their Product Pack policy explicitly opts out.

The implementation is generic. Matching-v2 attribute roles may declare
`unknown_is_blocking: false`; no Egg-specific branch was added to the engine or certification
service. The active policy decorates each case with its exact unknown-tolerant attributes and the
AI prompt must obey that case-bound list. Deterministic known conflicts remain authoritative.

This Product Pack revision changes the certification-policy checksum. Existing queue `2.1.0`, its
94 carried decisions, and all prior AI tasks remain immutable audit history and cannot be silently
carried into a new policy queue. Production adoption therefore requires a newly versioned,
exhaustive operational queue, explicit certification, a checksum-bound gold-set release, and a
governed reporting replay. Building or importing that queue starts no paid AI or PDP calls.

Production Product Pack and report blueprint `1.2.2` passed CI run `32166745063` and deployed
after the immutable catalog correctly rejected an initial attempt to change blueprint `1.2.1` in
place. Exhaustive operational queue `3.0.0` (checksum
`ebf7d453b0d0b99b0e1220e009ec0b01f93cd9f405413aef2c29d82c7afc298e`) contains 185 pending
cases. Relative to queue `2.1.0`, 41 candidates were removed by known shell-color conflicts: 25
white-versus-brown, 12 brown-versus-white, and four brown-versus-specialty/mixed. The retained
queue contains zero shell-color conflicts and 97 organic-unknown cases. Active-policy verification
finds exactly one blocked case because housing remains unresolved. No prior certification crossed
the policy revision, no AI task started, and temporary staging objects were deleted after import.

The platform owner completed queue `3.0.0` with 183 comparable decisions, one not-comparable
decision, and one explicitly flagged case. The flagged Walmart `654756038` versus Kroger
`0001111087023` relationship remains excluded because Walmart housing evidence is unknown while
the Kroger item is known cage-free. No approved relationship has an active certification blocker.

## Governed replay identity

Every Matching v2 reporting replay is bound to an immutable gold-set release. The analysis-run
identity therefore includes `matching_v2_gold_set_release_id` in addition to the collection,
Product Pack, legacy match revision, and brand revision. This preserves legacy idempotency while
allowing a distinct, auditable analysis run for each certified Matching v2 release. A separate
source-result/release constraint makes retrying the same release idempotent.

The AnalysisResult source contract carries the complete release-coverage envelope: source and
selected candidate counts, selection completeness/rate, certified and unresolved totals, and
per-retailer reconciliation. These are governed provenance fields, not optional UI calculations.

## Governed Egg reporting release — 2026-08-18

- Gold-set release `8374b3c8-379c-4b19-b400-773f36a9a1e4` contains the platform owner's 94
  certified decisions: 90 comparable and 4 not comparable.
- Analysis `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-8374b3c8`
  completed from that immutable release with no legacy or automatic match fallback.
- Sixty certified relationships produced admissible store/ZIP price evidence. Thirty certified
  comparable relationships produced no admissible co-observed price evidence under the configured
  geography and comparison profiles and are disclosed, not silently counted.
- The remaining 132 unresolved candidates are excluded. The report is therefore published as
  `Review Required`, while each retailer/profile scorecard can independently be ready when its
  evidence threshold is satisfied.
- Live UI validation reconciled retailer, comparison-basis, included-product, observation, ZIP,
  and reported-relationship counts. Decision Readiness is scoped to the selected retailer and
  comparison basis.
- The obsolete pre-governance Egg Matching v2 result
  `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-0dd6df6d` was archived only
  after the governed replacement passed CI, deployed, and completed the browser validation.

### Product Pack 1.2.2 certified replay

- Gold-set release `de5fc82e-27e9-40c4-a284-ffea2989f261`, checksum
  `970b02be6e171c5649b3c9c6e66be138fdcbf01d2fce7b80f6f62fc21e9fbc35`, contains 184
  certified labels: 183 comparable and one not comparable. Exactly one of 185 exhaustive queue
  cases remains flagged and excluded; automatic fallback is disabled.
- Analysis `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-de5fc82e`
  completed on its first attempt and published with Product Pack/report blueprint `1.2.2`.
- Live provenance reconciles the immutable release ID and checksum, all 185 selected/source
  candidates, 100% selection coverage, 183 comparable labels, one not-comparable label, one
  unresolved exclusion, and every retailer-level certification count.
- Browser validation confirmed that the comparison-basis control changes the scorecard evidence.
  Compatible-spec reporting now produces price observations for 11 retailers, including 1,961
  ALDI observations across 1,327 ZIP markets and nine Meijer observations across nine ZIP markets.
  Sam's Club and Trader Joe's have certified product relationships but zero admissible co-observed
  store/ZIP price comparisons in the historical Search data; the UI reports zero evidence instead
  of manufacturing a price result. Strict exact-spec remains a separate, intentionally narrower
  basis.
- The report remains `Review Required` because one certification case is deliberately unresolved;
  retailer/profile scorecards independently report Ready or Limited Evidence from their own
  deterministic observation and geography thresholds.
- After the release passed provenance and scorecard validation, six older active publications were
  recoverably archived. The Competitive Intelligence library now exposes only this certified Egg
  release candidate. Source Search/PDP data, generated artifacts, analysis runs, match decisions,
  immutable releases, and audit history were retained. Browser verification reports one of one
  active publications and confirms that the direct `?lens=compatible` view shows the broad
  retailer comparison basis rather than the intentionally narrower strict exact-spec default.

## PDP and vision evidence remediation

The normalized PDP contract already retains descriptions, identifiers, specification, physical
properties, variant configuration, seller, brand, category, primary/all images, media metadata,
fulfillment, reviews, demand, relationships, source-field inventory, and unmapped-field inventory.
Search remains authoritative for store price, presence, sponsorship, and time.

Matching evidence now carries the deduplicated PDP image set rather than only one representative
hero image. Vision remains conditional: it is invoked only when critical structured attributes are
missing or conflicting. A request interleaves Walmart and competitor images and is bounded to six
images per product (twelve per pair). Any image-derived attribute must cite visible text and the
exact supplied URL. If a retailer host blocks image download, the governed structured-only fallback
is recorded; the model cannot claim image evidence.

The normalization audit reports field-level availability for seller, brand, description,
identifiers, specifications, physical properties, primary imagery, and multiple imagery. This
separates two different questions: whether every provider field was mapped, and whether the source
actually supplied enough decision-useful evidence for a product. Regenerating a candidate graph or
starting paid AI review remains an explicit administrator action after deployment and audit.
