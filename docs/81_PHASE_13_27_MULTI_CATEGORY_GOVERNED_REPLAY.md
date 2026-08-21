# Phase 13.27 — Multi-Category Governed Replay

## Status

Banana, Strawberry, and Ground Beef implementation, production replay, semantic
release audit, and live-route verification completed on August 20, 2026. Their
obsolete predecessors were already recoverably archived on August 18 and remain
available through audit lineage. Milk remains fail-closed pending current
Product Pack 1.5.0 certification.

## Purpose

Replay Fresh Bananas, Fresh Strawberries, Fresh Ground Beef, and Fresh Fluid
Milk under the current reporting stack without weakening Matching v2 authority
or deleting historical evidence.

## Operational queue audit

The earlier non-Egg queues are deterministic stratified validation samples.
They measure matching quality but cannot drive operational reporting. Current
source evidence was therefore rebuilt as exhaustive operational certification
queues before any replay was requested.

For Bananas, Strawberries, and Ground Beef, every current eligible relationship
already existed in the prior reviewed queue under the same Product Pack version
and policy checksum. A fail-closed migration retained a prior decision only
when all of the following reconciled:

- exact retailer product pair;
- exact Product Pack ID, version, and policy checksum;
- identical structured listing, attribute, proposal, edge, and scope evidence;
- image evidence was additive rather than removed or contradicted;
- observed-location evidence was additive rather than changed; and
- both the prior immutable decision references and current evidence references
  were retained on the new append-only submission.

The resulting operational queues contain 11 of 11 final Banana cases, six of
six final Strawberry cases, and 53 of 53 final Ground Beef cases. Ground Beef
retains two explicit insufficient-evidence exclusions; they are not forced into
price comparisons.

Milk Product Pack 1.5.0 materially differs from the earlier sampled queue and
adds exact package-volume governance. Its exhaustive current scope contains
6,396 candidate product relationships, so prior sampled decisions are not
eligible for carry-forward. Milk remains blocked from governed replay until a
current, scalable certification path is completed.

## Certified profile projection correction

The first Strawberry and Ground Beef replay attempts exposed a worker defect.
Certified product identity was projected into legacy radius profiles even
though the Matching v2 reporting path establishes identity at exact Search
location grain and creates the user-facing 1, 3, and 5 mile views later in the
radius-native competitive portfolio. Strawberry therefore failed on the
legacy exact-ZIP-only confirmed-match implementation. Ground Beef failed
because the worker incorrectly treated a profile's unknown-value policy as a
proxy for whether a human-certified equivalent product may use that profile.

Certified relationships now project into every exact-location Product Pack
profile and never into a legacy radius profile. The immutable certification
tier remains on the relationship; Product Pack exact-location profiles define
the metric and attribute lens; the downstream competitive portfolio remains
the only authority for physical-store 1, 3, and 5 mile scoring. A Product Pack
without an exact-location profile fails closed.

## Production replay results

The current immutable releases produced these active decision-ready reports:

- Fresh Bananas: `fresh_bananas-3db3e46c-8a89-4519-9936-5e0c48161a5d-match-v2-00a5061c`;
- Fresh Strawberries: `fresh_strawberries-81e1dd0d-450d-49bb-a28c-b32de48ea51c-match-v2-4e6bddc0-r2`;
- Fresh Ground Beef: `fresh_ground_beef-b01158a0-6ac5-4d8d-9d57-6978cfd61d17-match-v2-a7fb8453-r2`.

Every report is `ready_to_share`, has complete metric-reference coverage, has
zero unsupported numeric claims, one publication, and three pre-materialized
Price Architecture matrices. Banana materializes five comparison bases at 1,
3, and 5 miles (15 portfolio documents). Strawberry and Ground Beef each
materialize Strict and Unit-price at all three radii (six documents each).

Ground Beef exposed a second scale defect during derivative materialization:
each concurrent benchmark-product projection independently reloaded the same
immutable Product Pack from Postgres. The exact-version catalog loader now
serializes the first load and caches the validated immutable pack for the
service lifetime. This removed the connection stampede without reducing
product scope, changing source evidence, or making a provider call.

## Verification

- `apps/worker/tests/test_analysis.py`: 12 passed;
- `packages/python/rci-analytics/tests/test_matching.py` and
  `test_competitive_leadership.py`: 32 passed;
- Product Pack cache and competitive portfolio suites: 33 passed;
- Banana semantic portfolio audit: 15 documents, zero errors, three explicit
  `no_scored_evidence` warnings;
- Strawberry semantic portfolio audit: six documents, zero errors or warnings;
- Ground Beef semantic portfolio audit: six documents, zero errors or warnings;
- production Competitive Intelligence and Price Intelligence routes returned
  HTTP 200 for all three replacements, and the Ground Beef portfolio API
  returned HTTP 200 with the governed Strict / 3-mile document.

The regression suite covers exact-tier Strawberries and equivalent-tier Ground
Beef, including exclusion of the obsolete radius profile. No MetricsCart or
OpenAI call is required by this correction.

## Archival boundary

An obsolete predecessor may be recoverably archived only after its replacement
AnalysisResult succeeds, all required comparison-basis × radius documents pass
the semantic release audit, and live report behavior is validated. Search
data, raw objects, PDP evidence, review submissions, certification releases,
failed replay attempts, and audit lineage are never deleted.

All exact predecessors for the three completed categories were already marked
with recoverable `archived_at` timestamps before this phase. The accepted
replacements remain the only active reports. Milk's predecessor is also
archived, but no new Milk report is activated until its materially new 6,396
case scope has a scalable, current certification authority.
