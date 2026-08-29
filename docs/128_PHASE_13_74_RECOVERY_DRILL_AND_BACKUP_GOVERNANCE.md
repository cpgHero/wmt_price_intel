# Phase 13.74 — Recovery Drill and Backup Governance

**Status:** completed and production-attested on 2026-08-29  
**Provider/AI spend:** zero  
**Production mutation during validation:** one named Postgres volume backup, daily/weekly backup schedules, and two recovery-attestation timestamps only

## Objective

Prove that the production control plane can be restored into an isolated Railway environment without replacing production, issuing provider or AI calls, sending email, or claiming success from table counts alone. The acceptance boundary includes database integrity, private-object evidence, protected administrator access, and representative Price and Competitive Intelligence reads.

## Isolation and fail-closed controls

The drill used Railway environment `recovery-drill-20260829` with a dedicated Postgres service and a dedicated `recovery-api-app` service. The recovery API referenced only the restored database. MetricsCart, OpenAI, email, worker, scheduler, matching-review, Product Pack authoring, and PDP-enrichment execution were absent or disabled. `COLLECTION_PROVIDER=fake` prevented production collection. Bucket access was added only after database reconciliation and only for read-path acceptance; the temporary environment is not an operational worker environment.

No production application service was pointed at the recovered database. No restoration occurred over the production volume.

## Recovery evidence

| Evidence | Result |
| --- | --- |
| Named production volume backup | `recovery-drill-20260829`; 2,734 MB referenced; retained without an expiry at drill time |
| Logical dump | PostgreSQL custom format; 422 MB; PostgreSQL 18.4; 679 TOC entries |
| Logical dump SHA-256 | `4afddeac1b311af3dcefb96e0ae953b893eb6de02f95d138f6c6c444e7e7c3be` matched before and after transfer |
| Restore | `pg_restore --jobs=4 --exit-on-error --no-owner --no-acl`; completed in 67 seconds |
| Restored database size | 1,285 MB after restore and database rename |
| Schema head | `0048_price_catalog` in both production and recovery |
| Exact reconciliation | Byte-for-byte match across migration head and 19 trust-critical table counts |
| Private-object evidence | Dataset Parquet, Milk HTML report, and Egg audit ZIP each matched database byte size and SHA-256 metadata |
| API health | `/health/live` and `/health/ready` returned HTTP 200; Postgres dependency reported ready |
| Admin boundary | `/api/v1/admin/operations` returned HTTP 401 without a credential and HTTP 200 with the isolated recovery credential |
| Price read | Milk paged Price catalog returned HTTP 200, 5 of 649 products, and brand/brand-type/seller facets in 0.19 seconds |
| Competitive read | Ground Beef three-mile retailer scorecards returned HTTP 200 and two governed scorecards in 4.22 seconds |

The canonical reconciliation query is [`scripts/recovery_reconcile.sql`](../scripts/recovery_reconcile.sql). The drill matched these production and recovery values exactly:

- 1 organization, 100 retailers, and 182,443 retailer locations;
- 36 collection definitions, 48 collection runs, and 36,211 durable collection tasks;
- 17,555 dataset artifacts, 62 analysis runs, 47 analysis results, and 96 publication records;
- 294 report artifacts and 8 report-materialization jobs;
- 8,710 PDP snapshots, 17,445 Matching v2 cases, and 5,367 review submissions;
- 127 Competitive Portfolio materializations and 11,725 audit events.

`price_intelligence_snapshot` contained zero rows in both databases. That exact match proves restore fidelity; Price Intelligence currently uses publication-time compact catalogs and retained artifacts rather than that legacy table.

## Recovery objectives and limitations

The measured database restore operation was 67 seconds after the dump was available. This is a component recovery time, not a complete production RTO: environment creation, transfer, deployment, DNS, credentials, acceptance, and operator decision time must be included in an incident. The logical dump is a point-in-time copy created during the drill; it does not establish continuous recovery-point coverage.

Railway PITR was disabled and no scheduled volume backup was configured at drill start. The drill created a named manual volume backup and then enabled non-disruptive daily and weekly schedules. Daily retention is six days; weekly retention is 27 days. PITR remains disabled and is not retroactive. Enabling PITR can redeploy Postgres, so it requires a separately observed maintenance window. Scheduled backups and PITR must not replace the independent logical-dump procedure.

The legacy unpaginated full Price payload remained slow on a cold recovery API process and exceeded the 30-second operator shell window. The user-facing, publication-materialized paged catalog passed in 0.19 seconds and is the governed Home read path. The slow legacy endpoint remains a performance limitation to remove or bound; it did not prevent recovery acceptance.

## Operator procedure

1. Create a new Railway recovery environment and dedicated Postgres service.
2. Disable or omit every provider, AI, email, worker, scheduler, PDP, and mutating admin capability.
3. Create and checksum a custom-format logical production dump using a read-only operation.
4. Transfer the dump without printing credentials, verify its checksum, and restore with `--exit-on-error`, `--no-owner`, and `--no-acl`.
5. Run `scripts/recovery_reconcile.sql` against production and recovery and require an exact diff.
6. Verify representative private objects against immutable database byte-size and checksum metadata.
7. Start a dedicated recovery API, verify ready state and the protected administrator boundary, then exercise paged Price and projected Competitive reads.
8. Record evidence before setting either production recovery attestation.
9. Remove temporary dumps and credentials, and delete or stop the isolated recovery resources after the evidence record is durable.

## Acceptance decision

The isolated logical restore, database reconciliation, bucket-object verification, administrator boundary, and representative intelligence reads passed. Daily and weekly Railway backup schedules are active. Production System Operations reports both attestations as current after API deployment `501d614e-26eb-4183-aa4b-44589b0ae802`. The temporary production and local dump files, recovery-only bucket credentials, services, database volume, and `recovery-drill-20260829` environment were then permanently removed; the named production backup and this non-secret evidence record remain. PITR remains an explicit maintenance-window follow-up and is not implied by those attestations.
