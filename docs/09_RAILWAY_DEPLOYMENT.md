# Railway Production Deployment

The deployable topology is six Railway resources in one project, environment, and region:

- `web`: Next.js production server; the only service with a public domain.
- `api`: FastAPI control plane on the private network; owns the Alembic pre-deploy migration.
- `worker`: durable queue consumer; start at exactly one replica.
- `scheduler`: always-on schedule, alert-evaluation, and email-delivery process. Postgres leases make
  it replica-safe, though the initial rollout remains one replica.
- `postgres`: Railway PostgreSQL, authoritative state and queue.
- `artifacts`: private Railway S3-compatible Bucket for raw and derived evidence.

Do not set a Railway Root Directory for the four source services. Every Docker build needs the
monorepo root as its context. Instead, set each service's Config File Path:

| Service | Config File Path |
| --- | --- |
| web | `/infra/railway/web.json` |
| api | `/infra/railway/api.json` |
| worker | `/infra/railway/worker.json` |
| scheduler | `/infra/railway/scheduler.json` |

The config files pin the Dockerfile, watch paths, health check, restart policy, and graceful drain.
Only the API runs `alembic -c database/alembic.ini upgrade head` as a pre-deploy command. Railway
runs that command inside the private network before the new API deployment can become active.

## Variable map

Use Railway reference variables instead of copying database or bucket credentials. The names below
assume the database service is named `postgres` and the Bucket is named `artifacts`.

### Shared non-secret variables

```dotenv
APP_ENV=production
APP_VERSION=0.1.0
METRICSCART_CREDIT_USD=0.002
RCI_LAST_DATABASE_BACKUP_VERIFIED_AT=<ISO-8601 timestamp after backup evidence is verified>
RCI_LAST_RESTORE_DRILL_AT=<ISO-8601 timestamp after an isolated restore drill passes>
LOG_LEVEL=INFO
```

### web

```dotenv
PORT=3000
RCI_API_INTERNAL_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}
```

### api

```dotenv
PORT=8000
DATABASE_URL=${{postgres.DATABASE_URL}}
RCI_REPOSITORY_ROOT=/app
OBJECT_STORAGE_ENDPOINT=${{artifacts.ENDPOINT}}
OBJECT_STORAGE_REGION=${{artifacts.REGION}}
OBJECT_STORAGE_BUCKET=${{artifacts.BUCKET}}
OBJECT_STORAGE_ACCESS_KEY_ID=${{artifacts.ACCESS_KEY_ID}}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${{artifacts.SECRET_ACCESS_KEY}}
OBJECT_STORAGE_FORCE_PATH_STYLE=false
RCI_INTERNAL_SERVICE_TOKEN=<same random secret as worker>
```

### worker

