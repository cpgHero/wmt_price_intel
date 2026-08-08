# Local development

Prerequisites are Python 3.14.6, uv 0.11.28, Node.js 24.18.0, pnpm 11.20.0,
and Docker with Compose.

1. Copy `.env.example` to `.env` and keep the development-only defaults local.
2. Run `make bootstrap`.
3. Run `make dev` to start Postgres 18.4 and the S3-compatible local bucket.
4. Run `uv run alembic -c database/alembic.ini upgrade head`.
5. Run `uv run rci-locations` to idempotently import the supplied location master.
6. Start the API with `uv run uvicorn rci_api.main:app --reload --port 8000`.
7. Start the web application with `pnpm --filter @rci/web dev`.

The worker defaults to `COLLECTION_PROVIDER=fake`, so local development cannot accidentally call
MetricsCart. To exercise the real provider deliberately, create the configured private bucket, set
`COLLECTION_PROVIDER=metricscart`, and provide the MetricsCart and object-storage variables from
`.env.example`. Production/Railway workers must use that explicit mode. Raw responses are written
as immutable, attempt-scoped `json.gz` objects before a task is credited or paginated.

Run `make check` before opening a pull request. `make down` stops local infrastructure
without deleting its named volumes.
