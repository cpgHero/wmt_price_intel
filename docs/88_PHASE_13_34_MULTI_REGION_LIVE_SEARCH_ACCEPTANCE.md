# Phase 13.34 — Multi-Region Live Search Acceptance

## Outcome

The owner-approved five-region Strawberry collection was launched against the production
MetricsCart Search-by-ZIP boundary on 2026-08-22. The ALDI availability gate failed closed before
Walmart, Amazon Same Day, or the sixth ALDI location could incur provider spend. The run is retained
as immutable evidence, but it is **not** an accepted multi-region collection and it produced no
analysis or report.

This is a successful safety-control test and a failed provider-availability acceptance test. The
result must not be represented as schema drift, an application crash, or proof that the five ALDI
locations are invalid. The evidence supports a narrower conclusion: at collection time, MetricsCart
returned the same billable 404 unavailable-page response for all five sampled ALDI store/ZIP pages.

## Approved scope

- Collection: `Fresh Strawberries Five-Region Live API Acceptance 2026-08-22`
- Run ID: `e9f163bd-024d-4a53-87e6-1141f2975cc9`
- Definition version ID: `f2479094-7183-431d-895b-840e59b98673`
- Geography snapshot ID: `7927f5d3-2818-4392-a7d7-e380a097a067`
- Product Pack: Fresh Strawberries `1.0.1`
- Search term: `strawberries`
- Regions: California, Florida, Illinois, Ohio, and Pennsylvania
- Planned scope: five Walmart pages, six ALDI pages, and five Amazon Same Day ZIP pages
- ALDI gate: deterministic sample of five first pages; maximum billable-404 rate `0.50`
- Approved hard cap: 27 Search credits
- PDP enrichment: disabled

The first estimate expired before the paid action and was correctly rejected without a provider
call. The identical 27-credit estimate was regenerated, re-approved, and then launched.

## Actual provider results and spend

| Retailer | Planned pages | Attempted | HTTP 200 | HTTP 404 | Credits | Outcome |
|---|---:|---:|---:|---:|---:|---|
| ALDI | 6 | 5 | 0 | 5 | 10 | Gate failed at a 100% billable-404 rate |
| Walmart | 5 | 0 | 0 | 0 | 0 | Cancelled before provider request |
| Amazon Same Day | 5 | 0 | 0 | 0 | 0 | Cancelled before provider request |
| **Total** | **16** | **5** | **0** | **5** | **10** | **Run failed closed** |

At the owner-supplied rate of $0.002 per credit, actual provider spend was approximately $0.02.
The gate prevented the remaining 17 estimated credits from being spent. There were no retries,
rate-limit responses, or HTTP 429 events.

## ALDI gate evidence

| Store | ZIP | State | Historical Strawberry rows on 2026-08-07 | Live result |
|---|---|---|---:|---|
| `479-098` | `93215` | CA | 13 | HTTP 404 |
| `474-031` | `33809` | FL | 14 | HTTP 404 |
| `468-051` | `61764` | IL | 15 | HTTP 404 |
| `461-002` | `43015` | OH | 15 | HTTP 404 |
| `469-066` | `17009` | PA | 15 | HTTP 404 |

The unattempted sixth ALDI page was store `474-235`, ZIP `33803`; it had 13 historical Strawberry
rows on 2026-08-07. All six store/ZIP pairs match both the canonical location master and the retained
ALDI historical source. That corroborates the requested context but does not prove current retailer
or provider availability.

Every attempted request used the catalogued endpoint
`/mc/new_aldi/serp/zipcode` with exactly `keyword`, `zipcode`, `store`, and `page`. This is the same
route and parameter contract that returned HTTP 200 for store `463-048`, ZIP `44906`, in the
Phase 13.33 production pilot. The five retained raw bodies are byte-identical and contain:

```json
{"error":"Page not found","message":"Requested URL or Store is not available on the website"}
```

Each compressed object checksum matches its database artifact record, and each decompressed body
checksum matches the artifact metadata. A billable 404 is immutable failure evidence; it is not a
successful empty page and it does not enter normalization.

## Data-quality verdict

- **Request completeness:** passed. Required keyword, ZIP, store, and page values were present.
- **Location reconciliation:** passed against the canonical location master and August 7 retained
  Strawberry results for all sampled pairs.
- **Endpoint regression evidence:** not established. The same ALDI contract passed in production one
  day earlier, so five 404s do not justify changing the adapter without a controlled diagnostic.
- **Schema contract:** not evaluated because no HTTP 200 payload was returned.
- **Walmart and Amazon regional behavior:** not evaluated because the gate intentionally prevented
  their tasks from being claimed.
- **Analysis and reporting:** not produced. No successful page existed to normalize or analyze.
- **Multi-region release decision:** blocked. Do not expand to a full-location collection.

## Required next diagnostic

Do not retry all five failed pages blindly. After a new explicit paid-call approval, run an ALDI-only
two-location diagnostic with one page per location and a four-credit hard cap:

1. the previously successful control store `463-048`, ZIP `44906`; and
2. one of the failed five-region pairs.

If both return 404, treat the ALDI Search surface as unavailable and escalate the preserved request
and response evidence to MetricsCart before spending further credits. If the control succeeds and
the failed-region pair does not, refresh or validate regional ALDI location coverage before choosing
replacement stores. If both succeed, classify this run as a transient provider/retailer event and
repeat the original five-region acceptance under a fresh estimate and approval.

Only after ALDI availability is resolved should Walmart and Amazon Same Day be collected in the
same governed multi-region definition. That preserves one coherent comparison period and prevents a
partial regional report from being mistaken for an accepted competitive study.
