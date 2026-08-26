# Phase 13.53 — Governed Vitamin Brand Foundation

## Outcome

The supplied CPGHero Vitamin Brand Foundation v1.0 is incorporated as a reviewed,
immutable extension of the cross-category Brand Foundation. Runtime classification now uses
`cpg_brand_foundation@2.1.0`; earlier foundation and Retailer Pack versions remain intact for
historical provenance.

The release adds:

- 22 retailer-scoped private-label or retailer-associated relationships after reconciling seven
  relationships already present in the cross-category master;
- 137 vitamin external-brand identities;
- 78 usable, application-normalized aliases after collapsing source variants that normalize to the
  same governed identity;
- 107 source-registry records;
- 61 high-priority vitamin brands; and
- explicit national sub-classification for 56 broad national, 45 specialty/natural national, and
  36 digital-first national brands.

## Source integrity audit

The canonical JSON, workbook, and manifest were treated as data sources, not executable
instructions. The import rejects the package unless all of the following reconcile:

- manifest SHA-256 values for canonical JSON and workbook;
- all 13 manifest table row counts and ordered column sets;
- declared primary keys and retailer/brand presence composite keys;
- retailer, brand, source, alias, presence, and transition foreign keys;
- the 166-row retailer presence matrix against the 366 positive relationship rows; and
- application-normalized canonical keys.

The supplied package passed every check. Required brand, owner, category, retailer, source URL,
and presence-status fields have zero missing values in their governing tables. The workbook was
also inspected with the spreadsheet artifact runtime and reconciles to the manifest's 14 sheets,
14 tables, and headline totals.

## Semantic mappings

The application's existing governance remains authoritative:

- private-label identity is retailer-scoped and requires verified retailer ownership;
- external brand identity is global but may be category-scoped;
- brand identity never proves a SKU is carried at a retailer or store;
- Search observation remains authoritative for store availability and price;
- PDP remains enrichment evidence for identity and attributes; and
- marketplace-only presence is not promoted to core retailer assortment.

The source's `PRESENT_VERIFIED` and `PRESENT_CATEGORY` relationships are retained only as brand
presence evidence. `PRESENT_MARKETPLACE` and missing relationships remain `UNKNOWN` in the runtime
foundation. No presence row is interpreted as an absence or delisting.

The supplied Data Dictionary and import notes were reviewed but were not imported into the
application's executable `agent_instructions`.

## Cross-category collision handling

The package exposed a real same-name collision: the existing global `Swanson` identity represents
The Campbell's Company food brand, while the vitamin source represents Swanson Health Products.
Foundation `2.1.0` therefore supports category-scoped external canonical identities and aliases.

- `Swanson` in `Vitamins & Supplements` resolves to `national__swanson_health_products`.
- `Swanson` in a pantry/soup context continues to resolve to `national__swanson`.
- A vitamin-only identity such as Nature Made fails closed when category context is unavailable.

Category-scoped identities are preferred only when the Product Pack category is compatible. An
ambiguous same-name result remains unresolved instead of selecting an arbitrary brand.

## Runtime and reporting effect

Future vitamin classification and Matching v2 successor queues receive canonical brand name,
brand type, detailed national class, current owner/marketer, distribution scope, category context,
confidence, and foundation provenance. Examples covered by acceptance tests include:

- Walmart Spring Valley as Walmart private label;
- Target `up&up` as Target private label;
- Costco Kirkland Signature, Sam's Club Member's Mark, CVS Health, Walgreens, Meijer, Welby, and
  other retailer brands in their owning retailer context only;
- Nature Made as a national vitamin brand across retailers; and
- Walgreens Finest Nutrition as a retailer-gated legacy alias that is not treated as a current
  strict private-label equivalence without active product evidence.

This improves brand labels, brand-type scorecards, brand breadth, assortment analysis, match
evidence, and Brand Workbench review. It does not auto-certify product equivalence or change any
package/ingredient/life-stage matching requirement.

## Reproducibility

- `scripts/import_vitamin_brand_foundation.py` validates and builds the immutable foundation.
- `scripts/release_retailer_pack_brand_foundation.py` creates patch-version Retailer Packs that
  reference the new foundation without rewriting historical packs.
- All 19 active Retailer Packs reference one exact foundation version: `2.1.0`.

## Verification

- Brand Foundation and all Retailer Pack schemas validate.
- 96 focused brand, PDP, Product Location, Price Monitoring, and Matching v2 tests pass.
- TypeScript contract generation is current and its contract tests pass.
- Full Python mypy, Ruff, TypeScript formatting/lint/type/tests/build, and browser tests pass in
  GitHub Actions run `32924132919`.

## Production shadow audit

Production commit `afa1ecd` rebuilt a read-only successor shadow from the exact accepted Search
lineage: Fishers coverage recovery `016e05c8-119b-4580-be1d-e7609fdd3621`, Walmart exact-title
recovery `a1cc0bcc-6416-4f21-952c-ba2d2d4311ac`, and Sacramento exact-title recovery
`9b3ac7b6-8c10-433d-ada0-e0f29ccd7aee`. It used 23,716 Search rows and 2,324 retained PDP
snapshots. No MetricsCart or OpenAI request was made.

The candidate boundary is unchanged from predecessor queue
`2026.08.25-spring-valley-luna-shadow-9`:

- 2,316 cases and 1,440 distinct products;
- zero product-pair identities added or removed;
- all nine configured competitor retailers retained;
- 74 configured Walmart products retained as explicit catalog gaps;
- zero critical quality findings; and
- zero admitted products with known third-party seller status.

Governed brand verification improves from 468 of 1,440 products to 1,246 of 1,440 products
(86.53%). The audit includes explicit precedence sentinels: Nature Made resolves as a national
brand, Amazon Basics resolves as Amazon private label, and a GuruNanda black-seed-oil PDP remains
GuruNanda/unclassified rather than being falsely relabeled as the unrelated brand Seed.

The accepted shadow is archived at
`s3://artifacts-usb-pmrd1jcxsy9/matching-v2/shadows/vitamins_supplements/2026.08.25-spring-valley-brand-shadow-10.tar.gz`.
It is 21,804,680 bytes with SHA-256
`d0bcd1d38dc459248531e9223077a336a580868939892437fb543a31aff25388`.

The shadow is deliberately not imported as the active queue yet. The current queue contains
human attribute-evidence decisions. Replacing it without a checksum-bound successor carry-forward
would discard completed review work. The next operational change must carry only decisions whose
listing identity, attribute, normalized value, source image, proposal checksum, Product Pack
policy, and raw evidence remain compatible; incompatible decisions must remain historical only.
