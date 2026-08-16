# Phase 13.4 — Human Match Certification

## Outcome

Phase 13.4 converts deterministic Matching v2 shadow evidence into an immutable, independently
reviewable certification workflow. It does **not** make Matching v2 authoritative. Existing v1
matching and published reports remain unchanged until a Product Pack passes every release gate.

## Real-data evidence audit

The profiler replayed all five supplied August 2026 category datasets through retailer
normalization, Product Pack classification, listing collapse, Matching v2 shadow evaluation, and
deterministic stratified sampling.

| Product Pack | Source rows | Normalized unique rows | Review cases | Normalization failures | Retailer mismatches |
|---|---:|---:|---:|---:|---:|
| Fresh shell eggs | 386,889 | 343,193 | 1,126 | 0 | 0 |
| Fresh fluid milk | 348,980 | 328,554 | 311 | 0 | 0 |
| Fresh ground beef | 225,791 | 218,329 | 220 | 0 | 0 |
| Fresh strawberries | 297,443 | 287,316 | 100 | 0 | 0 |
| Fresh bananas | 168,440 | 163,987 | 99 | 0 | 0 |
| **Total** | **1,427,543** | **1,341,379** | **1,856** | **0** | **0** |

The replay made no provider, PDP, OpenAI, or vision calls.

### Release-blocking evidence finding

Egg Search exports do not contain enough critical attribute evidence for safe automatic matching.
Complete critical-attribute coverage ranges from 0% to 10.9% by retailer; Walmart is 1.1% and ALDI
is 0%. Eggs therefore require targeted PDP/label/vision evidence plus human adjudication before
certification. This is an evidence gap, not permission to infer missing claims from title similarity.

The other category profiles are materially stronger but are not certified merely because their
coverage is high. Ground beef reached 100% critical-attribute completeness in the supplied data;
milk reached 91.9%–94.4%; strawberries reached 88.9%–100%; bananas reached 73.7%–100%.

Because the first full milk profile exposed 5,416 exact-specification proposals that had not been
human validated, `auto_approval_tiers` is empty in every Product Pack. Automatic approval remains
disabled until category-specific precision is proven against released gold labels.

Price-basis eligibility is also Product Pack governed. Exact-package comparisons require the
category's explicit package-defining attribute to match: egg count, milk volume, ground-beef
weight, strawberry weight, or banana selling unit. The lowest local offer remains a separate
selection policy and is never represented as a unit/price basis.

## Durable workflow

1. `rci-matching-v2-profile` streams the complete source files and emits a checksummed evidence
   profile and deterministic review queue.
2. Queue import validates the JSON Schema and canonical document checksum before inserting any
   records.
3. The workbench presents the product pair, governed tier proposal, attributes, provenance,
   reliability, and immutable evidence references.
4. Two distinct reviewer identities independently submit decisions.
5. Adjudication can only cite the current submission from each reviewer. Case-scoped PostgreSQL
   advisory locks prevent a review/adjudication race.
6. An adjudicated case rejects further review submissions. Any future correction must be an
   explicit superseding adjudication, preserving the complete audit chain.
7. Gold-set export includes only adjudicated, evidence-backed labels. `insufficient_evidence`
   decisions remain in the audit trail but do not become positive or negative release labels.

The tables created by migration `0030_matching_v2_human_review` are append-only. Database triggers
reject updates and deletes for queues, cases, submissions, adjudications, and adjudication links.

## Administrative API

The production API is disabled unless `MATCHING_V2_REVIEW_API_ENABLED=true` and requires
`X-RCI-Admin-Token`. The web proxy additionally requires the existing administrator session and
same-origin validation for writes.

- `POST /api/v1/matching-v2/review-queues/import`
- `GET /api/v1/matching-v2/review-queues`
- `GET /api/v1/matching-v2/review-queues/{queue_id}`
- `POST /api/v1/matching-v2/review-queues/{queue_id}/cases/{case_id}/submissions`
- `POST /api/v1/matching-v2/review-queues/{queue_id}/cases/{case_id}/adjudications`
- `GET /api/v1/matching-v2/review-queues/{queue_id}/gold-set`

Queue-scoped case routes are deliberate: the same pair can appear in multiple evidence/policy
versions without a review being written to the wrong release queue.

## Workbench

`/admin/matching-v2` provides:

- protected administrator access;
- queue import and queue/status selection;
- full pagination for large queues;
- side-by-side product identity, imagery, retailer links, brand class, and identifiers;
- inspectable attribute evidence and engine rationale;
- retailer filtering with Walmart fixed as the benchmark side;
- explicitly selected AI-draft batches capped at 25 cases with cost-ceiling disclosure;
- independent decision and tier selection with required rationale;
- reviewer history and two-review consensus finalization;
- truthful whole-queue progress; and
- adjudicated gold-set access.

Reviewer identity is currently a stable, manually entered identity inside a protected administrator
session. Cryptographically verified individual identity must be added with application accounts and
RBAC before external production release; the shared administrator password alone cannot prove two
different humans performed the reviews.

## Remaining certification sequence

1. Deploy migration/API/workbench with the review API disabled by default.
2. Enable the protected review API and import the five validated queue documents.
3. Acquire targeted missing identity evidence, beginning with eggs; do not recollect store-level
   prices for this purpose.
4. Complete two-person review and adjudication by stratum.
5. Run release metrics overall and per stratum: candidate recall, automatic-tier precision, hard
   conflicts, coverage reasons, determinism, and local-comparison reconciliation.
6. Certify and cut over one Product Pack at a time in the order eggs, milk, ground beef,
   strawberries, bananas.
