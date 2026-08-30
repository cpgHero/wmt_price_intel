# Phase 13.76 — PITR and Database Credential Governance

**Status:** production-complete and zero-credit verified on 2026-08-29  
**Provider/AI spend:** zero  
**Authoritative data, matching, or reporting changes:** none

## Objective

Close the stateful recovery and database-credential follow-ups from Phase 13.75 without changing Search evidence, PDP evidence, certified relationships, Product Packs, metrics, or publications:

1. enable Railway Postgres point-in-time recovery (PITR) in an observed maintenance window;
2. rotate the production database role credential without exposing the replacement;
3. bind API, worker, and scheduler to the Railway Postgres service reference so later credential changes propagate consistently; and
4. prove fresh database connectivity and application readiness without paid MetricsCart or OpenAI calls.

The platform owner explicitly deferred rotation of the OpenAI API key, MetricsCart API key, and administrator password. Those values were not changed in this phase.

## Pre-maintenance gate

Before the stateful change:

- System Operations reported `healthy`;
- Search collection, analysis, PDP enrichment, Matching AI review, and report materialization each had zero queued or running work;
- there were zero active blocked reports and zero open publication blockers; and
- the retained named recovery-drill backup `recovery-drill-20260829` was present for the 2,734 MB Postgres volume.

## Production changes

- Railway PITR was enabled for the standalone production Postgres service. Railway created and wired the dedicated `Postgres-PITR` recovery bucket and redeployed Postgres.
- API, worker, and scheduler `DATABASE_URL` variables were explicitly set to the Railway service reference `${{postgres.DATABASE_URL}}`, then redeployed successfully.
- The live Postgres role password was replaced, and Postgres `POSTGRES_PASSWORD`, `PGPASSWORD`, and `DATABASE_URL` were updated coherently without logging the installed credential.
- Postgres and all three database consumers were redeployed inside the maintenance window.

PITR starts at enablement; it does not make earlier time points recoverable. The existing named backup and daily/weekly schedules remain separate recovery layers.

## Verification

- Railway reported PITR `enabled: true`, `bucketWired: true`, and live availability.
- PostgreSQL reported `archive_mode=on`, `wal_level=replica`, and a configured archive command.
- A forced WAL switch produced one successfully archived segment, zero failed segments, and a recorded archive timestamp.
- The resolved database URL checksum matched across Postgres, API, worker, and scheduler; no credential or reversible derivative was printed.
- A brand-new API-container database connection completed `SELECT 1` successfully after Postgres recovery.
- Web liveness/readiness and API liveness/readiness all returned HTTP 200.
- System Operations returned `healthy`; all five durable queues remained idle and publication blockers remained zero.
- The release-readiness verifier reported `paid_provider_calls: 0`.

The Railway CLI's optional detailed PITR coverage probe could not offer its default `~/.ssh/id_ed25519` identity in this desktop environment, even though the configured Railway identity works for service SSH. Direct database evidence therefore verifies WAL archiving, while Railway's top-level PITR status verifies enablement, bucket wiring, and live availability.

## Operating rules

- Keep application database consumers on `${{postgres.DATABASE_URL}}`; do not paste copied connection URLs into API, worker, or scheduler.
- Treat database-password rotation as observed stateful maintenance: verify idle queues and backup evidence, rotate the live role and Railway variables coherently, redeploy consumers, and require a fresh connection plus zero-credit acceptance before closing the window.
- Never infer PITR health solely from a configured bucket. Confirm Railway status and PostgreSQL archiver success/failure evidence.
- Never overwrite or delete raw snapshots, PDP evidence, match certification, AnalysisResults, publications, or audit lineage during recovery work.
- Keep provider-key and administrator-password rotation separately coordinated with the owner; this phase does not imply those deferred rotations occurred.