```dotenv
PORT=8080
DATABASE_URL=${{postgres.DATABASE_URL}}
COLLECTION_PROVIDER=metricscart
METRICSCART_API_BASE_URL=https://api.metricscart.com
METRICSCART_GLOBAL_RPS=2
METRICSCART_GLOBAL_RPM=108
METRICSCART_POST_429_RPS=2
METRICSCART_POST_429_RPM=108
METRICSCART_POST_429_RECOVERY_SECONDS=1800
METRICSCART_MAX_ATTEMPTS=5
METRICSCART_MAX_CONNECTIONS=256
METRICSCART_MAX_KEEPALIVE_CONNECTIONS=128
WORKER_CLAIM_LIMIT=10
WORKER_LEASE_SECONDS=300
WORKER_RETAILER_CONCURRENCY_LIMIT=80
ANALYSIS_PIPELINE_ENABLED=true
MATCHING_V2_SHADOW_ENABLED=false
MATCHING_V2_SHADOW_API_ENABLED=false
ANALYSIS_HISTORICAL_REPLAY_ENABLED=false
ANALYSIS_CLAIM_LIMIT=1
ANALYSIS_LEASE_SECONDS=600
REPORT_MATERIALIZATION_CLAIM_LIMIT=1
REPORT_MATERIALIZATION_LEASE_SECONDS=1800
ANALYSIS_MAX_ATTEMPTS=3
RCI_API_INTERNAL_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}
RCI_INTERNAL_SERVICE_TOKEN=<same random secret as api>
PRODUCT_DETAIL_ENRICHMENT_ENABLED=false
PRODUCT_DETAIL_RPS=3
PRODUCT_DETAIL_RPM=180
PRODUCT_DETAIL_GLOBAL_RPS=2
PRODUCT_DETAIL_GLOBAL_RPM=120
PRODUCT_DETAIL_CLAIM_LIMIT=18
PRODUCT_DETAIL_LEASE_SECONDS=300
PRODUCT_DETAIL_CACHE_TTL_SECONDS=2592000
PRODUCT_DETAIL_RENORMALIZATION_ENABLED=false
PRODUCT_DETAIL_RENORMALIZATION_CLAIM_LIMIT=8
PRODUCT_DETAIL_RENORMALIZATION_LEASE_SECONDS=300
AI_ENABLED=false
OPENAI_MODEL_INSIGHT=<explicit model ID; required only when AI_ENABLED=true>
OPENAI_MODEL_NARRATIVE=<explicit model ID; required only when AI_ENABLED=true>
OPENAI_MODEL_MATCHING_REVIEW=<explicit model ID; required for AI match drafts>
OPENAI_TIMEOUT_SECONDS=60
OPENAI_MAX_OUTPUT_TOKENS=8000
OPENAI_MAX_REQUEST_COST_USD=1.00
MATCHING_V2_AI_REVIEW_ENABLED=false
MATCHING_V2_AI_REVIEW_CONCURRENCY=2
OPENAI_MATCHING_TIMEOUT_SECONDS=90
OPENAI_MATCHING_MAX_OUTPUT_TOKENS=3000
OPENAI_MATCHING_MAX_REQUEST_COST_USD=0.35
OPENAI_MATCHING_REASONING_EFFORT=high
AI_MAX_METRICS=360
AI_MAX_ATTEMPTS=2
AI_LEASE_SECONDS=900
OBJECT_STORAGE_ENDPOINT=${{artifacts.ENDPOINT}}
OBJECT_STORAGE_REGION=${{artifacts.REGION}}
OBJECT_STORAGE_BUCKET=${{artifacts.BUCKET}}
OBJECT_STORAGE_ACCESS_KEY_ID=${{artifacts.ACCESS_KEY_ID}}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${{artifacts.SECRET_ACCESS_KEY}}
OBJECT_STORAGE_FORCE_PATH_STYLE=false
```

Set `METRICSCART_API_KEY` as a sealed worker secret. Do not share it with `web`. When governed AI
is accepted for production, set `OPENAI_API_KEY` as a sealed worker-only secret, choose both model
IDs explicitly, and then set `AI_ENABLED=true`. The worker rejects unknown model IDs and any request
whose conservative maximum cost exceeds `OPENAI_MAX_REQUEST_COST_USD`; with two sequential roles,
the default maximum is $2 per analysis. OpenAI credentials and models are not required for the
deterministic pipeline.

`MATCHING_V2_AI_REVIEW_ENABLED` must be set consistently on `api` and `worker`. The API receives no
OpenAI credential: it only creates an authenticated durable draft task. `OPENAI_API_KEY` remains a
sealed worker-only secret. The worker claims tasks with `FOR UPDATE SKIP LOCKED`, uses the explicit
matching-review model and per-request cost ceiling, and writes a non-authoritative result for human
review. `MATCHING_V2_AI_REVIEW_CONCURRENCY` is worker-only, defaults to `2`, and is clamped to `1–4`.
At the default, no more than two matching-review calls can be in flight per worker process, so the
configured $0.35 per-request ceiling implies at most $0.70 of simultaneous request exposure per
worker. The UI reads durable batch and task status from Postgres; it does not infer progress from
the currently visible page.

New reports use the same `RCI_INTERNAL_SERVICE_TOKEN` on `api` and `worker` to perform durable,
zero-provider-call materialization. The worker claims one `report_materialization_job` by default,
heartbeats an 1,800-second lease, and stages bounded Price Architecture and basis-by-radius
Competitive Portfolio documents through authenticated private API operations. Do not raise
`REPORT_MATERIALIZATION_CLAIM_LIMIT` until database, object-store, and API pressure are measured;
each portfolio already uses bounded internal concurrency. Administrators monitor and retry jobs at
`/admin/report-publishing`. A failed job never activates its pending result or archives the prior
trusted report.

The protected `/admin/operations` workspace reads live queue, publication, cooldown, recent-credit,
migration, Product Pack, Retailer Pack, and allowlisted Railway release metadata from the API. Set
`METRICSCART_CREDIT_USD` on `api` to the current accounting rate used for the displayed estimate;
provider invoices remain authoritative. `RCI_LAST_DATABASE_BACKUP_VERIFIED_AT` and
`RCI_LAST_RESTORE_DRILL_AT` are operator attestations, not automatic Railway evidence. Set the first
only after inspecting recoverable backup/PITR evidence and the second only after a non-production
restore has passed the documented reconciliation. Missing or stale values remain visible as
attention states.

