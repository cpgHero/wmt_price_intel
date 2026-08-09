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
```

### worker

```dotenv
PORT=8080
DATABASE_URL=${{postgres.DATABASE_URL}}
COLLECTION_PROVIDER=metricscart
METRICSCART_API_BASE_URL=https://api.metricscart.com
METRICSCART_GLOBAL_RPS=2
METRICSCART_GLOBAL_RPM=108
METRICSCART_MAX_ATTEMPTS=5
WORKER_CLAIM_LIMIT=10
WORKER_LEASE_SECONDS=300
ANALYSIS_PIPELINE_ENABLED=true
ANALYSIS_HISTORICAL_REPLAY_ENABLED=false
ANALYSIS_CLAIM_LIMIT=1
ANALYSIS_LEASE_SECONDS=600
ANALYSIS_MAX_ATTEMPTS=3
PRODUCT_DETAIL_ENRICHMENT_ENABLED=false
PRODUCT_DETAIL_RPS=3
PRODUCT_DETAIL_RPM=180
PRODUCT_DETAIL_CLAIM_LIMIT=1
PRODUCT_DETAIL_LEASE_SECONDS=300
PRODUCT_DETAIL_CACHE_TTL_SECONDS=604800
AI_ENABLED=false
OPENAI_MODEL_INSIGHT=<explicit model ID; required only when AI_ENABLED=true>
OPENAI_MODEL_NARRATIVE=<explicit model ID; required only when AI_ENABLED=true>
OPENAI_TIMEOUT_SECONDS=60
OPENAI_MAX_OUTPUT_TOKENS=8000
OPENAI_MAX_REQUEST_COST_USD=1.00
AI_MAX_METRICS=360
AI_MAX_ATTEMPTS=2
AI_LEASE_SECONDS=180
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
5. Deploy `api`. Its pre-deploy log must show Alembic at `0013_governed_ai`; then verify
   `/health/live` and `/health/ready` inside Railway.
6. Run the idempotent location import once in the API image:
   `rci-locations --source fixtures/location_master/locations.csv`. Confirm the expected Walmart and
   ALDI counts and that Target contains only `Country=USA` rows.
7. Deploy `worker` at one replica with `COLLECTION_PROVIDER=fake`; run a compact smoke collection,
   confirm leases, completion, and zero external provider calls, then switch to `metricscart`.
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

Keep `PRODUCT_DETAIL_ENRICHMENT_ENABLED=false` through migration and fixture acceptance. Enable it
only after an explicit enrichment run with a reviewed credit ceiling has been queued. Search and PDP
limits are independent per retailer/type but share their state across all worker replicas.

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

Increase only one replica at a time. After each increase, observe at least one representative run and
check queue latency, pages/minute, aggregate permit counts, 429s and `paused_until`, retries, lease
reclaims, duplicate task count, credits, database connections, CPU, and memory. Scale back immediately
if 429 frequency or lease expiry rises without useful throughput. Never compensate for provider 429s
by raising RPS/RPM above the contracted limit.

PDP workers use the same replica-scaling discipline. Each retailer/type limiter row is keyed as
`metricscart:pdp:<retailer_id>` plus a nonsecret credential hash, so Walmart PDP capacity does not
consume Walmart search capacity or ALDI PDP capacity.

## Rollback

- Application rollback: select the last healthy Railway deployment for the affected stateless
  service. Avoid rolling application code behind an irreversible schema change.
- Schema rollback: migrations are reversible and CI exercises `downgrade base`, but production
  downgrades require a database backup and explicit review of data-loss implications.
- Provider incident: set `COLLECTION_PROVIDER=fake` only for controlled smoke testing, or scale worker
  to zero to stop external calls. Pending tasks remain durable.
- Bucket incident: pause workers; do not mark a task successful unless its raw provider response was
  persisted. Restore service only after authenticated put/head/presign checks pass.

Current platform references: [Railway config as code](https://docs.railway.com/config-as-code/reference),
[private networking](https://docs.railway.com/private-networking),
[storage buckets](https://docs.railway.com/storage-buckets), and
[health checks](https://docs.railway.com/deployments/healthchecks).
