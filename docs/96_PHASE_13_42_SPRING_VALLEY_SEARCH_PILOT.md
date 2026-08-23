# Phase 13.42 — Spring Valley multi-retailer Search pilot

## Purpose

Collect one Search page for each of 85 owner-supplied Spring Valley vitamin keywords,
retain only the governed Spring Valley Walmart anchor catalog for later analysis, and
discover competitor candidates before any PDP or AI spend.

The source workbook contains 322 Spring Valley Walmart products and 85 distinct
keywords. Its governed repository representation is
`source_material/spring-valley/spring-valley-anchor-catalog.json`.

## Controls

- Product Pack: `vitamins_supplements@1.0.1` (active).
- Walmart catalog policy: explicit 322-product allowlist; non-Spring Valley Walmart
  Search results remain raw evidence but are analysis noise.
- Search scope: one page per keyword and retailer.
- PDP enrichment: disabled.
- AI: disabled.
- Delivery and report publication: disabled pending Search evidence qualification.
- Search budget approved by the owner: 2,500 credits / $5.00 at $0.002 per credit.

## Geography

The primary market is Columbus, Ohio. Each store retailer uses one frozen store/ZIP
combination; Amazon Same Day uses the Walmart-market ZIP. Kroger uses store `01600965`,
ZIP `43081`, after the owner confirmed that combination in MetricsCart.

The Kroger endpoint must retain its trailing slash:
`/mc/kroger/search/zipcode/`. Without that slash, MetricsCart returned billable 404s
for otherwise valid Kroger requests. This behavior is regression-tested in the
provider adapter suite.

## Production runs

### Nine-retailer primary run

- Run: `e962ced9-9e83-4cf3-b5f2-2cf514009ae3`
- Planned tasks: 765
- Successful tasks: 718
- Terminal failures: 47
- Actual credits: 1,284 ($2.568)

Retailer outcomes:

| Retailer | Successful pages | Failed pages | Result rows | Credits |
|---|---:|---:|---:|---:|
| Amazon Same Day | 84 | 1 | 1,344 | 170 |
| BJ's | 85 | 0 | 1,811 | 85 |
| Costco | 85 | 0 | 1,288 | 85 |
| CVS | 85 | 0 | 1,658 | 170 |
| Meijer | 40 | 45 | 1,062 | 94 |
| Sam's Club | 85 | 0 | 862 | 170 |
| Target | 85 | 0 | 2,370 | 340 |
| Walgreens | 84 | 1 | 5,991 | 85 |
| Walmart | 85 | 0 | 1,630 | 85 |

Meijer produced seven billable 404s and 38 non-billable terminal 500/timeout failures.
Amazon returned one billable HTTP 200 empty-object response that was quarantined as
schema drift rather than silently interpreted. Walgreens returned one billable 404.

### Kroger recovery run

- Run: `3093b480-d633-4f61-af47-ba499a355bb9`
- Successful tasks: 85 of 85
- Failed tasks: 0
- Retries: 0
- Result rows: 2,298
- Actual credits: 255 ($0.510)

## Reconciliation

- Production Search evidence: 803 successful pages, 47 failed pages, 20,314 result
  rows, and 1,539 credits ($3.078).
- Bounded diagnostics, including the Kroger route diagnosis: 43 credits ($0.086).
- Total Spring Valley Search usage: 1,582 credits ($3.164), below the approved $5.00
  ceiling.
- Temporary Railway worker scaling was restored to one replica after collection.

## Required next gate

Before PDP enrichment or match generation:

1. audit preserved payload fields and normalization coverage for all ten retailers;
2. apply the Spring Valley Walmart allowlist and retailer 1P/noise policy;
3. deduplicate competitor candidates across keywords;
4. calculate the admitted unique-product PDP estimate with the 30-day freshness cache;
5. request separate owner approval for PDP and AI spend.

No PDP enrichment, AI review, match certification, analysis publication, or report
publication is authorized by this Search phase.
