# Phase 13.58 — Vitamin Automated Certification and Release-Profile Correction

## Objective

Process the Vitamin matching population with governed automation instead of requiring the owner to
make more than one thousand repetitive decisions. Automation must improve throughput without
turning AI confidence into match authority.

## Production evidence reconciliation

The owner authorized the system to make the best defensible decisions across the complete Vitamin
queue. The guarded consensus policy reconciled 1,415 product-attribute claims across 837 products in
one checksum-bound action. It retained 465 exceptions: conflicting values, lower-confidence source
observations, and proposals that would replace an existing governed value.

The evidence-aware Luna review then reprocessed all 1,938 cases whose prior AI input was stale. The
durable Postgres queue completed all 1,938 tasks successfully. Temporary Railway scaling increased
throughput while preserving leases and idempotency; the worker was returned to one replica after the
batch.

## Governed match decisions

The server bulk-certified only recommendations that also passed deterministic Product Pack gates:

- two comparable relationships had deterministic tier and price-basis agreement with no warning;
- 370 not-comparable relationships had a known deterministic hard-blocker conflict; and
- one warned comparable relationship and every insufficient-evidence result remained unresolved.

The 372 final decisions were inserted in eight atomic, checksum-bound batches. AI supplied an
advisory explanation; Product Pack evidence supplied the authority. No reporting replay or
publication occurred.

## Root-cause finding

The post-run audit showed that ordinary-release products were incorrectly blocked. The Product Pack
assigned an inferred `Standard` release profile but also required explicit, reviewed release-profile
evidence before certification. This prevented otherwise obvious comparisons such as Vitamin E 180
mg softgel versus Vitamin E 180 mg softgel and Vitamin B12 3,000 mcg gummy versus the same
specification.

Product Pack `vitamins_supplements@1.3.1` corrects that semantic defect:

1. `release_profile` remains a hard blocker when two known values conflict;
2. an unlabeled ordinary release profile is not a missing-evidence blocker;
3. special claims such as extended, timed, fast, or quick-dissolve release still conflict with a
   known different profile; and
4. `package_count` is noncritical to product compatibility and remains authoritative only for
   deciding whether package price, normalized-unit price, or neither is a valid comparison basis.

The core engine remains category-generic. The behavior is expressed entirely through versioned
Product Pack roles and price-basis requirements.

## Trust boundary

- Active ingredient/formula, applicable strength and unit, dosage form, and life stage remain
  blocking identity evidence.
- Brand remains descriptive; Spring Valley is expected to compare with other brands.
- Package-count differences never create compatibility. They determine the valid price basis after
  compatibility exists.
- An unknown package count can leave a compatible relationship without a reportable price basis.
- Search remains authoritative for price and observed location. PDP/image evidence supports product
  identity only.
- Existing final decisions and immutable AI/evidence history are retained.

## Verification

Focused Product Pack, Matching v2 API, price-basis, and contract tests cover ordinary unlabeled
release, known release conflicts, audience conflicts, multi-ingredient applicability, differing
package counts, and missing normalized-unit denominators. The full local release gate passed 760
Python tests, 72 web unit tests, formatting, type checking, contract validation, and the production
web build. Railway deployed Product Pack `1.3.1` to API, worker, and web successfully.

## Production certification pass under Product Pack 1.3.1

The corrected policy changed every unresolved case's certification checksum, so the system ran a
fresh evidence-aware Luna review for all 1,920 pending relationships. Two durable batches completed
all 1,920 tasks with zero failures or `needs_review` task states. The run consumed 50,815,005 input
tokens and 2,744,833 output tokens for an estimated $13.4568006, within the owner-approved cap.

The checksum-bound certification preview found:

- 473 comparable recommendations that also passed deterministic identity, seller, observed-
  location, tier, and price-basis gates;
- one of those 473 contained a low-confidence AI attribute warning and remained unresolved;
- 1,165 insufficient-evidence recommendations remained unresolved; and
- 282 AI not-comparable recommendations lacked a deterministic known hard-blocker conflict and
  remained unresolved rather than becoming unsupported rejections.

The system committed the remaining 472 comparable relationships in ten atomic batches under the
explicit platform-owner automation authority. Advisory differences were limited by policy to
nonblocking context such as brand, package count, or unlabeled ordinary release. Known hard-blocker
conflicts could not pass the gate. The resulting operational queue contains 480 approved, 388
rejected, and 1,448 unresolved cases. No approved case is release-blocked or lacks observed Search
evidence. The approved set covers 68 of the 150 distinct observed Spring Valley benchmark products
represented in the candidate queue.

The unresolved population is a system exception set, not an owner-assigned manual backlog. For
example, the remaining apparent deterministic candidates include collagen-plus-vitamin-C versus
plain vitamin C and men's 50+ versus women's 50+. Their AI refusals exposed formula/audience
semantics that the current scalar deterministic attributes do not fully encode. They must remain
deferred until a future multi-ingredient formulation model can prove or reject them without lowering
the certification standard. Reporting was not replayed in this phase.