One Match Certification AI-review batch may contain up to 1,500 explicitly selected or
queue-wide eligible cases. The server ranks queue-wide scope by Search-derived benchmark and
competitor exposure, rejects known third-party/finalized/already-drafted cases, and refuses paid
work when either product has missing or zero observed-location evidence. The UI requires an
identified administrator to confirm the exact case count and worst-case aggregate policy exposure.
The worker concurrency control above—not the batch size—limits simultaneous OpenAI calls.

A terminal Matching v2 task enters `needs_review` after its two automatic attempts. Retrying that
work is an explicit administrator action, never an in-place reset. The individual or filtered-page
bulk confirmation calls the protected API, which creates a new task linked to the failed task,
preserves prior usage/error history, reapplies first-party seller and final-decision eligibility,
blocks prompt/input integrity failures, and caps administrator retry rounds at three. Each new task
uses the same worker-only model credential and per-request cost ceiling and remains advisory until a
human makes the final match decision.

### scheduler

```dotenv
PORT=8080
DATABASE_URL=${{postgres.DATABASE_URL}}
RCI_REPOSITORY_ROOT=/app
SCHEDULER_POLL_SECONDS=30
SCHEDULER_CLAIM_LIMIT=10
SCHEDULER_LEASE_SECONDS=300
EMAIL_PROVIDER=smtp
SMTP_HOST=<sealed secret or private relay host>
SMTP_PORT=587
SMTP_USERNAME=<sealed secret>
SMTP_PASSWORD=<sealed secret>
SMTP_FROM_EMAIL=retail-intelligence@example.com
SMTP_STARTTLS=true
```

If email is intentionally disabled, set `EMAIL_PROVIDER=unavailable`; queued deliveries fail through
the normal bounded retry path instead of silently disappearing. `EMAIL_PROVIDER=fake` is a
non-network acceptance mode and must not be mistaken for real delivery. Configure SMTP before
publishing any email-enabled alert or leadership delivery in production.

Railway's current Buckets use virtual-hosted S3 URLs by default, hence
`OBJECT_STORAGE_FORCE_PATH_STYLE=false`. If the Bucket credentials panel explicitly says an older
bucket needs path style, change this one value to `true` on `api` and `worker`.

## Networking and access

- Generate a public domain for `web` only.
- Leave `api`, `worker`, `scheduler`, and PostgreSQL without public HTTP domains.
- Browser actions call same-origin Next.js route handlers; those handlers and Server Components call
  `api` over `http://api.railway.internal:8000` through the reference variable above.
- The Bucket remains private. API responses expose neither bucket credentials nor raw storage URIs;
  artifact downloads are short-lived presigned URLs (five minutes by default).
- Place every service and stateful resource in the same Railway region to avoid cross-region database
  latency. Add multi-region stateless replicas only after the control plane has production evidence.

## Health, shutdown, and logs

| Service | Liveness | Readiness / Railway check |
| --- | --- | --- |
| web | `/health` | `/health/ready` also verifies private API reachability |
| api | `/health/live` | `/health/ready` verifies PostgreSQL |
| worker | `/health/live` | `/health/ready` verifies PostgreSQL |
| scheduler | `/health/live` | `/health/ready` verifies PostgreSQL |

The worker and scheduler host a small dependency-free health server on Railway's `PORT`. A worker
gets 90 seconds of deployment drain time: SIGTERM stops new claims, while in-flight work finishes or
its Postgres lease eventually becomes reclaimable. API and web deployments overlap for 20 seconds;
singleton worker and scheduler deployments do not overlap.

Python processes emit one-line JSON logs to stdout with Railway deployment/replica metadata. Worker
task logs include run, task, retailer, location, page, attempt, status, latency, and failure class.
Scheduler tick logs include synchronized schedules, materialized runs, evaluated analyses, triggered
events, sent email count, and bounded failures.
Known provider-key query parameters are redacted. Do not re-enable HTTPX request-level logging while
MetricsCart uses query-parameter authentication.

## First production rollout

1. Require the repository CI workflow on `main`; it runs Postgres migrations up/down, queue and
   shared-limiter integration tests, contracts, application tests, build, and web end-to-end checks.
2. Create `postgres` and `artifacts` in the intended production region. Enable daily and weekly
   PostgreSQL volume backups; for stricter recovery objectives, enable Railway PostgreSQL PITR.
3. Create the four GitHub-backed services with no Root Directory and assign the config paths above.
4. Add reference variables and sealed secrets. Confirm no plaintext secret appears in a shared or
   web variable.
