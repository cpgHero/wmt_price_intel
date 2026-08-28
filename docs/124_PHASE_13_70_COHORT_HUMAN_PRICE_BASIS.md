# Phase 13.70 — Cohort Human Price Basis

Date: 2026-08-28  
Status: Deployed and production-verified

## Decision

A fixed-package cohort must lead with the price basis a merchant or shopper
actually buys. A 64-fluid-ounce cohort therefore leads with its 64-fluid-ounce
package-equivalent median, not a gallon-normalized equivalent. Price per fluid
ounce remains visible as normalized secondary context.

When a fluid cohort contains different package volumes, price per fluid ounce
is the primary display because one package price would not be comparable across
the cohort. A per-gallon value remains canonical calculation and audit lineage
when the Product Pack governs that metric, but it is not the primary human
presentation for a non-gallon package.

## Deterministic display rules

1. `price_per_gallon` or another recognized fluid-ounce-normalized metric plus
   one governed `volume_oz` produces a primary package-equivalent value and a
   secondary per-fluid-ounce value.
2. The same normalized metric without a fixed `volume_oz` produces a primary
   per-fluid-ounce value.
3. Other comparison metrics retain their existing value and unit.
4. The same scale factor is applied to both retailer medians and the paired
   median difference. Directional outcomes, lower-price shares, counts,
   denominators, and cohort membership are unchanged.
5. CSV/Excel exports include the human display basis and values while retaining
   canonical metric, unit, medians, and package-equivalent compatibility fields.

## Reconciled Milk example

For the certified ALDI `64 fl oz · whole · organic · non-lactose-free` cohort:

- Walmart: `$11.92/gallon` canonical = `$5.96 per 64 fl oz package` =
  `$0.093125 per fl oz`.
- ALDI: `$7.70/gallon` canonical = `$3.85 per 64 fl oz package` =
  `$0.06015625 per fl oz`.
- Paired median difference: `-$4.14/gallon` canonical = `-$2.07 per 64 fl oz
  package` = `-$0.03234375 per fl oz`.

The paired median difference is computed across paired product-location
differences and therefore is not required to equal the subtraction of the two
marginal medians.

## Performance and trust boundary

The presentation helper runs over cohort values already present in browser
memory. It adds no API request, database query, durable materialization, worker
job, or schema migration. It does not change Search-authoritative prices,
certified relationships, Product Pack eligibility, radius rules, selected local
competitor evidence, normalized calculations, or stored report artifacts.

## Verification

- Fixed 64-fluid-ounce values and the paired gap have exact regression tests.
- Mixed-volume fluid cohorts have a per-fluid-ounce primary-basis regression.
- Non-volume metrics have a no-change regression.
- Web type checking and linting pass with the pinned Node and pnpm toolchain.
- All 81 web tests, lint, type checking, formatting, and the Next.js production
  build passed locally with the pinned toolchain.
- GitHub Actions run `33182901876` passed Python, contracts, reversible
  migrations, TypeScript, all 15 browser tests, the production build, and all
  four container builds.
- Railway web deployment `057b530e-74b5-44a3-b4f1-4ff422ee0e94` succeeded.
- The live ALDI / brand-neutral / five-mile Milk view contains exactly one
  target cohort row. It displays `$5.96` and `$3.85 per 64 fl oz package`,
  `$0.0931` and `$0.0602 per fl oz`, and an ALDI-lower paired median difference
  of `$2.07 per 64 fl oz package`. It does not display the gallon-normalized
  values as the primary price.
- The live included-products drawer opened in 376 milliseconds, showed all
  eight governed relationships, stated the package, per-fluid-ounce, and
  canonical audit bases, and produced no browser warning or error.
- Web readiness returned HTTP 200 with the API dependency ready in 0.229
  seconds. The report route returned HTTP 200 with a 0.160-second response
  start. No report rebuilding or materialization was triggered for acceptance.
