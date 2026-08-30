# Phase 13.77 — Three-category live Search recollection

## Owner decision

The platform owner approved a combined **$200 Search-only ceiling** for full national Banana,
Milk, and Egg recollection. The approval does not authorize Product Details or OpenAI spend.
Search remains authoritative for retailer-location price, positive-price observation, and
sponsorship. Product Details remains a separate cache-first workflow with a 30-day refresh policy.

## Immutable scope and budgets

All three runs use API Search contracts, one page per governed location, current frozen location
resolutions, retailer-isolated availability gates, durable tasks, immutable raw objects, and hard
credit ceilings.

| Category | Run ID | Estimated credits | Hard ceiling |
|---|---|---:|---:|
| Fresh Bananas | `f2e876dc-afb2-458c-9cbe-2cf02472b923` | 18,437 | 20,000 |
| Fresh Fluid Milk | `d0409065-cc9c-4326-a01d-42c335eef42d` | 18,437 | 20,000 |
| Fresh Shell Eggs | `10f96d03-0064-411a-a2d9-41eec6eec8f9` | 40,789 | 45,000 |
| Fresh Bananas — Walmart recovery | `b4dae462-a06a-4ea1-95ca-fc1260dff922` | 4,683 | 5,000 |
| Fresh Bananas — resilient Walmart recovery | `b11c9efa-c118-49b0-b6b6-a5045ba06940` | 4,683 | 4,683 |
| Fresh Shell Eggs — ALDI operational recovery | `3410a9ca-94b5-4221-8caf-4ed23949eb01` | 5,374 | 5,374 |
| Fresh Shell Eggs — Meijer operational recovery | `d2cb28fe-e32f-4390-9cbd-8e092e6fb273` | 556 | 556 |

The three primary runs estimate 77,663 credits ($155.326). One Walmart-only Banana recovery was
authorized after four successful preflight responses and one nonbillable provider HTTP 500 caused
the immutable primary run's Walmart gate to fail. The recovery reuses the frozen geography and has
a 5,000-credit ($10) hard ceiling; it does not rewrite or retry the failed primary task. The resilient
successor adds an exact 4,683-credit ceiling. At its launch, the conservative estimate across the
batch was 87,029 credits ($174.058), while actual credits plus open work plus the successor projected
62,638 credits ($125.276). The sum of per-run hard ceilings is 94,683 credits ($189.366), still below
the approved $200 Search ceiling.

## Throughput correction

MetricsCart Search quotas are independent by retailer and request type. Production therefore uses
the owner-confirmed ceiling of three Search starts per second and 180 per minute for each retailer.
The Postgres limiter scopes permits to the credential, Search request type, and retailer; all worker
replicas share that state and shared 429 cooldowns.

The collection worker now keeps a bounded rolling window of leased tasks. When one request
finishes, its slot is refilled immediately while slower requests remain leased and heartbeating.
Previously the worker waited for the slowest member of every claimed batch, so a single 60-second
timeout could idle otherwise-free retailer capacity. Rolling refill does not change task identity,
budgets, retailer gates, retry ceilings, cancellation, immutable raw evidence, or `FOR UPDATE SKIP
LOCKED` ownership. Graceful shutdown completes already-leased requests without claiming more.

Eligible claims are ranked by collection-run/retailer lane before row locking. Each claim window
takes one eligible task from every lane before taking a second from any lane. This prevents an
older category or a high-volume retailer from monopolizing rolling slots while preserving global
preflight priority and `SKIP LOCKED` safety across replicas.

The final claim update also rechecks pending/expired-lease eligibility after row locking. This
prevents a concurrently selected candidate from being reassigned after another replica has already
renewed its lease. The candidate set is explicitly materialized before the update. This is the
billable-call safety boundary for horizontal collection workers.

Production collection uses five worker replicas. Replica IDs are unique and the database-backed
limiter prevents horizontal scaling from multiplying a retailer quota.

Each replica also caps active work per retailer while retaining a larger total rolling window and
HTTP connection pool. Slow ALDI requests therefore cannot occupy every slot needed by Walmart,
Amazon, or another Egg retailer. The cap governs concurrency, not request starts; the shared
Postgres limiter remains the authoritative three-per-second and 180-per-minute boundary.

When a retailer returns HTTP 429, the shared state pauses only that retailer and records the event.
For 30 minutes after the last 429, that retailer is paced at one start per second and 54 starts per
minute initially, then ramps continuously back toward three starts per second and 180 per minute;
retailers without a recent 429 remain at the full ceiling. Repeated 429s reset only that retailer's
adaptive recovery window. This follows the fastest rate the live endpoint actually accepts instead of repeatedly
re-entering cooldown at an optimistic catalog ceiling.

## Availability-gate resilience and recovery rotation

The historical gate remains immutable and the default behavior remains strict. A new definition may
explicitly require a successful-sample quorum and allow a bounded number of retry-exhausted,
zero-credit transient samples. Only `provider_5xx`, `timeout`, `network`, and `rate_limit` are
tolerable. Authentication, invalid-request, schema, parse, storage, billable, and unknown failures
remain hard blockers; the billable-404 ceiling remains independent. All selected samples must
terminate before the retailer can pass.

