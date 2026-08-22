# Phase 13.35 — ALDI Search Control Diagnostic

## Outcome

The owner-approved two-location ALDI Strawberry Search diagnostic completed in production on
2026-08-22. The previously successful Ohio control returned HTTP 200, while the California pair
from the failed five-region sample returned the provider's billable HTTP 404 unavailable-page
response. The diagnostic used exactly four Search credits (approximately `$0.008` at the
owner-supplied `$0.002` per credit), with no retry or HTTP 429.

This result rules out an ALDI-wide endpoint outage, a general trailing-slash defect, and a missing
required parameter in the application adapter at the time of the test. It supports a narrower
conclusion: current ALDI Search availability is store/region dependent, or the affected regional
store mappings are no longer accepted by MetricsCart. The failed five-region run must not be
retried unchanged.

## Approved scope

- Collection: `ALDI Strawberry Search Control Diagnostic`
- Run ID: `0eb24781-e930-4532-9ce3-28be75eaf31d`
- Definition version ID: `e2d790f5-5f6d-477e-bf05-927e037f48d2`
- Geography snapshot ID: `0cb7a74f-46ba-45ea-bcc7-f7d552fa2eb1`
- Geography checksum: `dffe849196a6fba064017dd61fc83725125e195242b0b706f81ed81305586987`
- Scope-estimate ID: `788be966-70f6-442a-a82d-cc267c7dd24b`
- Configuration checksum: `34b6e9e34569641fb4e744d403b399633f49ac6f7ca316b06b71528b8d79e0d6`
- Product Pack: Fresh Strawberries `1.0.1`
- Search term: `strawberries`
- Endpoint: `GET /mc/new_aldi/serp/zipcode`
- Request parameters: `keyword`, `zipcode`, `store`, and `page`
- Pages: one per location
- Approved and actual cap: four credits
- PDP enrichment: disabled
- Delivery: audit package only; no email, Excel, or requested web-report export

The collection builder currently requires a competitor even for a retailer-isolation diagnostic.
To preserve the approved four-credit boundary, the same production geography, estimate, and launch
APIs were used directly. The geography request named Amazon Same Day only to satisfy the current
one-competitor geography contract, then explicitly excluded both generated Amazon ZIP scopes. The
frozen resolution therefore contains exactly two ALDI primary locations and zero competitor
locations, and the immutable definition contains only the ALDI adapter. No Walmart or Amazon task
was planned or called.

## Provider results

| Role | Store | ZIP | State | HTTP | Task result | Credits |
|---|---|---|---|---:|---|---:|
| Known-success control | `463-048` | `44906` | OH | 200 | 15-result successful page | 2 |
| Five-region failure sample | `479-098` | `93215` | CA | 404 | Nonretryable invalid request | 2 |
| **Total** |  |  |  |  | **1 of 2 successful** | **4** |

The production monitor reports `completed_with_warnings`, one successful page, one failed page,
four of four credits, zero retries, and a passed ALDI availability gate at the configured maximum
404 rate of `0.50`. The failed task is store `479-098`, ZIP `93215`, page `1`, HTTP 404, first of at
most five worker attempts; the failure is nonretryable, so no additional provider attempt occurred.

Both immutable gzip objects were read back from the Railway bucket. Their object SHA-256 values
match the database artifact checksums, and their decompressed SHA-256 values match the recorded body
checksums. The HTTP 200 object contains the expected top-level `query` and `results` keys, 15 result
objects, result path `results`, Search contract version `1.0.0`, positive-price availability
authority, `is_sponsored` sponsorship authority, and the shared 31-field result inventory. The
HTTP 404 body is exactly:

```json
{"error":"Page not found","message":"Requested URL or Store is not available on the website"}
```

The diagnostic intentionally has no competitor task. The generic analysis worker consequently
failed its three bounded attempts at the AnalysisResult contract because `competitors`,
`comparison_modes`, and `comparisons` were empty. It created no AnalysisResult or user-facing report.
That expected downstream failure does not alter the provider diagnostic verdict, and its queue
history is retained rather than hidden.

## Contract comparison with the owner-supplied CURL

The successful control uses the exact application catalog contract corresponding to the supplied
CURL:

- provider path `new_aldi`;
- path `/mc/new_aldi/serp/zipcode` with no trailing slash;
- keyword `strawberries`;
- ZIP `44906`;
- store `463-048` kept as a string;
- page `1`;
- no `sort` or `fulfillment_type` parameter.

Because that request returned HTTP 200 through the production worker, changing the shared ALDI
adapter path or adding unrelated parameters would be unsupported and could regress the working
control.

## Decision

- Keep the ALDI Search adapter and response contract unchanged.
- Do not classify the five-region failures as schema drift; the control proves the response surface
  can return a valid 200 under the current contract.
- Do not retry the failed California pair without new evidence; another 404 is billable.
- Refresh or validate ALDI's current store/ZIP coverage, preferably using an owner/provider-supplied
  current ALDI location source or a MetricsCart availability response.
- Select replacement regional ALDI stores only from current validated coverage, then run a bounded
  ALDI-only regional preflight before reintroducing Walmart and Amazon Same Day.
- After ALDI regional coverage passes, recreate the five-region comparison as one coherent
  collection period under a fresh estimate and approval.

The collection, task, raw response, credit, geography, definition, and estimate lineage remains
immutable. This diagnostic does not replace or alter the five-category certified reporting
baseline.
