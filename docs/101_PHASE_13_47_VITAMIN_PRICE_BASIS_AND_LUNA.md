# Phase 13.47 — Vitamin Compatibility, Price Basis, and Luna Review

## Decision

Product compatibility and price-comparison basis are separate governed decisions.

1. The matching engine first determines whether two products are valid retail substitutes using the Product Pack's identity and hard-blocker attributes.
2. Price never establishes or rescues that relationship.
3. After compatibility is supported, package price is eligible only when the governed package counts are known and equivalent.
4. Normalized-unit price is eligible only when both governed package-count denominators are known and positive. Counts may differ.
5. A compatible relationship may support package price, normalized-unit price, or both. If neither basis is supported, it is not ready for price-comparison certification.

For Vitamins & Supplements this means active ingredient or governed formula, labeled strength and unit when applicable, dosage form, release profile, and life-stage/audience must agree before count-normalized pricing is considered. Brand remains descriptive and cannot rescue a specification conflict.

## AI boundary

New Matching v2 reviews use `gpt-5.6-luna`. Prompt `matching_v2_evidence_review@1.1.0` requires the advisory model to make the two decisions in order and return `comparison_basis_proposal` with `package_price`, `normalized_unit_price`, or both for a comparable proposal.

The server remains authoritative:

- it rejects a comparable AI draft with no price basis;
- it rejects a proposed price basis not present in deterministic edge evidence;
- it rejects price bases on non-comparable or insufficient-evidence drafts;
- it binds the basis, case checksum, AI task/output checksum, queue version, and policy version into the human bulk-confirmation checksum; and
- it never lets an AI draft automatically certify a relationship or update reporting.

The AI does not calculate price, unit price, gaps, coverage, or reporting metrics. Search remains authoritative for shelf price and location. PDP and verified image evidence may provide package-count denominators.

## Product Pack contract

Product Pack `vitamins_supplements@1.3.0` adds `price_basis_known_requirements` as a generic capability. Unlike equality requirements, a known-value requirement permits different positive denominators while requiring both values to be usable. The vitamin policy is:

- `exact_package` requires matching `package_count` evidence;
- `normalized_unit` requires known positive `package_count` evidence on both products.

No category branch was added to the core engine.

## Cost governance

The pinned Luna rates are `$0.20` per million input tokens and `$1.20` per million output tokens. Existing immutable Terra tasks retain their original model and usage records. New or explicitly retried tasks use the current configured Luna model only after deployment. Per-request maximum-cost validation, durable queues, retry lineage, and recorded usage remain in force.

## Auto-certification boundary

Higher throughput comes from deterministic eligibility plus checksum-bound administrator bulk certification. Raw model confidence is not an auto-certification authority. Truly automatic certification remains disabled until a category-specific certified gold set proves the existing release threshold without unlabeled auto-approvals or hard-blocker conflicts.
