# Phase 13.40 — ALDI Identifier and Keyword Diagnostic

Status: completed and production-verified on 2026-08-22 (America/Chicago)

## Objective

Determine whether the ALDI Milk collection failures were caused by the Search endpoint shape, the `milk` keyword, the current `Store_No`, or the alternate MetricsCart location ID. The platform owner approved five ALDI Search attempts, no retries, and a maximum of 10 billable credits (approximately $0.02). Walmart, Amazon, PDP, and AI work were excluded.

## Controlled matrix

All requests used `GET /mc/new_aldi/serp/zipcode` with the catalogued `keyword`, `zipcode`, `store`, `page=1`, and API-key parameters. The production adapter, shared ALDI Search rate-limit partition, durable Postgres queue, immutable raw-object store, and credit ledger remained authoritative.

| Keyword | ZIP | Store parameter | Purpose | HTTP | Results | Credits |
|---|---:|---|---|---:|---:|---:|
| beef | 44432 | 36873 | MetricsCart playground control | 200 | 60 | 2 |
| milk | 44432 | 36873 | Keyword isolation at the same control | 200 | 15 | 2 |
| milk | 44906 | 463-048 | Milk at the prior successful hyphenated ALDI store | 200 | 16 | 2 |
| beef | 06418 | 473-054 | Keyword isolation at a failed Milk geography | 404 | — | 2 |
| beef | 06418 | 2013023 | Alternate `mc_location_id` at the same geography | 500 | — | 0 |

Exactly five provider attempts ran. Every task had `max_attempts=1`; there were no retries or rate-limit responses. The actual ledger was eight credits, approximately $0.016, below the approved 10-credit ceiling.

## Immutable evidence

- Beef identifier run: `200268b3-79a3-4ce3-87be-cca720bc7676`
- Milk keyword run: `a1e1a3e2-a2fd-479b-aa8f-312d118d5dc0`
- Beef control recovery run: `4470a5c2-08b0-4607-8fef-d12b86136284`
- Beef control raw checksum: `85cb640110de70aff97ae8cb76781c7c1f900d0dfba0b0761dcb4eca3f91368b`
- Milk control raw checksum: `15a84e87a0c6890ab81915238f6b7edba6de3b36b27aea9bc44840f865f59a0b`
- Milk hyphenated-store raw checksum: `17f6703547a4ef10d3909b8b5f360a3636960a1fd1b5cb5ee4b5fcb4a6ff8043`
- Failed `Store_No` raw checksum: `5bc15d47c0b0e5185b6cfb7b181d8840b1cd727811a2dcd1266176401ef12511`
- Failed `mc_location_id` raw checksum: `38e4dc6d03a7ecda2dd3218924ee48fb66f2bb4ac0e7620a25e75977594125b2`

Checksum-verified decompression found the expected provider messages: the 404 reports that the requested URL or store is unavailable on the website; the 500 reports that MetricsCart failed to process the request. These are provider responses, not app-generated errors.

The initial Beef run intentionally failed its retailer gate when the alternate identifier returned a terminal non-404 response. That gate cancelled the still-pending control without calling MetricsCart. The control was then completed in a separate one-page, two-credit immutable recovery run rather than rewriting the failed run.

The playground control pair `44432 / 36873` is not present in the newly imported ALDI master. Its tasks therefore used an explicitly labelled diagnostic location override while preserving a canonical ALDI record only as lineage; the outbound ZIP and store parameters were exactly `44432` and `36873`. It must not be treated as an approved collection-master location.

## Findings

1. The production endpoint and request construction are valid. The same adapter returned three HTTP 200 responses without a trailing slash change or parameter change.
2. `milk` is valid. It returned HTTP 200 at both the playground control and the prior successful hyphenated ALDI store.
3. `Store_No` remains the correct outbound ALDI store parameter. Replacing it with `mc_location_id` produced a non-billable HTTP 500 and must not be adopted.
4. The `06418 / 473-054` failure is location-specific, not keyword-specific: both Milk and Beef fail there while control locations succeed.
5. The updated ALDI roster is an identity/geography source, not proof that every listed store is currently callable through MetricsCart Search.

## Production decision

- Keep `/mc/new_aldi/serp/zipcode` unchanged.
- Keep `Store_No` plus normalized ZIP as the ALDI Search request identity.
- Do not switch Search to `mc_location_id`.
- Continue the full Milk run for healthy retailers; retain ALDI as retailer-isolated and stopped where its preflight fails.
- Give MetricsCart the exact failing ALDI store/ZIP list from the Milk and subsequent Egg runs, including the contrasting successful controls.
- Before the next broad ALDI run, use a bounded regional callability gate or a provider-supported callable-location roster. Do not infer nationwide callability from the location master alone.

No product normalization, PDP enrichment, AI generation, match certification, or user-facing report was created from these diagnostic-only runs.
