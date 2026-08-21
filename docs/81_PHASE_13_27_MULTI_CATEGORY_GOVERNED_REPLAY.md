# Phase 13.27 — Multi-Category Governed Replay

## Status

Implementation and focused verification complete on August 20, 2026. Production
deployment, replay recovery, semantic release audits, and predecessor archival
remain pending.

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

## Verification

- `apps/worker/tests/test_analysis.py`: 12 passed;
- `packages/python/rci-analytics/tests/test_matching.py` and
  `test_competitive_leadership.py`: 32 passed.

The regression suite covers exact-tier Strawberries and equivalent-tier Ground
Beef, including exclusion of the obsolete radius profile. No MetricsCart or
OpenAI call is required by this correction.

## Archival boundary

An obsolete predecessor may be recoverably archived only after its replacement
AnalysisResult succeeds, all required comparison-basis × radius documents pass
the semantic release audit, and live report behavior is validated. Search
data, raw objects, PDP evidence, review submissions, certification releases,
failed replay attempts, and audit lineage are never deleted.
