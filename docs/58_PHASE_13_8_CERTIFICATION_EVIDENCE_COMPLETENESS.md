# Phase 13.8 — Certification Evidence Completeness and Seller Eligibility

## Outcome

Every active Match Certification queue now presents observed store/location counts from the same
positive-price Search observations used to construct Matching v2 evidence. The fix is generic across
Product Packs and retailers. It replaces the earlier banana-only compatibility patch without
rewriting imported queue documents, human decisions, or AI drafts.

Known third-party marketplace offers are ineligible at every certification boundary. They cannot be
imported into a new queue, displayed from a legacy queue, submitted to AI review, or certified by an
individual or bulk action.

## Source authority

- Search is authoritative for product presence and local price.
- A product is observed at a location only when its normalized Search price is non-null and greater
  than zero.
- The count is the number of distinct normalized store/location keys where that listing was
  observed—not Search row count, result position count, or PDP availability.
- PDP and Retailer Pack evidence govern seller eligibility and identity. PDP never changes an
  observed-location count.

## Legacy queue reconciliation

Modern Matching v2 queue generation persists `observed_location_count` directly in each listing
summary. Several release queues were imported before that field existed. Re-importing or replacing
those immutable queues would have discarded active AI drafts and certification history.

The API therefore applies a versioned, repository-controlled read-view reconciliation catalog:

`config/matching-v2-review-footprints.json`

Catalog version 2 stores one entry per queue ID/version and one governed record per retailer listing.
Each record contains the Search-derived observed-location count and the seller-governance outcome
used by the corresponding evidence replay. Case-level entries remain supported only for backward
compatibility. Existing values in an imported queue always win; the catalog fills missing values and
never overwrites immutable evidence.

The five current release queues were replayed locally from their supplied Search/PDP artifacts with
the production Product and Retailer Packs:

| Product Pack | Queue cases | Reconciled listing records | Known third-party cases |
|---|---:|---:|---:|
| Fresh bananas | 94 | 29 | 0 |
| Fresh strawberries | 72 | 17 | 0 |
| Fresh ground beef | 210 | 74 | 0 |
| Fresh fluid milk | 311 | 374 | 0 |
| Fresh shell eggs | 1,217 | 632 | 0 |

The egg footprint reconciliation normalized and de-duplicated all 386,889 consolidated Search rows
to the same 343,193 canonical offers used by the release evidence replay. Every one of the 632
listings represented in the active 1,217-case queue resolved to at least one positive-price
store/location observation. No paid MetricsCart or OpenAI call was required for this reconciliation.

## Seller eligibility contract

Marketplace Retailer Packs own explicit first-party seller allowlists. A known PDP seller outside the
allowlist resolves to `excluded_third_party` and is removed before candidate generation. Missing
seller evidence remains `seller_unverified` only where the Retailer Pack expressly permits it; it is
not represented as verified first-party. This preserves the platform owner's prior exception for
blank seller fields while excluding every known non-retailer marketplace seller.

Certification adds defense in depth:

1. Queue import rejects any case whose benchmark or competitor listing has an ineligible or known
   third-party seller-governance outcome.
2. Queue read views suppress any such case found in a legacy document or reconciliation catalog.
3. AI review rejects those cases before creating paid work.
4. Individual and guarded bulk certification reject those cases before writing a decision.
5. Gold-set export consumes the filtered queue view, so excluded offers cannot become release labels.

Retailers without a marketplace policy remain `not_governed`; this describes the absence of a
marketplace seller decision and is not a claim that missing evidence has been verified.

## Verification requirements

- API unit tests cover listing-level reconciliation, non-overwrite behavior, seller-governance
  completion, and import rejection for known third-party offers.
- Matching analytics tests continue to prove that known marketplace sellers outside the Retailer
  Pack allowlist contribute no in-scope observations or review candidates.
- The complete repository test suite and web build must pass.
- Production verification must confirm observed-location labels on strawberries and at least one
  additional formerly incomplete queue, plus the first-party bulk guardrail and queue counts.

## Production verification

Railway production was verified after deployment without writing a match decision:

- Strawberry cards display source-reconciled Walmart, ALDI, and Amazon Same Day footprints; the
  leading one-pound Walmart listing shows 3,652 observed stores/locations and its ALDI comparison
  shows 2,594.
- The 1,217-case egg queue displays footprints across all 13 competitor retailers; the leading
  Marketside listing shows 4,468 observed Walmart stores/locations.
- The egg evidence drawer identifies the Walmart PDP seller as `Walmart.com` with `Verified First
  Party` eligibility. A non-marketplace Safeway comparison remains honestly labeled `Not Governed`.
- The active queue sizes remain 94 bananas, 72 strawberries, 210 ground beef, 311 milk, and 1,217
  eggs. Existing final decisions and completed AI drafts were preserved.
