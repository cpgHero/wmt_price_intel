# Phase 13.55 — Vitamin Full-Population AI Evidence Review

## Objective

Run the complete brand-enhanced Vitamin Matching v2 candidate population through the governed
advisory review workflow without exceeding the platform owner's approved `$50.00` AI cap or
allowing AI output to become authoritative evidence or a final match.

## Scope and spending gate

The active immutable queue was
`2026.08.25-spring-valley-brand-shadow-10`, containing 2,316 pending candidate relationships and
zero final match decisions. Production was pinned to `gpt-5.6-luna`.

The first eligible selection contained 1,500 cases. Its conservative exposure was `$46.878656`,
calculated using every case's canonical derived certification view, all 12 permitted images, and
the full 6,000-output-token allowance. Batch `094a4540-d829-4d22-ae49-743066e4aadc` completed all
1,500 tasks with zero failures for `$9.8828092` recorded usage.

After reconciling actual spend, the remaining 816 cases had a conservative exposure of
`$25.529446`. Actual first-batch spend plus that maximum was `$35.4122552`, below the owner cap.
Batch `4ef3aaf3-cfd3-4ecc-bc57-9db77a9fd1dc` then completed all 816 tasks with zero failures for
`$6.8944466`.

Total recorded AI spend was `$16.7772558`. No MetricsCart call was made.

## Throughput control

The Railway worker temporarily scaled from one replica to 16 replicas. Each replica retained the
application's bounded concurrency, durable Postgres claim, lease, retry, and idempotency controls.
All 2,316 tasks completed exactly once, and the worker returned to one `us-west2` replica after
the batch. Scaling changed elapsed time only; it did not expand the case population or AI budget.

## Recommendation audit

All latest task records have status `succeeded`:

- 6 comparable recommendations: five `equivalent_product` and one `exact_specification`;
- 549 not-comparable recommendations;
- 1,761 insufficient-evidence recommendations;
- 6 recommendations support normalized-unit price, and one also supports package price;
- no comparable recommendation contains an incompatible governed attribute; and
- 25 relationships currently pass the deterministic guarded bulk-certification boundary.

The remaining not-comparable recommendations are not automatically certifiable when the claimed
conflict exists only in unverified image evidence. Insufficient-evidence output remains non-final.

## Attribute-evidence audit

The two batches produced 12,853 image-cited proposals:

- 8,899 corroborate existing evidence and require no administrator action;
- 3,431 fill an unknown value;
- 247 refine a lower-authority current value;
- 275 conflict with a lower-authority current value; and
- one is invalid and remains in audit history.

The 3,953 eligible case-level proposals collapse to 1,880 distinct listing-and-attribute claims.
Repeated proposals converge on one normalized value for 1,753 claims; 1,712 of those consensus
claims have a minimum confidence of at least 95%. The other 127 distinct claims contain conflicting
values and require individual evidence review. Repetition across candidate pairs is not treated as
independent evidence and does not authorize automatic verification.

## Authority boundary and next gate

AI output is advisory. This phase created no attribute-evidence decision, final product-match
decision, gold-set release, analysis replay, or report. The next safe workflow is product-level
claim reconciliation: show one representative claim with every supporting and conflicting image
citation, let an identified administrator verify or reject it once, propagate that immutable
decision by listing identity, recompute the deterministic engine, and only then reassess guarded
bulk match certification.
