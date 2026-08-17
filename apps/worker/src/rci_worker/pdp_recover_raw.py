"""Recover immutable PDP responses left uncommitted after a worker interruption.

This command never imports or constructs the MetricsCart HTTP client. Its only external
reads are Postgres and the configured object bucket. The default mode is a dry run;
``--apply`` additionally requires the paid PDP worker to be disabled.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_products import (
    MetricsCartProductDetailAdapter,
    PostgresProductDetailRepository,
    ProductDetailCatalog,
    ProductDetailFetchResult,
    ProductDetailJob,
    ProductDetailRawArtifact,
    ProductDetailRequestContext,
)


@dataclass(frozen=True, slots=True)
class RawClassification:
    http_status: int
    billable: bool
    failure_class: str | None = None
    failure_message: str | None = None
    should_retry: bool = False
    retry_delay_seconds: float = 0


@dataclass(frozen=True, slots=True)
class RawEvidence:
    job: ProductDetailJob
    storage_key: str
    compressed: bytes
    body: bytes
    payload: dict[str, Any]
    observed_at: datetime
    response_content_type: str | None
    classification: RawClassification


def _enabled(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def classify_raw_payload(payload: dict[str, Any]) -> RawClassification:
    """Infer only response shapes that are unambiguous without stored HTTP metadata."""

    if isinstance(payload.get("name"), str) and payload["name"].strip():
        return RawClassification(http_status=200, billable=True)
    message = str(payload.get("message") or payload.get("error") or "").strip()
    if "rate limit" in message.lower():
        return RawClassification(
            http_status=429,
            billable=False,
            failure_class="rate_limit",
            failure_message=message or "MetricsCart HTTP 429",
            should_retry=True,
            retry_delay_seconds=60,
        )
    raise ValueError("raw response does not have an unambiguous recoverable response shape")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())),
    )
    return parser.parse_args()


def _context(document: dict[str, Any]) -> ProductDetailRequestContext:
    def optional(name: str) -> str | None:
        value = document.get(name)
        return str(value) if value is not None else None

    return ProductDetailRequestContext(
        product_id=str(document["product_id"]),
        zipcode=optional("zipcode"),
        store=optional("store"),
        fulfillment_type=optional("fulfillment_type"),
        shopping_type=optional("shopping_type"),
        url=optional("url"),
    )


def _job(row: dict[str, Any], catalog: ProductDetailCatalog) -> ProductDetailJob:
    retailer_id = str(row["retailer_id"])
    endpoint = catalog.get(retailer_id)
    queued_endpoint = dict(row["endpoint"])
    for name, expected in {
        "retailer_id": endpoint.retailer_id,
        "endpoint_id": endpoint.endpoint_id,
        "path": endpoint.path,
        "contract_version": endpoint.contract_version,
        "credits_per_successful_page": endpoint.credits_per_successful_page,
    }.items():
        if queued_endpoint.get(name) != expected:
            raise ValueError(
                f"queued endpoint mismatch for {retailer_id}: {name}="
                f"{queued_endpoint.get(name)!r}, catalog={expected!r}"
            )
    return ProductDetailJob(
        id=str(row["id"]),
        run_id=str(row["enrichment_run_id"]),
        canonical_product_db_id=str(row["canonical_product_id"]),
        canonical_product_id=str(row["canonical_product_stable_id"]),
        retailer_id=retailer_id,
        endpoint=endpoint,
        context=_context(dict(row["request_context"])),
        request_checksum=str(row["request_checksum"]),
        credits_per_call=int(row["credits_per_call"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
    )


async def _uncommitted_jobs(
    database: DatabaseProbe,
    run_id: str,
    catalog: ProductDetailCatalog,
) -> list[ProductDetailJob]:
    async with database.engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT j.*, p.canonical_product_id AS canonical_product_stable_id
                        FROM product_detail_job j
                        JOIN canonical_product p ON p.id = j.canonical_product_id
                        JOIN product_detail_enrichment_run r ON r.id = j.enrichment_run_id
                        WHERE j.enrichment_run_id::text = :run_id
                          AND r.status = 'active'
                          AND j.status IN ('queued', 'running')
                          AND j.attempt_count > 0
                          AND NOT EXISTS (
                            SELECT 1 FROM product_detail_snapshot s
                            WHERE s.product_detail_job_id = j.id
                              AND s.attempt_number = j.attempt_count
                          )
                        ORDER BY j.retailer_id, j.created_at, j.id
                        """
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .all()
        )
    return [_job(dict(row), catalog) for row in rows]


def _raw_prefix(job: ProductDetailJob) -> str:
    return (
        "raw/provider=metricscart/type=pdp/"
        f"retailer_id={job.retailer_id}/endpoint_id={job.endpoint.endpoint_id}/"
        f"request={job.request_checksum}/attempt={job.attempt_count:04d}/"
    )


