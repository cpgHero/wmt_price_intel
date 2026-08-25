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

The pinned Luna rates are `$0.20` per million input tokens and `$1.20` per million output tokens. Existing immutable Terra tasks retain their original model and usage records. New or explicitly retried tasks use the current configured Luna model. Per-request maximum-cost validation, durable queues, retry lineage, and recorded usage remain in force.

## Bounded Luna validation

The first production validation uses the immutable Product Pack `1.3.0` shadow queue `2026.08.25-spring-valley-luna-shadow-9`. Its 2,316 pair identities exactly match the accepted predecessor, with zero added or removed pairs, zero observed-location failures, zero price-basis invariant failures, and no known third-party seller leakage. Eighteen cases spanning all nine competitors were selected before any model request, with a disclosed aggregate maximum of `$6.30`.

Batch `efc2b2fa-a9cf-4c03-b49c-184bc75e9481` failed closed before inference because the strict response schema contained the unsupported JSON Schema keyword `uniqueItems`. All 18 historical task records remain immutable, no draft was accepted, no relationship was certified, reporting was unchanged, and recorded model cost was `$0.00`.

The response schema now uses only the OpenAI Structured Outputs subset. Duplicate or unsupported comparison bases remain rejected by application validation after parsing, so schema compatibility does not relax the governed price-basis boundary. Lineage-linked retry batch `8e862ad6-d981-43dd-b893-fa574d33f44d` preserved the failed tasks and completed all 18 cases on Luna for `$0.1312886` with zero technical failures.

The semantic result is a validation checkpoint, not a certification release:

- 10 drafts remained `insufficient_evidence`;
- two proposed `not_comparable` after identifying active-ingredient-form conflicts;
- six proposed `comparable` with normalized-unit pricing only;
- the server blocked one comparable proposal because deterministic evidence did not support its proposed unit-price basis; and
- the remaining five carried deterministic-tier disagreement and low-confidence attribute-evidence warnings, so none were certified during validation.

The model correctly avoided package-price comparison when package counts differed, but it frequently described descriptive brand and package-count differences as generic conflicts. Attribute proposals still require the governed evidence-verification workflow before deterministic recomputation. No AI output changed product compatibility, reporting, or price math.

The immutable validation audit is stored at `s3://artifacts-usb-pmrd1jcxsy9/matching-v2/validations/vitamins_supplements/2026-08-25/luna-bounded-validation/batch_id=8e862ad6-d981-43dd-b893-fa574d33f44d/audit.json` with SHA-256 `091c153c04ca39d3b2e91fb2062f4bd2a63c2712ee7d0c99dc374d3fdc0288d9`.

## Post-validation governance hardening

The bounded run exposed a certification-boundary defect: an AI draft could propose a match tier different from the deterministic engine tier and the bulk preview treated that disagreement as an advisory warning. No validation case was certified, but warning-only treatment was too permissive.

Policy `guarded_ai_recommendation_bulk_certification@1.6.0` now fails closed when the deterministic tier is missing, blocked, or different from the AI proposal. The request-specific Structured Outputs schema exposes only the deterministic engine tier and only deterministic eligible price bases. Application validation repeats both checks after generation. This prevents AI from creating, promoting, or widening product compatibility and prevents an unsupported package or normalized-unit basis from reaching certification, including for historical drafts generated under an earlier schema.

AI-extracted PDP or image attributes remain proposals. They must be verified through the governed evidence-reconciliation workflow and the deterministic edge must be recomputed before a stronger tier or additional comparison basis can become eligible. The AI result itself never upgrades the edge.

## Auto-certification boundary

Higher throughput comes from deterministic eligibility plus checksum-bound administrator bulk certification. Raw model confidence is not an auto-certification authority. Truly automatic certification remains disabled until a category-specific certified gold set proves the existing release threshold without unlabeled auto-approvals or hard-blocker conflicts.

## Production verification

The release is active in Railway production as of 2026-08-25.

- GitHub Actions run `32889170545` passed Python, TypeScript, browser, migration, contract, and all four container gates.
- API deployment `a2c6274f-655c-4aa8-9528-076ca0714e87` succeeded.
- Worker deployment `4ffc7aad-ef19-4c5e-a819-973fac2b56b1` succeeded.
- Direct process inspection confirmed `OPENAI_MODEL_MATCHING_REVIEW=gpt-5.6-luna` in both the API and worker.
- No paid AI review or MetricsCart collection was launched as part of the deployment.
- GitHub Actions run `32891810158` passed the complete release gate for schema compatibility commit `788fedd`.
- Railway API deployment `e18f7c81-700d-40f1-9b1f-dc3d9040460f` and worker deployment `e4c47c59-3924-44bb-aa75-5e49b664ea29` succeeded on that commit.
- Direct worker inspection confirmed the production response schema contains no `uniqueItems` keyword and remains pinned to `gpt-5.6-luna`.