5. Deploy `api`. Its pre-deploy log must show Alembic at the repository's single current migration
   head (System Operations currently expects `0048_price_catalog`); then verify
   `/health/live` and `/health/ready` inside Railway.
6. Run the idempotent location import once in the API image:
   `rci-locations --source fixtures/location_master/locations.csv`. Confirm the expected Walmart and
   ALDI counts and that Target contains only `Country=USA` rows. A retailer-only current-roster
   refresh may use the same importer against a retained source, for example
   `rci-locations --source fixtures/location_master/retailer_updates/aldi-locations-2026-08-22.csv`.
   Record the import ID and checksum; do not delete frozen collection geography snapshots.
7. Run the fake-provider smoke test only in a non-production environment. Production workers fail
   closed when `COLLECTION_PROVIDER=fake`; set `COLLECTION_PROVIDER=metricscart` before deploying a
   production worker.
8. Use the web collection wizard for a deliberately small one-location MetricsCart strawberry run.
   Verify the exact estimate and approval cap, ALDI availability gate, raw `json.gz` objects, actual
   credits, redacted logs, immutable Parquet datasets, canonical result, and no task duplication.
9. Publish one disabled test alert and one scheduled collection definition. Deploy `scheduler` as
   one replica, enable the definitions, and verify one run per cron slot, one evaluation per result,
   immutable evidence references, and one idempotent SMTP delivery.
10. Deploy `web`; generate a public domain, verify web readiness over the private API link, and
    confirm the Automation page reports schedule, alert-event, and delivery state.
11. Publish the compact strawberry AnalysisResult and generate HTML, XLSX, email, and audit ZIP.
    Confirm each download URL expires and no bucket object is anonymously readable.
12. Run a backup restore drill into a non-production environment before declaring the rollout done.
13. Open `/admin/operations`, reconcile its commit/deployment/migration identity, require zero
    expired leases, and run the zero-credit verifier:
    `python3 scripts/verify_release_readiness.py --web-base <public-web-url> --api-base <private-api-url>`.
    Run this inside the Railway network when the API has no public domain. A paid Search/PDP/AI
    canary remains a separate explicitly approved run.

Keep `PRODUCT_DETAIL_ENRICHMENT_ENABLED=false` through migration and fixture acceptance. Enable it
only after an explicit enrichment run with a reviewed credit ceiling has been queued. Search and PDP
limits are independent per retailer/type but share their state across all worker replicas.

`PRODUCT_DETAIL_RENORMALIZATION_ENABLED` is independent of paid enrichment. Enable it after the
`0028_pdp_renormalization` migration to replay retained immutable PDP payloads through
the current normalizer. It reads the private bucket, creates append-only normalization revisions,
and spends zero MetricsCart credits. Leave it enabled so future normalizer versions and source-field
drift are repaired and audited without recollection.

`MATCHING_V2_SHADOW_ENABLED` remains `false` until migration `0029_matching_architecture_v2`, a
versioned Product Pack `matching_v2` policy, and its candidate-recall fixture have passed. When
enabled, the worker writes immutable `matching_v2_shadow` JSON audit artifacts only. Shadow output
cannot alter the current AnalysisResult, publication, scorecards, match decisions, or AI context.
Each Product Pack must cap `maximum_candidate_pairs`; a shadow failure is logged and cannot fail the
authoritative analysis.

Set `MATCHING_V2_SHADOW_API_ENABLED=true` on `api` only after shadow artifacts exist. The endpoint
is read-only, bounded to 500 edges per request, and explicitly labels its output non-authoritative.

## Historical import job

Historical import is an explicit administrative job, not an API upload and not a MetricsCart
collection. Run validation before granting the process database or bucket credentials:

```bash
uv run rci-import-historical \
  --manifest examples/historical-input-manifest.strawberries.json \
  --source-root /path/to/source/files \
  --validate-only
```

Remove `--validate-only` only in an environment with private Postgres and bucket variables. The
command uploads immutable source bytes, records an audit event, and enqueues a zero-credit analysis
run. Repeating the identical command is idempotent. Do not copy source files into the Git image,
place bucket credentials in a manifest, or expose this command through a public web route.

Keep `ANALYSIS_HISTORICAL_REPLAY_ENABLED=false` through Phase 9.5.2. The durable jobs remain queued
without consuming attempts. Phase 9.5.3 enables this flag only after the full-source columnar replay
and memory gates pass.

## Worker scaling runbook