def _read_raw(client: Any, bucket: str, job: ProductDetailJob) -> RawEvidence | None:
    listing = client.list_objects_v2(Bucket=bucket, Prefix=_raw_prefix(job), MaxKeys=2)
    objects = listing.get("Contents", [])
    if not objects:
        return None
    if len(objects) != 1 or listing.get("IsTruncated"):
        raise RuntimeError(f"expected exactly one immutable raw response for job {job.id}")
    storage_key = str(objects[0]["Key"])
    response = client.get_object(Bucket=bucket, Key=storage_key)
    compressed = response["Body"].read()
    body = gzip.decompress(compressed)
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"raw response for job {job.id} is not a JSON object")
    metadata = response.get("Metadata", {})
    stored_status = metadata.get("http-status") if isinstance(metadata, dict) else None
    classification = classify_raw_payload(payload)
    if stored_status is not None and int(stored_status) != classification.http_status:
        raise ValueError(f"stored HTTP status conflicts with raw payload for job {job.id}")
    observed_at = objects[0].get("LastModified") or response.get("LastModified")
    if not isinstance(observed_at, datetime):
        observed_at = datetime.now(UTC)
    elif observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return RawEvidence(
        job=job,
        storage_key=storage_key,
        compressed=compressed,
        body=body,
        payload=payload,
        observed_at=observed_at,
        response_content_type=response.get("ContentType"),
        classification=classification,
    )


async def _acquire_recovery_lease(
    database: DatabaseProbe,
    job: ProductDetailJob,
    worker_id: str,
) -> bool:
    async with database.engine.begin() as connection:
        updated = await connection.execute(
            text(
                """
                UPDATE product_detail_job j
                SET status = 'running', locked_by = :worker_id, locked_at = now(),
                    lease_expires_at = now() + interval '10 minutes'
                FROM product_detail_enrichment_run r
                WHERE r.id = j.enrichment_run_id AND r.status = 'active'
                  AND j.id::text = :job_id
                  AND j.enrichment_run_id::text = :run_id
                  AND j.status IN ('queued', 'running')
                  AND j.attempt_count = :attempt_count
                  AND NOT EXISTS (
                    SELECT 1 FROM product_detail_snapshot s
                    WHERE s.product_detail_job_id = j.id
                      AND s.attempt_number = j.attempt_count
                  )
                RETURNING j.id
                """
            ),
            {
                "worker_id": worker_id,
                "job_id": job.id,
                "run_id": job.run_id,
                "attempt_count": job.attempt_count,
            },
        )
        return updated.first() is not None


async def _requeue_without_raw(
    database: DatabaseProbe,
    run_id: str,
    jobs: list[ProductDetailJob],
) -> int:
    job_ids = [job.id for job in jobs if job.status == "running"]
    if not job_ids:
        return 0
    statement = text(
        """
        UPDATE product_detail_job j
        SET status = 'queued', available_at = now(), locked_by = NULL, locked_at = NULL,
            lease_expires_at = NULL, completed_at = NULL,
            last_error = 'Recovery: worker stopped before an immutable provider response was stored'
        WHERE j.enrichment_run_id::text = :run_id
          AND j.id::text IN :job_ids
          AND j.status = 'running'
          AND NOT EXISTS (
            SELECT 1 FROM product_detail_snapshot s
            WHERE s.product_detail_job_id = j.id
              AND s.attempt_number = j.attempt_count
          )
        RETURNING j.id::text
        """
    ).bindparams(bindparam("job_ids", expanding=True))
    async with database.engine.begin() as connection:
        updated = (
            await connection.execute(statement, {"run_id": run_id, "job_ids": job_ids})
        ).all()
        await connection.execute(
            text(
                """
                INSERT INTO audit_event (
                  organization_id, event_type, entity_type, entity_id, details
                ) VALUES (
                  '00000000-0000-0000-0000-000000000001'::uuid,
                  'product_detail_uncommitted_jobs_requeued',
                  'product_detail_enrichment_run', :run_id,
                  CAST(:details AS jsonb)
                )
                """
            ),
            {
                "run_id": run_id,
                "details": json.dumps(
                    {
                        "job_count": len(updated),
                        "reason": "no immutable raw provider response existed",
                    },
                    sort_keys=True,
                ),
            },
        )
    return len(updated)


