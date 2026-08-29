# Phase 13.73 — Production Operations, Recovery, and Release Governance

Status: implemented; local release gates pass, Linux CI and production verification pending

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

Platform Docs version 1.3.72 adds:

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
  locally. Local browser execution is blocked by the known macOS Chromium `SIGTRAP`; Linux CI and
  signed-in production browser acceptance remain required.
- Reversible Alembic upgrade/downgrade/upgrade runs in Linux CI against its disposable Postgres
  service; this phase adds no migration.
- Four service-container builds.
- GitHub Actions, Railway deployments, public readiness, protected production System Operations,
  and one representative Price/Competitive read after deployment.
- No MetricsCart, PDP, OpenAI, SMTP, or paid canary call in this phase.

## Rollback

The workspace and endpoint are read-only and require no new database table. Roll back the stateless
API/web deployment to remove them. The documentation gate can be reverted independently, but doing
so reduces change-control assurance and must be documented. Do not delete queue, publication,
provider-limit, AnalysisResult, Product Pack, Retailer Pack, or audit history.
