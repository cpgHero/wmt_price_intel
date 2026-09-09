# Phase 13.84 — Retained-evidence distribution replay and golden rebuild

Status: implementation and focused local verification complete; Eggs and Vitamins production publication retry pending.

## Decision authority

Observed product distribution is defined at exact retailer-product grain:

- Count each distinct, nonblank physical store ID once when the exact retailer product appears in that store-level Search result with a numeric Search-listed price greater than zero.
- Do not gate the count on stock metadata or sponsorship, do not describe it as current inventory, and do not extrapolate to stores where the product was not observed.
- Keep service-area Search separate as `service_area_presence_count`; a service-area result never contributes a physical store.
- Apply retailer seller governance before analytics. Known third-party marketplace offers are excluded; a permitted blank seller remains seller-unverified.
- Treat nonpositive optional regular or discounted price values as missing. The package price remains unchanged and must itself be positive to support distribution or price analysis.

## Immutable retained-evidence replay

No provider, collection, PDP, MetricsCart, OpenAI, or other paid call was made. Each replay created a new immutable generation from evidence already retained by the platform.

| Category | Source lineage | Replay run | Generation | Governed outcome at this checkpoint |
| --- | --- | --- | --- | --- |
| Bananas | `fresh_bananas-3db3e46c-8a89-4519-9936-5e0c48161a5d-match-v2-7d95499f` | `faddb1fa-8284-4fe5-87d0-108a4278c62e` | 2 | 11 of 11 final decisions; `…7d95499f-r2` active |
| Fresh Fluid Milk | `fresh_fluid_milk-19a350ee-90d7-4ec5-92f9-467a15c116b4-match-v2-43c67b88` | `2469f94e-f842-4fbb-a13c-e98acc6a46a6` | 2 | 1,064 of 1,064 final decisions; `…43c67b88-r2` active |
| Ground Beef | `fresh_ground_beef-b01158a0-6ac5-4d8d-9d57-6978cfd61d17-match-v2-29c475d3` | `4bbaeb46-41e7-457e-987f-11cc0faed128` | 2 | 51 comparable and 2 final insufficient-evidence exclusions; `…29c475d3-r2` active |
| Strawberries | `fresh_strawberries-81e1dd0d-450d-49bb-a28c-b32de48ea51c-match-v2-f8ecc77a` | `782c7f2d-3872-4afb-8b2c-06d8e70ac4de` | 2 | 6 of 6 final decisions; `…f8ecc77a-r2` active |
| Fresh Shell Eggs | `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-93bf1a76` | `ba9c4fd7-1186-4774-9025-2cd43004eee5` | 2 | 184 labels: 183 comparable and 1 not comparable, plus 1 final insufficient-evidence exclusion (185 total); result created, publication quarantined pending the narrow readiness correction |
| Vitamins & Supplements | `vitamins_supplements-aee8a9d6-33e5-4bac-903c-2570d869db52-match-v2-71792d31` | `9fe60b40-28bf-48b3-ba5d-fa65fd1e2370` | 4 | 868 labels: 480 comparable and 388 not comparable, plus 1,448 final insufficient-evidence exclusions (2,316 total); result created, publication quarantined pending the narrow readiness correction |

The readiness correction does not manufacture a zero scorecard. A configured retailer may be disclosed as `no_governed_relationships` only when checksum-governed certification is exhaustive, selection is complete, every retailer count reconciles, pending review is zero, certified comparable relationships are zero, and every emitted retailer scorecard carries that explicit evidence state. The same complete and reconciled proof may disclose `no_admissible_observations` when certified comparable relationships exist but no positive-price observations satisfy the selected geography and comparison basis; price outcomes remain unavailable rather than zero. An unaccounted retailer, incomplete certification, mixed evidence state, or zero-valued price outcome remains a publication blocker. Eggs and Vitamins remain quarantined until the correction is deployed, each job is explicitly retried, and activation is verified.

## Production evidence checks

- Milk product `46942839` is observed in 83 distinct positive-price Walmart store Search results, all in California, at $5.28. The evidence covers 59 cities and 78 ZIP codes. Another 4,600 searched Walmart locations did not return that product. The former 4,510-location presentation was wrong and is not retained in the corrected report.
- The Banana Walmart catalog has 12 products: 11 explicitly report seller `Walmart.com`; product `51259339` has no observed seller value and remains seller-unverified. No catalog product is attributed to a third-party marketplace seller.
- Competitive Intelligence and Price Intelligence currently expose the four successfully activated corrected categories above. Eggs and Vitamins must not be described as complete until their quarantined jobs pass the corrected trust gate and activate atomically.

## Egg golden rebuild

Authoritative source: `CCF_Search_Data_08.03.2026_v2.csv`

- Source SHA-256: `094aefb5dde3d8fdc50a4499a751b65df29229e47ee498b12da9f9d2f6fd9194`
- Source size: 192,378,972 bytes; 386,889 rows
- Normalized product catalog: 693 unique products
- Latest retained rows: 240,989
- Amazon: 18,274 retained rows, 18,129 positive-price rows, 1,379 service areas, and zero physical stores
- Positive-price Amazon rows with `stock=false`: 97 retained before comparison reduction and 94 after reduction
- Trader Joe's product `072270`: 648 distinct positive-price stores
- Current deterministic matcher: 0 strict relationships and 262 compatible relationships

The former 5,155 strict-match golden was not reproducible from the authoritative raw source under the current classifier and is replaced rather than preserved as an unexplained historical artifact. These golden metrics validate the deterministic local pipeline; they are not substitutes for the separately governed production Matching v2 release.

## Verification

- `53 passed` across the complete Price Monitoring and report-blueprint test files after the two corrections.
- Ruff format and lint pass for all four changed implementation/test files.
- Full Banana and Strawberry golden checks independently pass.
- The regenerated Egg CSV and JSON artifacts parse and reconcile across formats; the full Egg runtime test still requires CI because File Provider stalled the original workspace during module import. No local Egg pytest success is claimed.

Production acceptance is complete only when CI passes, the deployed worker and API are healthy, the quarantined Eggs and Vitamins jobs are explicitly retried, and both resulting reports are visible through the public report surfaces.
