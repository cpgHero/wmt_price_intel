# System Architecture

## Railway services

1. **web** - Next.js/TypeScript user interface.
2. **api** - FastAPI control plane, auth, collection definitions, run orchestration, results APIs, signed artifact access.
3. **worker** - horizontally scalable Python workers for collection, normalization, classification, matching, analytics, export jobs.
4. **scheduler** - small process/cron invocation that enqueues due collection definitions. Can share the worker image.
5. **postgres** - authoritative control plane and durable task queue.
6. **bucket** - S3-compatible object storage for raw pages, Parquet datasets, HTML, Excel, and audit packages.

Redis is intentionally omitted from V1. PostgreSQL handles durable task coordination and shared rate-limit state. Add Redis only after measuring a need.

## Data plane vs control plane

### PostgreSQL control plane
Stores definitions, versions, locations, run/task state, summary metrics, QA/validation issues, rate-limit state, artifact metadata, alerts, and audit history.

### Object-storage data plane
Stores immutable high-volume evidence:
- raw provider response pages (`json.gz`),
- checksummed historical source extracts (`csv`),
- normalized offers (`parquet`),
- classified offers (`parquet`),
- match detail (`parquet`),
- supporting CSVs,
- HTML/XLSX/ZIP exports.

Do not put large raw response bodies into PostgreSQL unless needed for a small diagnostic excerpt.

## Run lifecycle

`draft -> estimated -> queued -> collecting -> normalizing -> classifying -> analyzing -> validating -> generating_artifacts -> completed`

Terminal alternatives: `failed`, `cancelled`, `completed_with_warnings`.

## Collection task identity

Unique logical task key:
`collection_run_id + retailer_id + location_scope_key + page_number + request_fingerprint`

A unique database constraint prevents duplicate task rows. Workers claim tasks using a single transaction with `FOR UPDATE SKIP LOCKED` and set a lease owner/expiry.

## Shared MetricsCart limiting

A provider-budget row keyed by normalized credential budget key stores short-window and minute-window permit state plus `paused_until`. A transaction/advisory lock serializes permit issuance. A 429 updates shared cooldown so every replica waits.

## Analytical execution

Every completed live collection and historical import receives an immutable `analysis_input_set`.
The set links ordered, checksummed source artifacts to one zero-or-more-attempt durable
`analysis_run`. Historical imports receive a zero-credit workflow run so they use the same queue,
lease, output namespace, and audit path as live collections.

Workers read raw input artifacts from object storage, normalize to Parquet, then use Polars/DuckDB
for high-volume transformations and joins. PostgreSQL is not the primary dataframe engine.
