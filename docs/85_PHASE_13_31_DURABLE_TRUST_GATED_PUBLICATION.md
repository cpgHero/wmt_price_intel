# Phase 13.31 — Durable Trust-Gated Report Publication

## Outcome

New AnalysisResults are no longer treated as active reports immediately after deterministic
analytics finishes. They begin in `pending`, receive one idempotent Postgres materialization job,
and become `ready` only after the complete staged reporting surface passes the semantic trust gate.
The five Phase 13.30 certified reports remain the active acceptance baseline while any replacement
is queued, running, retrying, or blocked.

## Durable execution

Migration `0044_report_pub_gate` adds:

- `analysis_result.reporting_status`: `pending`, `ready`, or `blocked`;
- `report_materialization_job`: durable status, exact stage, progress, attempts, backoff, lease,
  audit result, and terminal error;
- `report_materialization_stage`: checksum-bound, idempotent Price Architecture and Competitive
  Portfolio documents keyed by job, kind, and scope.

Worker replicas claim eligible jobs with `FOR UPDATE SKIP LOCKED`. A heartbeat extends the lease.
Expired leases are reclaimable; temporary failures use bounded exponential backoff; three exhausted
attempts block the replacement. Automatic retries retain completed staged scopes. An explicit admin
retry resets the blocked job and its staging set without recollecting Search or PDP evidence.

## Materialization plan

Every job stages:

1. Walmart-anchored Price Architecture at the default $0.50 boundary behavior;
2. fixed-range Price Architecture at $0.50 increments;
3. fixed-range Price Architecture at $1.00 increments; and
4. one Competitive Portfolio for every configured Product Pack comparison basis at 1, 3, and 5
   miles.

Each competitive scope is a separate resumable work unit. This prevents Milk-sized reports from
depending on one browser request or one all-or-nothing infrastructure timeout.

## Automatic semantic publication gate

The gate fails closed when any required scope is missing or when the Phase 13.30 reconciliation
finds a critical error. It verifies:

- one named analysis and benchmark across every document;
- complete profile-by-radius and retailer scope;
- explicit physical-store radius and Amazon service-area policies;
- benchmark denominator = scored + unscored;
- scored = leader + tied + at-risk + losing;
- every displayed rate agrees with its governed numerator and denominator;
- product and certified-relationship rows add exactly to scorecards;
- scored-evidence-weighted average gaps reconcile;
- relationship, competitor-product, and benchmark-product counts reconcile;
- assortment and price scorecards share the same governed price evidence;
- cohort relationships never exceed the certified relationship ledger;
- stable product/relationship scope across 1/3/5 miles; and
- wider radii never remove scorable evidence or add unscored benchmark locations.

Warnings such as a certified relationship with no locally scorable evidence remain published and
visible. Errors block activation.

## Atomic activation and recovery

After the gate passes, one database transaction:

1. installs all staged Price Architecture documents;
2. installs all staged Competitive Portfolio documents;
3. records the complete audit document;
4. marks the replacement `ready`;
5. recoverably archives older ready AnalysisResults in the same Product Pack lineage; and
6. marks the durable job complete.

The prior trusted report remains active until that transaction commits. A user can never receive a
half-built replacement. No Search rows, raw objects, PDP evidence, human decisions, immutable gold
sets, superseded AnalysisResults, or audit lineage are deleted.

## Administrator experience

`/admin/report-publishing` shows the analysis and Product Pack identity, current stage, completed and
total steps, attempt count, reporting status, last error, audit counts, and timestamps. It polls
while open and provides a guarded retry only for blocked or retry-wait jobs. Access uses the existing
administrator session and server-side admin token; internal stage actions additionally require the
shared private service token and an active worker lease.

## Cost and source authority

This phase makes no MetricsCart or OpenAI request. Materialization reads retained immutable and
normalized evidence. Retrying report publication cannot spend provider or model credits.

## Acceptance gates

- Migration upgrades and downgrades cleanly.
- Existing AnalysisResults backfill as `ready`; new ones default to `pending`.
- Only `ready`, non-archived results appear in active analysis lists.
- Duplicate publication activation creates no duplicate job.
- Two worker replicas cannot claim the same job.
- Lease expiry, heartbeat, retry backoff, attempt exhaustion, and manual retry are tested.
- Missing staged scopes or semantic errors prevent activation.
- Successful finalization is atomic and records recoverably archived predecessor IDs.
- Platform Docs, navigation, API, worker, web tests, browser tests, builds, and service containers
  pass before deployment.

## Release verification

Phase 13.31 is deployed and production-verified at commit `59b2187`. GitHub Actions run
`32545856295` passed:

- Ruff formatting and linting;
- Mypy across 151 Python source files;
- the complete Python test suite and contract validation;
- Alembic upgrade, downgrade-to-base, and re-upgrade against PostgreSQL;
- TypeScript formatting, linting, type checking, unit tests, production build, and browser tests;
- API, worker, scheduler, and web container builds.

Railway deployed the same commit to all application services. The API pre-deploy step installed
`0044_report_pub_gate`, the administrator progress page returned HTTP 200, and the live worker
successfully imported the report-materialization module.

A read-only production reconciliation after deployment found exactly five active AnalysisResults:
Ground Beef, Strawberries, Bananas, Fresh Shell Eggs, and Fresh Fluid Milk. All five remained
`ready`; no active result was `pending` or `blocked`; and the new materialization queue was empty.
The migration therefore preserved the certified Phase 13.30 baseline without creating a replay,
provider call, AI call, or accidental archival.
