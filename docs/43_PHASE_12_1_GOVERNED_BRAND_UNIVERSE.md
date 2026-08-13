# Phase 12.1 — Governed Brand Universe

## Outcome

The application now consumes the supplied CPGHero Brand Foundation v2.0 as a versioned,
immutable Brand Foundation. The foundation expands the original private-label-only seed into a
707-record brand universe without weakening the product or store-level evidence rules.

## Classification model

Brand identity, ownership, distribution, and retailer presence are deliberately separate:

- A private-label relationship is retailer-scoped. It can enter the `private_label` reporting and
  matching role only when the row is approved, active or transitioning, in the configured eligible
  class, selected for private-label matching, and explicitly `retailer_owned`.
- A national or regional external brand exists once globally. Its role is available to any retailer
  observation that resolves to the governed canonical name or an allowed alias.
- Retailer presence is evidence, not identity. `UNKNOWN` is preserved and never interpreted as
  absent.
- A regional distribution description supports confidence and analysis; it does not reject a new
  observation outside the documented region.
- An unknown observed brand remains unclassified and enters the existing discovery/review path. It
  cannot mutate the approved foundation.

This means the primary business distinction is trustworthy: `private_label` means confirmed
retailer-owned. Regional, national, and unresolved brands are not private label.

## Resolution order

1. Resolve the retailer.
2. Resolve an exact retailer-scoped private-label canonical name.
3. Resolve an exact retailer-scoped private-label alias.
4. Resolve an exact global regional/national canonical name.
5. Resolve an exact global alias. Category-gated aliases require compatible Product Pack context.
6. Otherwise fail closed as unclassified and retain the raw brand for review.

Brand evidence may improve match candidate generation, but Product Pack attribute and package
compatibility remain mandatory. The resolver does not make price, product-equivalence, or retailer
presence claims.

## Imported evidence

- 224 private-label and retailer-associated relationships.
- 483 regional/national canonical brands.
- 185 priority dairy/egg brands.
- 105 usable exact aliases.
- 102 first-party/corporate evidence sources.
- 20 operational resolution and matching instructions.
- 483 retailer-presence seeds, all retaining their supplied `UNKNOWN` state.

The two duplicate Whole Foods Market Kitchen aliases pointed to different canonical brands. The
conflicting normalized alias is recorded under `alias_conflicts` and excluded from automatic
resolution pending human review.

## Reproducibility and governance

`scripts/import_brand_foundation_v2.py` checks that the JSON, CSV, and workbook representations
reconcile before producing the immutable foundation. Source SHA-256 checksums are stored with the
published document. Retailer Pack `1.1.0` versions point to Brand Foundation
`cpg_brand_foundation@2.0.0`; the prior Retailer Packs and private-label foundation remain available
for historical provenance.

## Acceptance checks

- Great Value resolves as Walmart-owned private label at Walmart and remains unresolved at ALDI.
- fairlife resolves once as a national brand for retailer observations without asserting retailer
  presence.
- Category-gated aliases resolve only in a compatible Product Pack context.
- Retailer-exclusive but not retailer-owned brands do not enter strict private-label equivalence.
- Price Monitoring uses governed canonical brand name/type while Search remains authoritative for
  product/location price facts.