An immutable recovery may exclude exact location-scope keys from preflight designation. The planner
rotates in the next deterministic fingerprints and fails planning if too few samples remain. The
excluded location is still collected in the full frozen geography; this control cannot hide a store,
rewrite a failed task, or suppress its final evidence.

The Banana Walmart replacement policy is five samples, a quorum of four successful samples, and at
most one tolerated transient nonbillable failure. It rotates ZIP `60430` / store `5404` out of the
preflight sample because that exact scope exhausted five zero-credit provider-500 attempts. The four
previous HTTP-200 controls remain samples and ZIP `32224` / store `1172` is the deterministic
replacement. Migration `0049_collection_gate_resilience`, the compatible API, and all five workers
were deployed before run `b11c9efa-c118-49b0-b6b6-a5045ba06940` launched. Its intended five-sample
gate included replacement ZIP `32224` / store `1172`, passed, and released all bulk tasks. The known
bad ZIP `60430` / store `5404` remained a non-preflight task in the full collection.

The terminal bulk-run rule uses the same narrow boundary. If useful work succeeded, a
retry-exhausted non-preflight failure may produce `completed_with_warnings` only when it is
zero-credit and in the explicit transient whitelist. Hard and billable non-404 failures remain
fatal; billable 404s retain their separate threshold and warning behavior. This preserves nearly
complete useful evidence without relabeling an authentication, contract, storage, or paid failure
as harmless.

## Execution and reconciliation gates

1. Each retailer must pass its own five-call availability gate before its bulk tasks are released.
   Legacy definitions require every sample to avoid a terminal non-404 failure. An explicitly
   configured resilient definition must satisfy its successful-sample quorum, transient-failure
   ceiling, independent 404 ceiling, and zero-hard-failure rule.
2. A failed retailer is isolated; healthy retailers continue concurrently.
3. HTTP 200 and 404 responses are billable. Billable 404s are not retried blindly.
4. Actual credits are reconciled from durable task evidence against each run ceiling and the
   combined owner ceiling.
5. Terminal failures are classified by retailer, request input, HTTP status, and billability before
   any recovery call is considered.
6. Search completion does not publish a report. Normalization, admission/noise controls, selective
   cache-first PDP planning, matching/certification, semantic publication gates, and successor
   acceptance remain separate governed stages.
7. Predecessor reports are archived only after a successful replacement is validated. Source data,
   raw objects, PDP evidence, certification history, and audit lineage are never deleted.

## Immutable composite evidence and failure-only recovery

Migration `0051_composite_evidence` and the compatible API implement the reconciliation boundary
without changing any terminal collection run. This implementation is test-verified locally and is
**not production-deployed or operationally applied yet**.

The owner-approved three-category authorization is one aggregate batch of **100,000 Search
credits**, which equals **$200.00 at the server-controlled $0.002 per credit**. The exact immutable
inventory is the seven complete run IDs in the table above. Their terminal actual usage is
**67,908 credits / $135.816** (13,290 + 18,278 + 26,369 + 4 + 4,607 + 5,354 + 6), leaving at most
32,092 credits / $64.184 under the owner ceiling.

The web API cannot create or redefine this authorization. An identified operator first runs
`scripts/authorize_collection_spend.py` with all seven IDs, a 100,000-credit ceiling, the fixed
$0.002000 rate, USD, the owner-approved reason and actor, and the explicit confirmation flag. This
creates one immutable `collection_spend_authorization`. The authenticated batch API accepts only
that authorization UUID and derives the organization, phase, inventory/checksum, ceiling, rate,
currency, reason, and actor. One unique batch consumes it. A missing run, another organization,
duplicate assignment, inventory mismatch, request-controlled price/cap, or actual spend above the
ceiling fails closed. All pre-existing runs must be terminal before new credits can be reserved.

An exact recovery preview contains only failed or cancelled canonical provider requests that still
block assembly. Successful pages and billable HTTP 404 pages are immutable evidence and are never
selected for another paid call. The preview exposes both the selected task count and the maximum
provider attempts. Its maximum credit reservation is the hard upper bound
`sum(credits_per_success * max_attempts)`, not a one-attempt estimate. Exact recovery currently
rejects a selected page that could spawn an unapproved pagination descendant. Approval binds the
base snapshot, selection, actor, reason, aggregate batch, and credit ceiling by checksum; active
plans for one base may not overlap canonical requests. Launch creates only those approved tasks,
without an availability gate, and is idempotent.

The existing full-retailer Banana and Egg ALDI operational recoveries predate exact selection. They
may be attached only through explicit `legacy_operational_adoption`; the base and adopted recovery
runs must both already belong to the same immutable spend-authorized batch. Legacy adoption
reserves no new credit because terminal actuals are already accounted. Every extra recovery request
must already exist in the base run. A usable base success always wins; a recovery success can fill
a base gap; all duplicate or weaker task IDs remain visible as redundant evidence. For legacy tasks
whose provider contract was not frozen, the platform reconstructs identity from the current
catalog and requires each successful or retained-404 raw artifact to corroborate request method,
path, and parameter-name set. Parameter values and historical catalog defaults cannot be proven
retroactively and are disclosed as unverified; this evidence is never described as exact
historical request-contract proof.