async def _status(database: DatabaseProbe, run_id: str) -> dict[str, Any]:
    async with database.engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT r.status, r.max_credits, r.planned_credits, r.actual_credits,
                          count(*) FILTER (WHERE j.status = 'queued')::integer AS queued,
                          count(*) FILTER (WHERE j.status = 'running')::integer AS running,
                          count(*) FILTER (WHERE j.status = 'succeeded')::integer AS succeeded,
                          count(*) FILTER (WHERE j.status = 'failed')::integer AS failed
                        FROM product_detail_enrichment_run r
                        JOIN product_detail_job j ON j.enrichment_run_id = r.id
                        WHERE r.id::text = :run_id
                        GROUP BY r.id
                        """
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .one()
        )
    return {name: int(value) if name != "status" else str(value) for name, value in row.items()}


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.apply and _enabled(os.getenv("PRODUCT_DETAIL_ENRICHMENT_ENABLED")):
        raise RuntimeError("disable PRODUCT_DETAIL_ENRICHMENT_ENABLED before recovery")
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    repository_root = args.repository_root.resolve(strict=True)
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT") or None,
            region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or None,
            config=Config(
                s3={
                    "addressing_style": (
                        "path"
                        if _enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE", "true"))
                        else "virtual"
                    )
                }
            ),
        )
        bucket = os.environ["OBJECT_STORAGE_BUCKET"]
        catalog = ProductDetailCatalog.from_path(repository_root)
        jobs = await _uncommitted_jobs(database, args.run_id, catalog)
        evidence: list[RawEvidence] = []
        no_raw: list[ProductDetailJob] = []
        for job in jobs:
            raw = await asyncio.to_thread(_read_raw, client, bucket, job)
            if raw is None:
                no_raw.append(job)
            else:
                evidence.append(raw)

        dry_run = {
            "run_id": args.run_id,
            "mode": "apply" if args.apply else "dry_run",
            "uncommitted_jobs": len(jobs),
            "raw_responses": len(evidence),
            "raw_http_statuses": {
                str(status): sum(item.classification.http_status == status for item in evidence)
                for status in sorted({item.classification.http_status for item in evidence})
            },
            "recoverable_billable_credits": sum(
                item.job.credits_per_call for item in evidence if item.classification.billable
            ),
            "jobs_without_raw": len(no_raw),
            "running_without_raw": sum(job.status == "running" for job in no_raw),
        }
        if not args.apply:
            return {**dry_run, "status": await _status(database, args.run_id)}

        repository = PostgresProductDetailRepository(database.engine, repository_root)
        worker_id = "pdp-raw-recovery"
        recovered = 0
        recovered_credits = 0
        for item in evidence:
            adapter = MetricsCartProductDetailAdapter(item.job.endpoint)
            normalized = (
                adapter.normalize(item.payload, item.job.context)
                if item.classification.http_status == 200
                else None
            )
            if not await _acquire_recovery_lease(database, item.job, worker_id):
                continue
            artifact = ProductDetailRawArtifact(
                artifact_id=(
                    "pdp-raw-" + hashlib.sha256(item.storage_key.encode()).hexdigest()[:32]
                ),
                storage_uri=f"s3://{bucket}/{item.storage_key}",
                checksum=hashlib.sha256(item.compressed).hexdigest(),
                byte_size=len(item.compressed),
                metadata={
                    "provider": "metricscart",
                    "source_type": "pdp",
                    "retailer_id": item.job.retailer_id,
                    "endpoint_id": item.job.endpoint.endpoint_id,
                    "attempt": item.job.attempt_count,
                    "http_status": item.classification.http_status,
                    "request_method": item.job.endpoint.method,
                    "request_path": item.job.endpoint.path,
                    "request_parameter_names": sorted(item.job.context.parameters()),
                    "response_content_type": item.response_content_type,
                    "content_encoding": "gzip",
                    "body_checksum": hashlib.sha256(item.body).hexdigest(),
                    "recovered_from_immutable_raw": True,
                },
            )
            credits = item.job.credits_per_call if item.classification.billable else 0
            await repository.record_fetch(
                item.job,
                worker_id,
                ProductDetailFetchResult(
                    observed_at=item.observed_at,
                    http_status=item.classification.http_status,
                    billable=item.classification.billable,
                    credits=credits,
                    raw_artifact=artifact,
                    normalized=normalized,
                    failure_class=item.classification.failure_class,
                    failure_message=item.classification.failure_message,
                    should_retry=item.classification.should_retry,
                    retry_delay_seconds=item.classification.retry_delay_seconds,
                ),
                cache_ttl_seconds=int(os.getenv("PRODUCT_DETAIL_CACHE_TTL_SECONDS", "604800")),
            )
            recovered += 1
            recovered_credits += credits
        requeued = await _requeue_without_raw(database, args.run_id, no_raw)
        return {
            **dry_run,
            "recovered_responses": recovered,
            "recovered_billable_credits": recovered_credits,
            "requeued_without_raw": requeued,
            "status": await _status(database, args.run_id),
        }
    finally:
        await database.dispose()


def main() -> None:
    print(json.dumps(asyncio.run(_run(_arguments())), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
