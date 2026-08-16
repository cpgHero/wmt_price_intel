# Security, Governance, and Observability

## Secrets

MetricsCart, OpenAI, object-storage, session, and SMTP credentials are server-side environment
variables only. Never persist plaintext credentials in collection or alert definitions, evidence,
events, email bodies, or logs. Rate-limit state uses a nonsecret credential-budget hash rather than
the key itself. SMTP is constructed only in API/scheduler processes and is never exposed to Next.js.

## Access control

V1 roles: Admin, Analyst, Viewer.
- Admin: provider settings, location imports, Product Pack publishing, users.
- Analyst: create/run collections, review QA, publish analyses.
- Viewer: read completed analyses/reports.

`/admin/docs` uses the existing eight-hour administrator session and returns its content through a
private, no-store same-origin route only after authentication. It documents operating controls but
contains no secret values, raw private object URIs, or credentials. Full individual accounts and
RBAC remain future work and are called out as an explicit limitation in the owner/admin guide.

## Artifact access

Private bucket by default. Generate short-lived signed URLs. Raw provider responses are more restricted than leadership reports.

## Audit events

Record definition version changes, run start/cancel/retry, schedule materialization, alert-version
publishing/evaluation, email enqueue/send/failure, manual QA decisions, Product Pack publish, report
generation, and benchmark updates.

## Metrics

- run duration and phase duration,
- tasks pending/running/succeeded/failed,
- provider response latency/status,
- PDP jobs pending/running/succeeded/failed and cache-hit rate,
- PDP planned vs actual billable credits by retailer,
- 429 count and cooldown seconds,
- estimated vs actual credits,
- normalized offers/page,
- classification confidence/review rate,
- strict match rate,
- QA issue counts,
- artifact generation failures,
- worker lease expirations/reclaims.
- schedule lag/materialization failures,
- analysis-evaluation lease expirations,
- alert trigger/suppression count,
- email pending age, retry count, terminal failure count.

## Structured logs

Include run_id, task_id/job_id, retailer_id, location key, page, worker_id, attempt, status, latency.
PDP raw-object metadata records parameter names, never values or the API key. Redact the API-key
query parameter before logs.
