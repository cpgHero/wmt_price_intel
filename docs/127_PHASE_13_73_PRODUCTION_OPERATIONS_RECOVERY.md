# Phase 13.73 — Production Operations, Recovery, and Release Governance

Status: deployed and production-verified; recovery attestations remain intentionally unset

Date: August 29, 2026

## Objective

Turn the repository's existing health endpoints, leased queues, provider cooldowns, spend controls,
reversible migrations, and atomic report publication into one administrator-visible operating
workflow. The phase must improve incident response and release evidence without duplicating queue
state, exposing secrets, rewriting immutable evidence, or making an unapproved provider/AI call.

## Implemented scope

### Protected System Operations workspace

`/admin/operations` uses the existing eight-hour protected administrator session and a same-origin
web proxy. Its API endpoint requires the narrow server-to-server administrator token in production.
The read-only workspace exposes:

- Railway commit SHA, deployment ID, environment, service, and application version from an explicit
  non-secret allowlist;
- the live `alembic_version` and repository-derived migration head;
- deployed Product Pack and active Retailer Pack IDs, versions, and checksums;
- Search, analysis, PDP, Matching v2 AI, and report-materialization queue depth, running claims,
  expired leases, and recent failures/review outcomes;
- current provider cooldowns, the last shared 429, and configured rate/attempt boundaries;
- active ready/pending/blocked publications, open validation blockers, and latest successful work;
- 30-day Search/PDP credits, the configured per-credit accounting estimate, recorded AI estimated
  cost, and completed AI tasks whose cost metadata is unknown; and
- explicit backup and restore-drill freshness based on operator-attested ISO-8601 timestamps.

The endpoint never serializes arbitrary environment values, API keys, database/bucket credentials,
or admin/session secrets. Provider billing remains financially authoritative.

Service-specific settings are not inferred across Railway containers. In particular, an API-local
`COLLECTION_PROVIDER` value is displayed only when the API service actually exposes it; otherwise
the page says **Not exposed to API**. The worker remains independently fail-closed against
`COLLECTION_PROVIDER=fake` in production. A durable service heartbeat would be required before this
console could truthfully claim the worker's complete runtime configuration.

### Fail-closed operational state

System Operations reports `blocked` when the database migration does not match the deployed
repository head, any running durable task has an expired lease, or an open validation blocker
exists. Recent failures/review outcomes, active provider cooldowns, and missing/stale recovery
attestations report `attention`. This status assists diagnosis; it does not mutate queues or reports.

### Zero-credit release verifier

`scripts/verify_release_readiness.py` performs bounded JSON checks against web/API liveness and
readiness endpoints and emits a checksummed-style JSON evidence document that explicitly records
zero paid provider calls. It does not call Search, PDP, OpenAI, email, or bucket mutation paths.
A live paid provider/AI canary remains separately approved and budgeted.

### Documentation change gate

`scripts/check_platform_docs_coverage.py` classifies behavioral source, configuration, contract,
migration, Product Pack, Retailer Pack, AI, report, and Railway changes. CI fails when those changes
omit either the maintained `platform-docs.ts` manual or a numbered `docs/` phase/change record.
Test-only and documentation-only changes do not create a recursive documentation requirement.

### Operating manual

Platform Docs version 1.3.73 adds:

- **Production incident response & recovery** — severity definitions, availability workflow,
  evidence-preserving rollback, database/bucket recovery drill, and current automation boundary.
- **Release manifest, canaries & change control** — manifest definitions, release sequence,
  automatic blockers, zero-credit verification, and paid-canary boundary.

The Application Map, Railway deployment guide, environment example, maintenance checklist, and
append-only change-order log are synchronized with the new workspace.

## Recovery evidence boundary

The application cannot claim that a Railway backup is recoverable merely because a backup exists.
`RCI_LAST_DATABASE_BACKUP_VERIFIED_AT` may be set only after backup/PITR evidence is inspected.
`RCI_LAST_RESTORE_DRILL_AT` may be set only after an isolated non-production restore reconciles the
database migration, definitions, queue history, AnalysisResults, publication state, artifact
metadata, representative bucket objects/checksums, protected admin access, and representative Price
and Competitive Intelligence reads. The restored environment must not contain production provider,
AI, email, or worker credentials. This phase does not perform or falsely attest that infrastructure
operation.

## Verification gates

- Python formatting, Ruff, MyPy, contracts, and the complete test suite pass locally: 791 tests
  passed and 16 credential/database/golden-data-dependent tests were explicitly skipped.
- TypeScript contracts, formatting, lint, typecheck, 86 unit tests, and the production build pass
  locally. Local browser execution remains affected by the known macOS Chromium `SIGTRAP`; the same
  Playwright suite passes in Linux CI and signed-in production browser acceptance passed.
- Reversible Alembic upgrade/downgrade/upgrade runs in Linux CI against its disposable Postgres
  service; this phase adds no migration.
- Four service-container builds.
- GitHub Actions, Railway deployments, public readiness, protected production System Operations,
  and one representative Price/Competitive read after deployment.
- No MetricsCart, PDP, OpenAI, SMTP, or paid canary call in this phase.

## Production release evidence

- Implementation commit: `8f14a06325169df086b1a1635e8fcf24f99713a3`
  (`Add production operations and release governance`).
- Truth-label correction commit: `517e598d7d68b58602335a31b5a96e4b74f64967`
  (`Correct operations provider configuration label`). The correction prevents the API container
  from implying that it can observe the worker container's collection-provider setting.
- GitHub Actions runs `33270091290` and `33270492530` completed successfully. The latter passed the
  documentation gate, Python formatting/Ruff/MyPy/contracts/full test suite, disposable-Postgres
  upgrade/downgrade/upgrade, TypeScript contracts/format/lint/typecheck/unit/build/Linux Playwright,
  and web/API/worker/scheduler container builds.
- Railway production deployments are healthy: web
  `e65338e6-da71-4243-8d34-16e257166f0e` and API
  `0250e356-9836-49fa-8160-778189c45650` run the correction commit; worker
  `dbab7ef5-6a50-48ff-a623-5c8d002a61c8` and scheduler
  `44712f8a-bb21-4a76-aac1-002a5a961224` run the implementation commit because the correction did
  not touch their watched build inputs.
- The zero-credit verifier passed web/API liveness and readiness in production and recorded
  `paid_provider_calls: 0`.
- Signed-in production browser acceptance passed for System Operations, Platform Docs, the Price
  Intelligence library and a milk retailer detail, the Competitive Intelligence library, and a
  governed ground-beef report. No browser warning or error was emitted on those checks.
- The deployed API reports commit `517e598d7d68`, migration `0048_price_catalog` matching repository
  head, zero queued/running/expired Search, analysis, PDP, Matching AI, and report-materialization
  tasks, zero active provider cooldowns, six ready reports, and zero open validation blockers.
- Overall state correctly remains `attention`: one preserved historical Spring Valley report
  materialization failed because its analysis was not decision-ready, and neither backup
  verification nor an isolated restore drill has been attested. No report, queue history, or
  recovery timestamp was altered to manufacture a green state.

## Rollback

The workspace and endpoint are read-only and require no new database table. Roll back the stateless
API/web deployment to remove them. The documentation gate can be reverted independently, but doing
so reduces change-control assurance and must be documented. Do not delete queue, publication,
provider-limit, AnalysisResult, Product Pack, Retailer Pack, or audit history.