Railway defaults a service to one replica; explicitly verify one worker replica in Settings → Scale
before enabling MetricsCart. Keep `METRICSCART_GLOBAL_RPS=2` and `METRICSCART_GLOBAL_RPM=108`
identical across replicas because every replica shares the same credential-hash budget row. The
scheduler may also scale after initial validation: schedule, analysis, and email work are leased in
Postgres and schedule slots/delivery keys are unique.

An owner-approved production collection may raise the shared Search limiter to the provider's
confirmed retailer-specific ceiling, currently `METRICSCART_GLOBAL_RPS=3` and
`METRICSCART_GLOBAL_RPM=180`. `WORKER_RETAILER_CONCURRENCY_LIMIT` is a per-replica safety boundary:
it prevents a slow retailer from consuming every async task slot while another retailer has unused
quota. `WORKER_CLAIM_LIMIT` and `METRICSCART_MAX_CONNECTIONS` must be large enough to accommodate
the sum of independently active retailer lanes; increasing them never changes the database-backed
start-rate limit.

Provider 429 evidence is retailer-scoped. After a 429, every replica honors the shared cooldown and
temporarily paces only that retailer at `METRICSCART_POST_429_RPS` /
`METRICSCART_POST_429_RPM`. A retailer returns to the normal ceiling only after the configured
recovery window passes without another 429. Do not disable the adaptive lane to make a run appear
faster.

Increase only one replica at a time. After each increase, observe at least one representative run and
check queue latency, pages/minute, aggregate permit counts, 429s and `paused_until`, retries, lease
reclaims, duplicate task count, credits, database connections, CPU, and memory. Scale back immediately
if 429 frequency or lease expiry rises without useful throughput. Never compensate for provider 429s
by raising RPS/RPM above the contracted limit.

PDP workers use the same replica-scaling discipline. Every request must obtain both an account-wide
PDP permit (`metricscart:pdp:all_retailers`) and a retailer/type permit
(`metricscart:pdp:<retailer_id>`), each keyed by the same nonsecret credential hash. The defaults
pace all retailer PDP traffic at two requests per second / 120 per minute while retaining each
retailer's documented three requests per second / 180 per minute ceiling. A 429 pauses both scopes,
preventing replicas from exhausting job retries during a hidden account-wide provider cooldown.
Search and PDP remain independent limiter domains.

## Rollback

- Application rollback: select the last healthy Railway deployment for the affected stateless
  service. Avoid rolling application code behind an irreversible schema change.
- Schema rollback: migrations are reversible and CI exercises `downgrade base`, but production
  downgrades require a database backup and explicit review of data-loss implications.
- Provider incident: use `COLLECTION_PROVIDER=fake` only in a non-production environment, or scale
  worker to zero to stop external calls. Pending tasks remain durable.
- Bucket incident: pause workers; do not mark a task successful unless its raw provider response was
  persisted. Restore service only after authenticated put/head/presign checks pass.

## Backup and isolated restore drill

Recovery attestations are evidence, not configuration defaults. Set
`RCI_LAST_DATABASE_BACKUP_VERIFIED_AT` only after a recoverable backup is inspected. Set
`RCI_LAST_RESTORE_DRILL_AT` only after an isolated restore passes the complete acceptance sequence.

Use the maintained procedure and evidence format in
[`128_PHASE_13_74_RECOVERY_DRILL_AND_BACKUP_GOVERNANCE.md`](128_PHASE_13_74_RECOVERY_DRILL_AND_BACKUP_GOVERNANCE.md).
At minimum, every drill must:

1. restore into a dedicated non-production Postgres service with paid and mutating services absent;
2. checksum the dump before and after transfer;
3. run `scripts/recovery_reconcile.sql` against production and recovery and require an exact diff;
4. reconcile representative private bucket objects to database byte-size and SHA-256 metadata;
5. prove unauthenticated admin denial and authenticated admin access;
6. exercise one publication-materialized Price read and one projected Competitive read; and
7. remove temporary dump files and credentials after the evidence record is durable.

Railway volume backups, PITR, and logical dumps address different failures. Keep an independent
logical-dump procedure even when Railway backups are enabled. PITR is not retroactive and may
redeploy Postgres when enabled; schedule that change in an observed maintenance window. A successful
manual restore drill does not imply that PITR or scheduled backups are active.

Current platform references: [Railway config as code](https://docs.railway.com/config-as-code/reference),
[private networking](https://docs.railway.com/private-networking),
[storage buckets](https://docs.railway.com/storage-buckets), and
[health checks](https://docs.railway.com/deployments/healthchecks).