Composite assembly writes a new immutable input generation with component checksums, one lineage
row per canonical provider request, selected artifact IDs, superseded and redundant task IDs,
actual component credits, request-identity provenance, and a manifest checksum. It never mutates or
deletes a source run, task, 404, raw object, or prior input set. Deterministic precedence retains a
usable base success; otherwise a conclusive recovery success or retained 404 may replace a weaker
gap. A timeout cannot loosen schema drift or quarantine.

Raw collection readiness is deliberately narrower than report readiness. Every configured retailer
must have planned evidence, at least the inherited minimum successful pages, at least one non-empty
successful page, at least 95% conclusive success/404 coverage, no contract/quarantine failure, and
an inherited acceptable 404 rate. A bounded isolated zero-credit gap can remain a warning only when
useful evidence exists; an all-404, all-empty, absent, schema-drift, quarantined, or substantially
unrecovered retailer blocks analysis. Passing this gate proves raw Search coverage only. Product
admission, first-party/noise controls, matching, and publication remain separate. The publication
semantic gate blocks any configured competitor with no admitted governed comparable price evidence;
zero is never published as a valid scorecard. A checksum-bound unavailable approval excludes one
evidence-deficient competitor from every scorecard and assortment calculation while retaining its
ID, evidence status, approval, and reason in source/readiness metadata. It cannot waive contract
drift or quarantine, and publication blocks if any unavailable retailer emits a scorecard.

The frozen Egg run contains 2,667 Kroger tasks: 1,369 canonical eight-digit store scopes and 1,298
seven-digit aliases made ineligible by location audit `6901fd05-6390-4052-a331-88f5c16ef773`.
Phase 13.77 does not mutate or silently re-denominate that history. Paid preview/approval fails
closed when a selected task now points to an ineligible location, so no 2,667-task Kroger recovery
can launch. Kroger must be explicitly unavailable/no-scorecard in this composite. Follow-on Phase
0052 must introduce an audit/checksum-bound scope projection that preserves every excluded task and
before/after count, then establishes the 1,369-row denominator before Kroger can be recovered or
scored. Failed Meijer recovery is also explicit unavailable/no-scorecard in this release; its
partial evidence remains immutable and visible in readiness metadata.

A ready composite queues exactly one downstream `analysis_run`; a blocked composite queues none.
The analysis source records the base run, every recovery component, and manifest checksum. Replay
generation suffixes apply to every generation after the first, preventing analysis-ID collisions.
The composite also asserts that every selected usable artifact was inserted and that terminal exact
recovery actual credits did not exceed their reserved upper bound.

Recovery control routes require the production administrator token, and approval actors come from
the authenticated server request rather than request-body claims. A never-launched approval may be
superseded atomically without double reservation. Once an exact recovery has launched, it cannot be
superseded or silently paid again. If it terminates without adequate evidence, the composite stays
blocked or receives an explicit reasoned unavailable approval; no zero scorecard is emitted. Any
future unresolved-only retry needs a versioned continuation workflow and remaining-cap approval.

## Verification

- Full Python suite: 859 passed and 24 skipped. The focused composite, collection, API, worker,
  analytics, and publication suite passed 93 tests; PostgreSQL-only integration and concurrency
  tests skipped
  locally because `RCI_TEST_DATABASE_URL` was unavailable.
- Rolling-refill regression proves a third task begins while the first slow request is still active.
- Ruff, mypy across 156 application/package source files, web TypeScript type checking, one unit
  suite plus 85 web tests/build, 91 normative JSON-document validations, and offline Alembic upgrade
  SQL through `0051_composite_evidence` passed.
- Commit `c6af7b6139738dc65e2ea2328a3d039c863f0406` passed GitHub Actions run `33326968373`,
  including 17 Playwright tests, real-Postgres upgrade/downgrade/upgrade, and all four containers.
- Railway deployed API `9e60276c-8b65-4785-b418-5038c23b468d`, worker
  `4284e6a8-6f88-4139-8faa-cdb005f5b79b`, web `5a27fa39-3cf9-483d-95af-4a12534145f3`,
  and scheduler `ffecd07a-25cf-49c3-95f8-bc53a038c9da`. Migration `0049_gate_resilience` is current,
  health/readiness passed, and logs prove five of five unique worker replicas run the new deployment.
- Resilient recovery run `b11c9efa-c118-49b0-b6b6-a5045ba06940` launched with exactly 4,683
  approved credits. Its five-sample gate passed and released the Walmart bulk collection.
- All seven authorized runs are terminal at the exact 67,908-credit / $135.816 total recorded above.
  Composite production registration, checksum-bound unavailable approvals, materialization, semantic
  publication validation, and successor-report archival remain intentionally pending deployment of
  `0051_composite_evidence`; no new provider call is authorized by this implementation work.
