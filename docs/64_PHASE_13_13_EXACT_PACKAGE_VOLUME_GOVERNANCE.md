# Phase 13.13 — Exact Milk Package-Volume Governance

Status: deployed and verified

## Decision

Fresh Fluid Milk package volume is an exact compatibility requirement. A gallon cannot match a
half gallon, a half gallon cannot match a quart, and a quart cannot match a pint. A verified brand,
similar title, normalized unit price, or otherwise compatible milk specification cannot override a
package-volume conflict.

Unknown package volume is not silently treated as compatible. It requires more evidence before a
comparable decision can be certified.

## Product Pack behavior

- Fresh Fluid Milk Product Pack `1.5.0` promotes `volume_oz` from a soft comparator to a
  `hard_blocker` with the existing 0.5-ounce rounding tolerance.
- Report blueprint `fresh_fluid_milk_leadership` `1.4.0` binds Product Pack `1.5.0` for new
  definitions without changing historical report definitions.
- Brand remains descriptive for the primary all-brand Milk profile. Compatible regional, national,
  and private-label products can still match when their governed specifications—including exact
  package volume—agree.
- The category-neutral matching engine remains unchanged; the Product Pack owns this behavior.

## Certification boundary

Review-queue evidence is immutable. Older Milk queues may therefore show the role that was active
when they were generated. Before a new AI review, AI retry, individual decision, bulk decision,
adjudication, or certified gold-set export, the API overlays the current Product Pack roles in a
derived certification view. The historical queue role remains visible as `queue_role`.

For a proposed `comparable` decision, every current Product Pack hard blocker must be known and
compatible. A conflict or unresolved value blocks certification at the server boundary. A governed
`not_comparable` recommendation remains eligible for human confirmation when all other controls
pass, because the conflict is evidence supporting rejection rather than a reason to block it.

Previously finalized comparable decisions are not silently deleted. The queue view identifies any
finalized approval that conflicts with the current policy, prevents it from entering a new certified
gold set, and presents it for explicit flag-and-review handling.

## Administrator experience

Match Certification displays a prominent current-policy warning for affected pairs, shows the
primary and competitor values, labels legacy queue roles when they differ, disables **Approve
match**, and leaves **Reject match** and **Needs evidence** available. Queue rows display a package
or compatibility-blocked badge before the drawer is opened.

## AI-review behavior

Governed prompt `matching_v2_evidence_review` `1.0.4` requires:

- known hard-blocker conflicts to produce `not_comparable`;
- unknown hard blockers to produce `insufficient_evidence`;
- gallon, half-gallon, quart, pint, and other different sizes never to be treated as interchangeable;
- unit-price normalization never to manufacture a semantic product match; and
- brand evidence never to override a hard specification conflict.

AI remains advisory and cannot certify or publish a relationship.

## Verification gates

- Product Pack and report-blueprint schema/semantic validation;
- explicit 128↔64 oz, 64↔32 oz, and 32↔16 oz deterministic rejection tests;
- same-brand evidence proving it cannot rescue a cross-volume pair;
- legacy soft-role overlay regression;
- comparable bulk-certification rejection and not-comparable acceptance regression;
- individual, bulk, retry, adjudication, and gold-set enforcement tests;
- full Python, web, browser, migration, build, deployment, and read-only production audit; and
- Milk golden regression using the available full source fixtures.

## Compatibility and rollback

Historical Product Packs, queues, prompts, decisions, and reports remain immutable. Rolling back
the application restores the prior service behavior but does not delete the new Product Pack,
blueprint, prompt, audit evidence, or decisions. Any unsafe prior approval must be explicitly
flagged and replaced, never rewritten in place.

## Production verification

Verified August 17, 2026.

- GitHub Actions run `31999183989` passed the complete Python, TypeScript, migration,
  contract, browser, build, and four-container release gate. Local verification passed
  `500` Python tests with `13` environment-dependent golden tests skipped by the repository's
  standard gate, `52` normative contract validations, and `57` web unit tests.
- Railway deployed commit `83c6f8f` successfully to web
  (`804ba906-b4a7-40ee-97a0-0ca8bf6143b7`), API
  (`02558013-a9c9-41d9-9364-e1d246583bc8`), worker
  (`ce98b3cd-ada5-47c8-b7d7-65fc81c2ae64`), and scheduler
  (`3c702f78-405c-4d8d-ba02-59d0f372457e`).
- A read-only production audit evaluated all `311` cases in the active Fresh Fluid Milk queue.
  The current Product Pack blocks `215` cases that have at least one unresolved or conflicting
  hard attribute. This includes `128` volume conflicts and `68` cases with unresolved volume.
- Seven previously approved comparable cases are now fail-closed under the current rule: two
  confirmed cross-volume relationships (`32` oz vs `64` oz and `32` oz vs `128` oz) and five
  relationships with unresolved volume evidence. They are excluded from new certified gold-set
  output and cannot be newly approved as comparable until the evidence is corrected.
- No paid MetricsCart or AI calls were made for this policy correction or verification.
