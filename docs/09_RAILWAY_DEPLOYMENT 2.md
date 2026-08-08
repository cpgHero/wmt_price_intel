# Railway Deployment Specification

## Services

- `web`: Next.js production server.
- `api`: FastAPI/uvicorn.
- `worker`: Python worker image, horizontally scalable replicas.
- `scheduler`: same Python image with scheduler command; can be Railway cron or small always-on poller.
- `postgres`: Railway PostgreSQL.
- `artifacts`: Railway S3-compatible Bucket.

## Environment variables

See `.env.example`. Minimum production secrets:
- `DATABASE_URL`
- `METRICSCART_API_KEY`
- object storage credentials/endpoint/bucket
- `OPENAI_API_KEY` when AI enabled
- session/JWT secret

## Networking

Use Railway private networking for web->api and worker->postgres where available. Public API exposure should be limited to endpoints required by the web application. Bucket downloads should use short-lived signed URLs.

## Worker scaling

Start with one worker replica and shared MetricsCart limiter enabled. Increase replicas gradually while verifying aggregate RPS/RPM, 429 count, duplicate claims, queue latency, and processing throughput.

## Deploy gates

- migrations complete,
- location seed/import verified,
- schema/contract tests pass,
- shared limiter tests pass,
- strawberry compact tests pass,
- no secrets in image/build logs,
- health/readiness endpoints pass.
