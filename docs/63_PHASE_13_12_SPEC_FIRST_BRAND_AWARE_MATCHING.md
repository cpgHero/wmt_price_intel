# Phase 13.12 — Spec-First, Brand-Aware Milk and Egg Matching

Status: implemented; deployment validation pending

## Decision

Fresh Fluid Milk and Fresh Shell Eggs are matched on governed package and product specifications.
Brand is important evidence and an analytical dimension, but a different, regional, private-label,
national, missing, or unresolved brand cannot independently make a pair not comparable or
insufficient.

The inverse is also enforced: brand agreement does not rescue products whose Product Pack
hard-blocker specifications conflict.

## Product Pack behavior

- Fresh Fluid Milk `1.4.0` makes `all_brand`—labeled **Specification-equivalent
  (brand-aware)**—the preferred scorecard profile. Its dimensions remain volume, fat type, flavor,
  organic, lactose-free, ultrafiltered, A2, grass-fed, omega-3/DHA, kids, and protein-fortified.
- Milk's same-brand and private-label profiles remain available as secondary lenses. They answer
  brand-specific questions; they are not the primary eligibility gate.
- Fresh Shell Eggs already uses `ignore_brand` in both strict and compatible profiles. Count, size,
  shell color, grade, organic status, and housing method remain the governed specifications.
- Matching v2 marks brand `descriptive`, noncritical, and weight zero for both Product Packs. The
  computed `brand_relationship` still distinguishes verified same-brand, private-label,
  regional-brand, national-brand, and unknown relationships for review and reporting.

No category branch was added to the matching engine. The generic profile selector now honors each
Product Pack's configured preferred scorecard profile.

## AI-review behavior

Governed prompt `matching_v2_evidence_review` version `1.0.3` makes Product Pack attribute roles
mandatory. Descriptive, identity, and ignored fields may characterize or segment a relationship,
but cannot alone support `not_comparable` or `insufficient_evidence`. The instruction explicitly
protects different and unknown brands when brand is non-decisive and preserves the rule that brand
agreement cannot override a hard-blocker conflict.

The model remains advisory. A human decision is still required, all source and prompt checksums are
retained, and reanalysis does not run automatically.

## Verification gates

- Product Pack contract and semantic validation;
- Milk primary-profile selection and immutable catalog version checks;
- actual Milk and Egg Product Pack policies proving different brands remain exact-specification
  candidates when every governed specification agrees;
- the same policies proving an equal brand cannot override a hard specification conflict;
- prompt-version and instruction regression coverage;
- full Milk and Egg golden regression, full Python/web suites, reversible migrations, build,
  deployment, and read-only production verification.
