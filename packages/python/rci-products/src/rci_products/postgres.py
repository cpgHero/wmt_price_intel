"""Postgres canonical-product store and durable Product Details queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_contracts import validate_instance
from rci_products.documents import (
    canonical_product_document,
    identity_from_normalized_document,
    normalization_document,
    serp_identity,
    snapshot_document,
)
from rci_products.models import (
    PRODUCT_DETAIL_NORMALIZER_VERSION,
    CanonicalProductRecord,
    EnqueueProductDetailResult,
    JsonObject,
    NormalizedProductDetail,
    ProductDetailEndpoint,
    ProductDetailFetchResult,
    ProductDetailJob,
    ProductDetailNormalizationCandidate,
    ProductDetailNormalizationRecord,
    ProductDetailRequestContext,
    ProductDetailRun,
    ProductDetailSnapshotRecord,
    ProductDetailStatus,
    sha256_document,
)
from rci_products.repository import ProductDetailBudgetExceeded, require_positive_budget

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _json(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _product(row: RowMapping) -> CanonicalProductRecord:
    return CanonicalProductRecord(
        id=str(row["id"]),
        canonical_product_id=str(row["canonical_product_id"]),
        retailer_id=str(row["retailer_id"]),
        retailer_product_id=str(row["retailer_product_id"]),
        identifiers=dict(row["identifiers"]),
        identity=dict(row["identity"]),
        identity_checksum=str(row["identity_checksum"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run(row: RowMapping) -> ProductDetailRun:
    return ProductDetailRun(
        id=str(row["id"]),
        max_credits=int(row["max_credits"]),
        planned_credits=int(row["planned_credits"]),
        actual_credits=int(row["actual_credits"]),
        status=str(row["status"]),
    )


def _endpoint_document(endpoint: ProductDetailEndpoint) -> JsonObject:
    return {
        "retailer_id": endpoint.retailer_id,
        "provider_retailer": endpoint.provider_retailer,
        "domain": endpoint.domain,
        "endpoint_id": endpoint.endpoint_id,
        "method": endpoint.method,
        "path": endpoint.path,
        "credits_per_successful_page": endpoint.credits_per_successful_page,
        "paid_calls_enabled": endpoint.paid_calls_enabled,
        "required_params": list(endpoint.required_params),
        "supported_params": list(endpoint.supported_params),
        "contract_version": endpoint.contract_version,
        "default_params": endpoint.defaults(),
        "fixed_params": endpoint.fixed(),
        "identity_param": endpoint.identity_param,
        "product_id_left_pad_width": endpoint.product_id_left_pad_width,
    }


def _endpoint(value: object) -> ProductDetailEndpoint:
    document = cast(JsonObject, value)
    return ProductDetailEndpoint(
        retailer_id=str(document["retailer_id"]),
        provider_retailer=str(document["provider_retailer"]),
        domain=str(document["domain"]),
        endpoint_id=str(document["endpoint_id"]),
        method=str(document["method"]),
        path=str(document["path"]),
        credits_per_successful_page=int(document["credits_per_successful_page"]),
        paid_calls_enabled=bool(document.get("paid_calls_enabled", True)),
        required_params=tuple(str(item) for item in document["required_params"]),
        supported_params=tuple(str(item) for item in document["supported_params"]),
        contract_version=str(document.get("contract_version", "1.0.0")),
        default_params=tuple(
            sorted(
                (str(name), str(parameter_value))
                for name, parameter_value in cast(
                    JsonObject, document.get("default_params", {})
                ).items()
            )
        ),
        fixed_params=tuple(
            sorted(
                (str(name), str(parameter_value))
                for name, parameter_value in cast(
                    JsonObject, document.get("fixed_params", {})
                ).items()
            )
        ),
        identity_param=(
            cast(
                Literal["product_id", "url"],
                str(document["identity_param"]),
            )
            if document.get("identity_param")
            else None
        ),
        product_id_left_pad_width=(
            int(document["product_id_left_pad_width"])
            if document.get("product_id_left_pad_width") is not None
            else None
        ),
    )


def _context_document(context: ProductDetailRequestContext) -> JsonObject:
    return {
        "product_id": context.product_id,
        "zipcode": context.zipcode,
        "store": context.store,
        "fulfillment_type": context.fulfillment_type,
        "shopping_type": context.shopping_type,
        "url": context.url,
    }


def _context(value: object) -> ProductDetailRequestContext:
    document = cast(JsonObject, value)
    return ProductDetailRequestContext(
        product_id=str(document["product_id"]),
        zipcode=str(document["zipcode"]) if document.get("zipcode") is not None else None,
        store=str(document["store"]) if document.get("store") is not None else None,
        fulfillment_type=(
            str(document["fulfillment_type"])
            if document.get("fulfillment_type") is not None
            else None
        ),
        shopping_type=(
            str(document["shopping_type"]) if document.get("shopping_type") is not None else None
        ),
        url=str(document["url"]) if document.get("url") is not None else None,
    )


def _job(row: RowMapping) -> ProductDetailJob:
    return ProductDetailJob(
        id=str(row["id"]),
        run_id=str(row["enrichment_run_id"]),
        canonical_product_db_id=str(row["canonical_product_id"]),
        canonical_product_id=str(row["canonical_product_stable_id"]),
        retailer_id=str(row["retailer_id"]),
        endpoint=_endpoint(row["endpoint"]),
        context=_context(row["request_context"]),
        request_checksum=str(row["request_checksum"]),
        credits_per_call=int(row["credits_per_call"]),
        status=cast(ProductDetailStatus, str(row["status"])),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
    )


def _snapshot(row: RowMapping) -> ProductDetailSnapshotRecord:
    return ProductDetailSnapshotRecord(
        id=str(row["id"]),
        canonical_product_db_id=str(row["canonical_product_id"]),
        canonical_product_id=str(row["canonical_product_stable_id"]),
        request_checksum=str(row["request_checksum"]),
        document=dict(row["document"]),
        cache_expires_at=row["cache_expires_at"],
    )


def _normalization_candidate(row: RowMapping) -> ProductDetailNormalizationCandidate:
    return ProductDetailNormalizationCandidate(
        id=str(row["id"]),
        snapshot_id=str(row["product_detail_snapshot_id"]),
        normalizer_version=str(row["normalizer_version"]),
        canonical_product_db_id=str(row["canonical_product_id"]),
        canonical_product_id=str(row["canonical_product_stable_id"]),
        retailer_id=str(row["retailer_id"]),
        raw_storage_uri=str(row["raw_storage_uri"]),
        raw_checksum=str(row["source_raw_checksum"]),
        endpoint=_endpoint(row["endpoint"]),
        context=_context(row["request_context"]),
        attempt_count=int(row["attempt_count"]),
    )


class PostgresProductDetailRepository:
    def __init__(
        self,
        engine: AsyncEngine,
        repository_root: Path,
        *,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
    ) -> None:
        self._engine = engine
        self._root = repository_root
        self._organization_id = organization_id
        self._seeded_normalizer_versions: set[str] = set()

    async def upsert_serp_product(
        self,
        *,
        retailer_id: str,
        retailer_product_id: str,
        name: str,
        brand: str | None,
        url: str,
        image_primary: str | None,
        identifiers: JsonObject,
        context: JsonObject,
    ) -> CanonicalProductRecord:
        identity, checksum = serp_identity(
            name=name,
            brand=brand,
            url=url,
            image_primary=image_primary,
        )
        all_identifiers = {"retailer_product_id": retailer_product_id, **identifiers}
        context_checksum = sha256_document(context)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO canonical_product (
                              organization_id, canonical_product_id, retailer_id,
                              retailer_product_id, identifiers, identity, identity_checksum
                            ) VALUES (
                              CAST(:organization_id AS uuid), :stable_id, :retailer_id,
                              :retailer_product_id, CAST(:identifiers AS jsonb),
                              CAST(:identity AS jsonb), :identity_checksum
                            )
                            ON CONFLICT ON CONSTRAINT canonical_product_retailer_product_uq
                            DO UPDATE SET identifiers = canonical_product.identifiers
                              || EXCLUDED.identifiers
                            RETURNING *
                            """
                        ),
                        {
                            "organization_id": self._organization_id,
                            "stable_id": f"{retailer_id}:{retailer_product_id}",
                            "retailer_id": retailer_id,
                            "retailer_product_id": retailer_product_id,
                            "identifiers": _json(all_identifiers),
                            "identity": _json(identity),
                            "identity_checksum": checksum,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO canonical_product_context (
                      canonical_product_id, context_checksum, context
                    ) VALUES (
                      CAST(:product_id AS uuid), :checksum, CAST(:context AS jsonb)
                    )
                    ON CONFLICT ON CONSTRAINT canonical_product_context_uq DO NOTHING
                    """
                ),
                {
                    "product_id": str(row["id"]),
                    "checksum": context_checksum,
                    "context": _json(context),
                },
            )
            return _product(row)

    async def create_run(
        self,
        *,
        max_credits: int,
        active: bool = True,
    ) -> ProductDetailRun:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_detail_enrichment_run (
                              organization_id, max_credits, status
                            ) VALUES (CAST(:organization_id AS uuid), :max_credits, :status)
                            RETURNING *
                            """
                        ),
                        {
                            "organization_id": self._organization_id,
                            "max_credits": require_positive_budget(max_credits),
                            "status": "active" if active else "planning",
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "product_detail_run_created",
                "product_detail_enrichment_run",
                str(row["id"]),
                {"max_credits": int(row["max_credits"])},
            )
            return _run(row)

    async def enqueue(
        self,
        run_id: str,
        product: CanonicalProductRecord,
        endpoint: ProductDetailEndpoint,
        context: ProductDetailRequestContext,
        *,
        max_attempts: int = 3,
    ) -> EnqueueProductDetailResult:
        if not 1 <= max_attempts <= 10:
            raise ValueError("Product Details max_attempts must be between 1 and 10")
        checksum = context.checksum(endpoint)
        async with self._engine.begin() as connection:
            run_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM product_detail_enrichment_run "
                            "WHERE id::text = :run_id FOR UPDATE"
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .one()
            )
            if str(run_row["status"]) not in {"planning", "active"}:
                raise ValueError("Product Details run is not open for planning")
            cached = (
                await connection.execute(
                    text(
                        """
                            SELECT s.id::text
                            FROM product_detail_snapshot s
                            WHERE s.canonical_product_id::text = :product_id
                              AND s.request_checksum = :checksum
                              AND s.normalized
                              AND s.http_status = 200
                              AND s.cache_expires_at > now()
                            ORDER BY s.observed_at DESC, s.id DESC LIMIT 1
                            """
                    ),
                    {"product_id": product.id, "checksum": checksum},
                )
            ).scalar_one_or_none()
            if cached is not None:
                return EnqueueProductDetailResult(
                    job_id=None,
                    snapshot_id=str(cached),
                    request_checksum=checksum,
                    cached=True,
                    created=False,
                )
            existing = (
                await connection.execute(
                    text(
                        """
                            SELECT id::text FROM product_detail_job
                            WHERE enrichment_run_id::text = :run_id
                              AND request_checksum = :checksum
                            """
                    ),
                    {"run_id": run_id, "checksum": checksum},
                )
            ).scalar_one_or_none()
            if existing is not None:
                return EnqueueProductDetailResult(
                    job_id=str(existing),
                    snapshot_id=None,
                    request_checksum=checksum,
                    cached=False,
                    created=False,
                )
            planned = int(run_row["planned_credits"]) + endpoint.credits_per_successful_page
            if planned > int(run_row["max_credits"]):
                raise ProductDetailBudgetExceeded(
                    f"Product Details credit ceiling {run_row['max_credits']} would be exceeded"
                )
            await connection.execute(
                text(
                    "UPDATE product_detail_enrichment_run SET planned_credits = :planned "
                    "WHERE id::text = :run_id"
                ),
                {"planned": planned, "run_id": run_id},
            )
            job_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_detail_job (
                              enrichment_run_id, canonical_product_id, retailer_id,
                              endpoint, request_context, request_checksum, credits_per_call,
                              max_attempts
                            ) VALUES (
                              CAST(:run_id AS uuid), CAST(:product_id AS uuid), :retailer_id,
                              CAST(:endpoint AS jsonb), CAST(:context AS jsonb), :checksum,
                              :credits, :max_attempts
                            ) RETURNING id::text
                            """
                        ),
                        {
                            "run_id": run_id,
                            "product_id": product.id,
                            "retailer_id": product.retailer_id,
                            "endpoint": _json(_endpoint_document(endpoint)),
                            "context": _json(_context_document(context)),
                            "checksum": checksum,
                            "credits": endpoint.credits_per_successful_page,
                            "max_attempts": max_attempts,
                        },
                    )
                ).scalar_one()
            )
            return EnqueueProductDetailResult(
                job_id=job_id,
                snapshot_id=None,
                request_checksum=checksum,
                cached=False,
                created=True,
            )

    async def has_fresh_cache(
        self,
        *,
        retailer_id: str,
        retailer_product_id: str,
        endpoint: ProductDetailEndpoint,
        context: ProductDetailRequestContext,
    ) -> bool:
        checksum = context.checksum(endpoint)
        async with self._engine.connect() as connection:
            cached = (
                await connection.execute(
                    text(
                        """
                        SELECT s.id::text
                        FROM canonical_product p
                        JOIN product_detail_snapshot s ON s.canonical_product_id = p.id
                        WHERE p.organization_id::text = :organization_id
                          AND p.retailer_id = :retailer_id
                          AND p.retailer_product_id = :retailer_product_id
                          AND s.request_checksum = :checksum
                          AND s.normalized
                          AND s.http_status = 200
                          AND s.cache_expires_at > now()
                        ORDER BY s.observed_at DESC, s.id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "organization_id": self._organization_id,
                        "retailer_id": retailer_id,
                        "retailer_product_id": retailer_product_id,
                        "checksum": checksum,
                    },
                )
            ).scalar_one_or_none()
        return cached is not None

    async def claim(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: int,
    ) -> list[ProductDetailJob]:
        if limit < 1 or lease_seconds < 1:
            raise ValueError("Product Details claim limits must be positive")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_job j
                    SET status = 'failed', last_error = 'Lease expired after maximum attempts',
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        completed_at = now()
                    FROM product_detail_enrichment_run r
                    WHERE r.id = j.enrichment_run_id AND r.status = 'active'
                      AND j.status = 'running' AND j.lease_expires_at <= now()
                      AND j.attempt_count >= j.max_attempts
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_job j
                    SET status = 'canceled', locked_by = NULL, locked_at = NULL,
                        lease_expires_at = NULL, completed_at = now()
                    FROM product_detail_enrichment_run r
                    WHERE r.id = j.enrichment_run_id AND r.status = 'canceled'
                      AND j.status = 'running' AND j.lease_expires_at <= now()
                    """
                )
            )
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH ranked AS (
                              SELECT j.id, j.retailer_id, j.priority, j.created_at,
                                row_number() OVER (
                                  PARTITION BY j.retailer_id, j.priority
                                  ORDER BY j.created_at, j.id
                                ) AS retailer_rank
                              FROM product_detail_job j
                              JOIN product_detail_enrichment_run r
                                ON r.id = j.enrichment_run_id
                              WHERE r.status = 'active' AND (
                                (j.status = 'queued' AND j.available_at <= now()) OR
                                (j.status = 'running' AND j.lease_expires_at <= now())
                              ) AND j.attempt_count < j.max_attempts
                            ), candidates AS (
                              SELECT j.id
                              FROM product_detail_job j
                              JOIN ranked candidate ON candidate.id = j.id
                              WHERE (
                                (j.status = 'queued' AND j.available_at <= now()) OR
                                (j.status = 'running' AND j.lease_expires_at <= now())
                              ) AND j.attempt_count < j.max_attempts
                              ORDER BY candidate.priority, candidate.retailer_rank,
                                candidate.created_at, candidate.id
                              FOR UPDATE OF j SKIP LOCKED
                              LIMIT :limit
                            ), updated AS (
                              UPDATE product_detail_job j
                              SET status = 'running', locked_by = :worker_id, locked_at = now(),
                                  lease_expires_at = now()
                                    + make_interval(secs => :lease_seconds),
                                  attempt_count = j.attempt_count + 1
                              FROM candidates c WHERE j.id = c.id RETURNING j.*
                            )
                            SELECT u.*, p.canonical_product_id AS canonical_product_stable_id
                            FROM updated u JOIN canonical_product p
                              ON p.id = u.canonical_product_id
                            """
                        ),
                        {
                            "worker_id": worker_id,
                            "limit": limit,
                            "lease_seconds": lease_seconds,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [_job(row) for row in rows]

    async def record_fetch(
        self,
        job: ProductDetailJob,
        worker_id: str,
        result: ProductDetailFetchResult,
        *,
        cache_ttl_seconds: int,
    ) -> ProductDetailSnapshotRecord:
        if cache_ttl_seconds < 1:
            raise ValueError("Product Details cache TTL must be positive")
        snapshot_id = str(uuid4())
        document = snapshot_document(job, result, snapshot_id=snapshot_id)
        validate_instance(
            self._root,
            "product-detail-snapshot.schema.json",
            document,
            label=f"snapshot:{snapshot_id}",
        )
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT j.*, p.canonical_product_id AS canonical_product_stable_id,
                              p.identifiers AS product_identifiers, p.identity AS product_identity,
                              j.lease_expires_at > now() AS lease_valid
                            FROM product_detail_job j JOIN canonical_product p
                              ON p.id = j.canonical_product_id
                            WHERE j.id::text = :job_id FOR UPDATE OF j
                            """
                        ),
                        {"job_id": job.id},
                    )
                )
                .mappings()
                .one()
            )
            if (
                str(row["status"]) != "running"
                or str(row["locked_by"]) != worker_id
                or not bool(row["lease_valid"])
                or int(row["attempt_count"]) != job.attempt_count
            ):
                raise ValueError("Product Details job lease is not owned by this worker")
            cache_expires_at = (
                datetime.now(UTC) + timedelta(seconds=cache_ttl_seconds)
                if result.normalized is not None
                else None
            )
            snapshot_row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_detail_snapshot (
                              id, canonical_product_id, product_detail_job_id, attempt_number,
                              request_checksum, document, http_status, billable_credits,
                              raw_storage_uri, raw_checksum, normalized, observed_at,
                              cache_expires_at
                            ) VALUES (
                              CAST(:snapshot_id AS uuid), CAST(:product_id AS uuid),
                              CAST(:job_id AS uuid), :attempt_number, :request_checksum,
                              CAST(:document AS jsonb), :http_status, :credits,
                              :raw_storage_uri, :raw_checksum, :normalized, :observed_at,
                              :cache_expires_at
                            ) RETURNING *, :stable_id AS canonical_product_stable_id
                            """
                        ),
                        {
                            "snapshot_id": snapshot_id,
                            "product_id": job.canonical_product_db_id,
                            "job_id": job.id,
                            "attempt_number": job.attempt_count,
                            "request_checksum": job.request_checksum,
                            "document": _json(document),
                            "http_status": result.http_status,
                            "credits": result.credits,
                            "raw_storage_uri": result.raw_artifact.storage_uri,
                            "raw_checksum": result.raw_artifact.checksum,
                            "normalized": result.normalized is not None,
                            "observed_at": result.observed_at,
                            "cache_expires_at": cache_expires_at,
                            "stable_id": job.canonical_product_id,
                        },
                    )
                )
                .mappings()
                .one()
            )
            if result.normalized is not None:
                candidate = ProductDetailNormalizationCandidate(
                    id=str(uuid4()),
                    snapshot_id=str(snapshot_row["id"]),
                    normalizer_version=PRODUCT_DETAIL_NORMALIZER_VERSION,
                    canonical_product_db_id=job.canonical_product_db_id,
                    canonical_product_id=job.canonical_product_id,
                    retailer_id=job.retailer_id,
                    raw_storage_uri=result.raw_artifact.storage_uri,
                    raw_checksum=result.raw_artifact.checksum,
                    endpoint=job.endpoint,
                    context=job.context,
                    attempt_count=job.attempt_count,
                )
                normalized_document = normalization_document(candidate, result.normalized)
                validate_instance(
                    self._root,
                    "product-detail-normalization.schema.json",
                    normalized_document,
                    label=f"product-detail-normalization:{candidate.snapshot_id}",
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO product_detail_normalization (
                          product_detail_snapshot_id, normalizer_version, status,
                          attempt_count, document, document_checksum,
                          source_raw_checksum, completed_at
                        ) VALUES (
                          CAST(:snapshot_id AS uuid), :normalizer_version, 'succeeded',
                          1, CAST(:document AS jsonb), :document_checksum,
                          :source_raw_checksum, now()
                        ) ON CONFLICT ON CONSTRAINT
                          product_detail_normalization_snapshot_version_uq DO NOTHING
                        """
                    ),
                    {
                        "snapshot_id": candidate.snapshot_id,
                        "normalizer_version": PRODUCT_DETAIL_NORMALIZER_VERSION,
                        "document": _json(normalized_document),
                        "document_checksum": sha256_document(normalized_document),
                        "source_raw_checksum": candidate.raw_checksum,
                    },
                )
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_enrichment_run
                    SET actual_credits = actual_credits + :credits
                    WHERE id::text = :run_id
                    """
                ),
                {"credits": result.credits, "run_id": job.run_id},
            )
            next_status: ProductDetailStatus
            last_error: str | None
            if result.normalized is not None:
                current_identity = dict(row["product_identity"])
                pdp_identity = result.normalized.identity_document()
                current_identity.update(
                    {key: value for key, value in pdp_identity.items() if value is not None}
                )
                identifiers = {
                    **dict(row["product_identifiers"]),
                    **result.normalized.identifiers,
                }
                await connection.execute(
                    text(
                        """
                        UPDATE canonical_product SET identifiers = CAST(:identifiers AS jsonb),
                          identity = CAST(:identity AS jsonb), identity_checksum = :checksum,
                          updated_at = now()
                        WHERE id::text = :product_id
                        """
                    ),
                    {
                        "identifiers": _json(identifiers),
                        "identity": _json(current_identity),
                        "checksum": sha256_document(current_identity),
                        "product_id": job.canonical_product_db_id,
                    },
                )
                next_status, last_error = "succeeded", None
            elif result.should_retry and job.attempt_count < job.max_attempts:
                next_status = "queued"
                last_error = result.failure_message
            else:
                next_status = "failed"
                last_error = result.failure_message
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_job
                    SET status = :status,
                        available_at = CASE WHEN :status = 'queued'
                          THEN now() + make_interval(secs => :retry_delay)
                          ELSE available_at END,
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        last_http_status = :http_status, last_error = :last_error,
                        billable_credits = billable_credits + :credits,
                        completed_at = CASE WHEN :status IN ('succeeded', 'failed')
                          THEN now() ELSE NULL END
                    WHERE id::text = :job_id
                    """
                ),
                {
                    "status": next_status,
                    "retry_delay": max(result.retry_delay_seconds, 0),
                    "http_status": result.http_status,
                    "last_error": last_error,
                    "credits": result.credits,
                    "job_id": job.id,
                },
            )
            await self._reconcile_run(connection, job.run_id)
            await self._audit(
                connection,
                "product_detail_snapshot_recorded",
                "product_detail_snapshot",
                snapshot_id,
                {
                    "retailer_id": job.retailer_id,
                    "http_status": result.http_status,
                    "billable_credits": result.credits,
                    "normalized": result.normalized is not None,
                },
            )
            return _snapshot(snapshot_row)

    async def fail_transport(
        self,
        job: ProductDetailJob,
        worker_id: str,
        message: str,
        *,
        retry_delay_seconds: float,
    ) -> None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT j.*, r.status AS run_status,
                              j.lease_expires_at > now() AS lease_valid
                            FROM product_detail_job j JOIN product_detail_enrichment_run r
                              ON r.id = j.enrichment_run_id
                            WHERE j.id::text = :job_id FOR UPDATE OF j
                            """
                        ),
                        {"job_id": job.id},
                    )
                )
                .mappings()
                .one()
            )
            if (
                str(row["status"]) != "running"
                or str(row["locked_by"]) != worker_id
                or not bool(row["lease_valid"])
            ):
                raise ValueError("Product Details job lease is not owned by this worker")
            if str(row["run_status"]) == "canceled":
                next_status: ProductDetailStatus = "canceled"
            elif job.attempt_count < job.max_attempts:
                next_status = "queued"
            else:
                next_status = "failed"
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_job
                    SET status = :status,
                        available_at = now() + make_interval(secs => :retry_delay),
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        last_error = :message,
                        completed_at = CASE WHEN :status IN ('failed', 'canceled')
                          THEN now() ELSE NULL END
                    WHERE id::text = :job_id
                    """
                ),
                {
                    "status": next_status,
                    "retry_delay": max(retry_delay_seconds, 0),
                    "message": message,
                    "job_id": job.id,
                },
            )
            await self._reconcile_run(connection, job.run_id)

    async def extend_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE product_detail_job
                    SET lease_expires_at = now() + make_interval(secs => :lease_seconds)
                    WHERE id::text = :job_id AND status = 'running'
                      AND locked_by = :worker_id AND lease_expires_at > now()
                    RETURNING id
                    """
                ),
                {
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "lease_seconds": lease_seconds,
                },
            )
            return result.first() is not None

    async def cancel_run(self, run_id: str) -> int:
        async with self._engine.begin() as connection:
            run = (
                await connection.execute(
                    text(
                        """
                            UPDATE product_detail_enrichment_run
                            SET status = 'canceled', cancel_requested_at = now(),
                                completed_at = now()
                            WHERE id::text = :run_id AND status IN ('planning', 'active')
                            RETURNING id
                            """
                    ),
                    {"run_id": run_id},
                )
            ).first()
            if run is None:
                return 0
            result = await connection.execute(
                text(
                    """
                    UPDATE product_detail_job
                    SET status = 'canceled', completed_at = now()
                    WHERE enrichment_run_id::text = :run_id AND status = 'queued'
                    RETURNING id
                    """
                ),
                {"run_id": run_id},
            )
            canceled = len(result.all())
            await self._audit(
                connection,
                "product_detail_run_canceled",
                "product_detail_enrichment_run",
                run_id,
                {"queued_jobs_canceled": canceled},
            )
            return canceled

    async def get_snapshot(self, snapshot_id: str) -> ProductDetailSnapshotRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT s.*, p.canonical_product_id AS canonical_product_stable_id
                            FROM product_detail_snapshot s JOIN canonical_product p
                              ON p.id = s.canonical_product_id
                            WHERE s.id::text = :snapshot_id
                            """
                        ),
                        {"snapshot_id": snapshot_id},
                    )
                )
                .mappings()
                .first()
            )
            return _snapshot(row) if row is not None else None

    async def product_document(self, canonical_product_db_id: str) -> JsonObject:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM canonical_product WHERE id::text = :product_id"),
                        {"product_id": canonical_product_db_id},
                    )
                )
                .mappings()
                .one()
            )
            contexts = [
                dict(value)
                for value in (
                    await connection.execute(
                        text(
                            """
                            SELECT context FROM canonical_product_context
                            WHERE canonical_product_id::text = :product_id
                            ORDER BY created_at, id
                            """
                        ),
                        {"product_id": canonical_product_db_id},
                    )
                ).scalars()
            ]
            snapshot_ids = [
                str(value)
                for value in (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text FROM product_detail_snapshot
                            WHERE canonical_product_id::text = :product_id
                            ORDER BY observed_at, id
                            """
                        ),
                        {"product_id": canonical_product_db_id},
                    )
                ).scalars()
            ]
        document = canonical_product_document(
            _product(row),
            source_contexts=contexts,
            snapshot_ids=snapshot_ids,
        )
        validate_instance(
            self._root,
            "canonical-product.schema.json",
            document,
            label=f"canonical-product:{document['canonical_product_id']}",
        )
        return document

    async def claim_normalizations(
        self,
        worker_id: str,
        *,
        normalizer_version: str,
        limit: int,
        lease_seconds: int,
    ) -> list[ProductDetailNormalizationCandidate]:
        if not worker_id or not normalizer_version:
            raise ValueError("normalization worker and version are required")
        if limit < 1 or lease_seconds < 1:
            raise ValueError("normalization claim limit and lease must be positive")
        seed_version = normalizer_version not in self._seeded_normalizer_versions
        async with self._engine.begin() as connection:
            if seed_version:
                await connection.execute(
                    text(
                        """
                        INSERT INTO product_detail_normalization (
                          product_detail_snapshot_id, normalizer_version,
                          source_raw_checksum
                        )
                        SELECT s.id, :normalizer_version, s.raw_checksum
                        FROM product_detail_snapshot s
                        WHERE s.normalized AND s.http_status = 200
                        ON CONFLICT ON CONSTRAINT
                          product_detail_normalization_snapshot_version_uq DO NOTHING
                        """
                    ),
                    {"normalizer_version": normalizer_version},
                )
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_normalization
                    SET status = 'queued', locked_by = NULL, locked_at = NULL,
                        lease_expires_at = NULL, available_at = now(),
                        last_error = COALESCE(last_error, 'expired normalization lease')
                    WHERE normalizer_version = :normalizer_version
                      AND status = 'running' AND lease_expires_at <= now()
                      AND attempt_count < max_attempts
                    """
                ),
                {"normalizer_version": normalizer_version},
            )
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH candidates AS (
                              SELECT id FROM product_detail_normalization
                              WHERE normalizer_version = :normalizer_version
                                AND status = 'queued' AND available_at <= now()
                                AND attempt_count < max_attempts
                              ORDER BY available_at, created_at, id
                              FOR UPDATE SKIP LOCKED LIMIT :limit
                            ), updated AS (
                              UPDATE product_detail_normalization n
                              SET status = 'running', locked_by = :worker_id,
                                locked_at = now(),
                                lease_expires_at = now() + make_interval(secs => :lease_seconds),
                                attempt_count = n.attempt_count + 1
                              FROM candidates c WHERE n.id = c.id
                              RETURNING n.*
                            )
                            SELECT u.*, s.canonical_product_id, s.raw_storage_uri,
                              cp.canonical_product_id AS canonical_product_stable_id,
                              j.retailer_id, j.endpoint, j.request_context
                            FROM updated u
                            JOIN product_detail_snapshot s
                              ON s.id = u.product_detail_snapshot_id
                            JOIN product_detail_job j ON j.id = s.product_detail_job_id
                            JOIN canonical_product cp ON cp.id = s.canonical_product_id
                            ORDER BY u.created_at, u.id
                            """
                        ),
                        {
                            "normalizer_version": normalizer_version,
                            "limit": limit,
                            "worker_id": worker_id,
                            "lease_seconds": lease_seconds,
                        },
                    )
                )
                .mappings()
                .all()
            )
        if seed_version:
            self._seeded_normalizer_versions.add(normalizer_version)
        return [_normalization_candidate(row) for row in rows]

    async def record_normalization(
        self,
        candidate: ProductDetailNormalizationCandidate,
        worker_id: str,
        normalized: NormalizedProductDetail,
    ) -> ProductDetailNormalizationRecord:
        document = normalization_document(candidate, normalized)
        validate_instance(
            self._root,
            "product-detail-normalization.schema.json",
            document,
            label=f"product-detail-normalization:{candidate.snapshot_id}",
        )
        checksum = sha256_document(document)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT *, lease_expires_at > now() AS lease_valid
                            FROM product_detail_normalization
                            WHERE id::text = :normalization_id FOR UPDATE
                            """
                        ),
                        {"normalization_id": candidate.id},
                    )
                )
                .mappings()
                .one()
            )
            if (
                str(row["status"]) != "running"
                or str(row["locked_by"]) != worker_id
                or not bool(row["lease_valid"])
                or str(row["normalizer_version"]) != candidate.normalizer_version
            ):
                raise ValueError("Product Details normalization lease is not owned by this worker")
            updated = (
                (
                    await connection.execute(
                        text(
                            """
                            UPDATE product_detail_normalization
                            SET status = 'succeeded', document = CAST(:document AS jsonb),
                              document_checksum = :checksum, locked_by = NULL,
                              locked_at = NULL, lease_expires_at = NULL,
                              last_error = NULL, completed_at = now()
                            WHERE id::text = :normalization_id RETURNING *
                            """
                        ),
                        {
                            "document": _json(document),
                            "checksum": checksum,
                            "normalization_id": candidate.id,
                        },
                    )
                )
                .mappings()
                .one()
            )
            # Serialize canonical identity refreshes for multiple historical snapshots of
            # the same product. The latest-normalization query must run after this lock so
            # a waiting transaction sees the normalization committed by the prior writer.
            product = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT identity, identifiers FROM canonical_product
                            WHERE id::text = :product_id FOR UPDATE
                            """
                        ),
                        {"product_id": candidate.canonical_product_db_id},
                    )
                )
                .mappings()
                .one()
            )
            latest = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT n.document->'normalized' AS normalized
                            FROM product_detail_normalization n
                            JOIN product_detail_snapshot s
                              ON s.id = n.product_detail_snapshot_id
                            WHERE s.canonical_product_id::text = :product_id
                              AND n.status = 'succeeded'
                              AND n.normalizer_version = :normalizer_version
                            ORDER BY s.observed_at DESC, n.completed_at DESC, n.id DESC
                            LIMIT 1
                            """
                        ),
                        {
                            "product_id": candidate.canonical_product_db_id,
                            "normalizer_version": candidate.normalizer_version,
                        },
                    )
                )
                .mappings()
                .one()
            )
            latest_normalized = dict(latest["normalized"])
            current_identity = dict(product["identity"])
            current_identity.update(
                {
                    key: value
                    for key, value in identity_from_normalized_document(latest_normalized).items()
                    if value is not None
                }
            )
            latest_identifiers = latest_normalized.get("identifiers", {})
            identifiers = {
                **dict(product["identifiers"]),
                **(dict(latest_identifiers) if isinstance(latest_identifiers, dict) else {}),
            }
            await connection.execute(
                text(
                    """
                    UPDATE canonical_product SET identifiers = CAST(:identifiers AS jsonb),
                      identity = CAST(:identity AS jsonb), identity_checksum = :checksum,
                      updated_at = now()
                    WHERE id::text = :product_id
                    """
                ),
                {
                    "identifiers": _json(identifiers),
                    "identity": _json(current_identity),
                    "checksum": sha256_document(current_identity),
                    "product_id": candidate.canonical_product_db_id,
                },
            )
            await self._audit(
                connection,
                "product_detail_renormalized",
                "product_detail_normalization",
                candidate.id,
                {
                    "snapshot_id": candidate.snapshot_id,
                    "retailer_id": candidate.retailer_id,
                    "normalizer_version": candidate.normalizer_version,
                    "source_raw_checksum": candidate.raw_checksum,
                    "unmapped_source_fields": list(normalized.unmapped_source_fields),
                },
            )
        return ProductDetailNormalizationRecord(
            id=str(updated["id"]),
            snapshot_id=candidate.snapshot_id,
            normalizer_version=candidate.normalizer_version,
            document=document,
            document_checksum=checksum,
        )

    async def fail_normalization(
        self,
        candidate: ProductDetailNormalizationCandidate,
        worker_id: str,
        message: str,
        *,
        retry_delay_seconds: float,
    ) -> None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT *, lease_expires_at > now() AS lease_valid
                            FROM product_detail_normalization
                            WHERE id::text = :normalization_id FOR UPDATE
                            """
                        ),
                        {"normalization_id": candidate.id},
                    )
                )
                .mappings()
                .one()
            )
            if (
                str(row["status"]) != "running"
                or str(row["locked_by"]) != worker_id
                or not bool(row["lease_valid"])
            ):
                raise ValueError("Product Details normalization lease is not owned by this worker")
            next_status = (
                "queued" if int(row["attempt_count"]) < int(row["max_attempts"]) else "failed"
            )
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_normalization
                    SET status = :status,
                      available_at = now() + make_interval(secs => :retry_delay),
                      locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                      last_error = :last_error,
                      completed_at = CASE WHEN :status = 'failed' THEN now() ELSE NULL END
                    WHERE id::text = :normalization_id
                    """
                ),
                {
                    "status": next_status,
                    "retry_delay": max(retry_delay_seconds, 0),
                    "last_error": message[:2000],
                    "normalization_id": candidate.id,
                },
            )

    async def normalization_audit(self, normalizer_version: str) -> JsonObject:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT j.retailer_id, n.status, count(*)::integer AS count,
                              count(*) FILTER (
                                WHERE NULLIF(BTRIM(n.document #>> '{normalized,seller}'), '')
                                  IS NOT NULL
                              )::integer AS seller_count,
                              count(*) FILTER (
                                WHERE NULLIF(BTRIM(n.document #>> '{normalized,brand}'), '')
                                  IS NOT NULL
                              )::integer AS brand_count,
                              count(*) FILTER (
                                WHERE NULLIF(BTRIM(
                                  n.document #>> '{normalized,description_full}'
                                ), '') IS NOT NULL OR NULLIF(BTRIM(
                                    n.document #>> '{normalized,description_short}'
                                  ), '') IS NOT NULL
                              )::integer AS description_count,
                              count(*) FILTER (
                                WHERE jsonb_typeof(
                                  n.document #> '{normalized,identifiers}'
                                ) = 'object' AND n.document #> '{normalized,identifiers}'
                                  <> '{}'::jsonb
                              )::integer AS identifier_count,
                              count(*) FILTER (
                                WHERE jsonb_typeof(
                                  n.document #> '{normalized,specification}'
                                ) = 'object' AND n.document #> '{normalized,specification}'
                                  <> '{}'::jsonb
                              )::integer AS specification_count,
                              count(*) FILTER (
                                WHERE jsonb_typeof(
                                  n.document #> '{normalized,physical_properties}'
                                ) = 'object' AND n.document #> '{normalized,physical_properties}'
                                  <> '{}'::jsonb
                              )::integer AS physical_properties_count,
                              count(*) FILTER (
                                WHERE NULLIF(BTRIM(
                                  n.document #>> '{normalized,media,image_primary}'
                                ), '') IS NOT NULL
                              )::integer AS primary_image_count,
                              count(*) FILTER (
                                WHERE jsonb_typeof(
                                  n.document #> '{normalized,media,images}'
                                ) = 'array' AND jsonb_array_length(
                                  n.document #> '{normalized,media,images}'
                                ) > 1
                              )::integer AS multi_image_count
                            FROM product_detail_normalization n
                            JOIN product_detail_snapshot s
                              ON s.id = n.product_detail_snapshot_id
                            JOIN product_detail_job j ON j.id = s.product_detail_job_id
                            WHERE n.normalizer_version = :normalizer_version
                            GROUP BY j.retailer_id, n.status
                            ORDER BY j.retailer_id, n.status
                            """
                        ),
                        {"normalizer_version": normalizer_version},
                    )
                )
                .mappings()
                .all()
            )
            unknown_rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT fields.field, count(*)::integer AS count
                            FROM product_detail_normalization n
                            CROSS JOIN LATERAL jsonb_array_elements_text(
                              COALESCE(
                                n.document #> '{normalized,unmapped_source_fields}',
                                '[]'::jsonb
                              )
                            ) AS fields(field)
                            WHERE n.normalizer_version = :normalizer_version
                              AND n.status = 'succeeded'
                            GROUP BY fields.field ORDER BY count(*) DESC, fields.field
                            """
                        ),
                        {"normalizer_version": normalizer_version},
                    )
                )
                .mappings()
                .all()
            )
        return {
            "normalizer_version": normalizer_version,
            "retailers": [dict(row) for row in rows],
            "unmapped_source_fields": [dict(row) for row in unknown_rows],
        }

    async def publication_highlights(
        self,
        source_artifact_ids: list[str],
        *,
        limit: int = 8,
        per_retailer_limit: int = 16,
    ) -> list[JsonObject]:
        if not source_artifact_ids or limit < 1 or per_retailer_limit < 1:
            return []
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH matched AS (
                              SELECT cp.id, cp.canonical_product_id, cp.retailer_id,
                                cp.identity, cp.updated_at,
                                count(DISTINCT c.id)::integer AS source_context_count
                              FROM canonical_product cp
                              JOIN canonical_product_context c
                                ON c.canonical_product_id = cp.id
                              WHERE c.context->>'source_artifact_id' = ANY(
                                CAST(:source_artifact_ids AS text[])
                              )
                              GROUP BY cp.id
                            ), enriched AS (
                              SELECT matched.*, snapshot.document AS snapshot_document,
                                snapshot.normalization_document,
                                row_number() OVER (
                                  PARTITION BY matched.retailer_id
                                  ORDER BY (snapshot.id IS NOT NULL) DESC,
                                    matched.source_context_count DESC,
                                    matched.updated_at DESC, matched.id
                                ) AS retailer_rank
                              FROM matched
                              LEFT JOIN LATERAL (
                                SELECT s.id, s.document,
                                  normalization.document->'normalized' AS normalization_document
                                FROM product_detail_snapshot s
                                LEFT JOIN LATERAL (
                                  SELECT n.document
                                  FROM product_detail_normalization n
                                  WHERE n.product_detail_snapshot_id = s.id
                                    AND n.normalizer_version = :normalizer_version
                                    AND n.status = 'succeeded'
                                  ORDER BY n.completed_at DESC, n.id DESC LIMIT 1
                                ) normalization ON true
                                WHERE s.canonical_product_id = matched.id
                                  AND s.normalized AND s.http_status = 200
                                ORDER BY s.observed_at DESC, s.id DESC LIMIT 1
                              ) snapshot ON true
                            )
                            SELECT * FROM enriched
                            WHERE retailer_rank <= :per_retailer_limit
                            ORDER BY (snapshot_document IS NOT NULL) DESC,
                              source_context_count DESC, retailer_id, canonical_product_id
                            LIMIT :limit
                            """
                        ),
                        {
                            "source_artifact_ids": source_artifact_ids,
                            "limit": limit,
                            "per_retailer_limit": per_retailer_limit,
                            "normalizer_version": PRODUCT_DETAIL_NORMALIZER_VERSION,
                        },
                    )
                )
                .mappings()
                .all()
            )
        highlights: list[JsonObject] = []
        for row in rows:
            identity = dict(row["identity"])
            snapshot = row["snapshot_document"]
            revision = row["normalization_document"]
            normalized = (
                dict(revision)
                if isinstance(revision, dict)
                else (dict(snapshot.get("normalized", {})) if isinstance(snapshot, dict) else {})
            )
            media = normalized.get("media", {})
            commerce = normalized.get("commerce", {})
            highlights.append(
                {
                    "canonical_product_id": str(row["canonical_product_id"]),
                    "retailer": str(row["retailer_id"]),
                    "name": str(normalized.get("name") or identity.get("name") or "Product"),
                    "brand": normalized.get("brand") or identity.get("brand"),
                    "seller": normalized.get("seller") or identity.get("seller"),
                    "url": normalized.get("url") or identity.get("url"),
                    "image_url": (
                        (media.get("image_primary") if isinstance(media, dict) else None)
                        or identity.get("image_primary")
                    ),
                    "description": normalized.get("description_short")
                    or normalized.get("description_full"),
                    "category_path": normalized.get("category_path"),
                    "identifiers": normalized.get("identifiers", {}),
                    "specification": normalized.get("specification", {}),
                    "physical_properties": normalized.get("physical_properties", {}),
                    "variant_configuration": normalized.get("variant_configuration", {}),
                    "item_condition": (
                        commerce.get("item_condition")
                        if isinstance(commerce, dict)
                        else identity.get("item_condition")
                    ),
                    "fulfillment": normalized.get("fulfillment", {}),
                    "reviews": normalized.get("reviews", {}),
                    "demand": normalized.get("demand", {}),
                    "content": normalized.get("content", {}),
                    "relationships": normalized.get("relationships", {}),
                    "media": media if isinstance(media, dict) else {},
                    "pdp_source_field_inventory": normalized.get("source_field_inventory", []),
                    "pdp_unmapped_source_fields": normalized.get("unmapped_source_fields", []),
                    "price": normalized.get("price"),
                    "price_currency": normalized.get("price_currency"),
                    "role": (
                        "PDP-enriched reference"
                        if isinstance(snapshot, dict)
                        else "Search identity reference"
                    ),
                }
            )
        return highlights

    async def get_run(self, run_id: str) -> ProductDetailRun | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM product_detail_enrichment_run WHERE id::text = :run_id"
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .first()
            )
            return _run(row) if row is not None else None

    async def run_audit(self, run_id: str) -> JsonObject | None:
        """Return the paid-call ledger and exact request contexts for a PDP run."""

        run = await self.get_run(run_id)
        if run is None:
            return None
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.retailer_product_id, p.identity->>'name' AS product_name,
                              j.retailer_id, j.status, j.request_context,
                              j.last_http_status, j.billable_credits, j.attempt_count,
                              j.last_error, s.id::text AS snapshot_id,
                              s.document AS snapshot_document
                            FROM product_detail_job j
                            JOIN canonical_product p ON p.id = j.canonical_product_id
                            LEFT JOIN LATERAL (
                              SELECT snapshot.id, snapshot.document
                              FROM product_detail_snapshot snapshot
                              WHERE snapshot.product_detail_job_id = j.id
                                AND snapshot.normalized
                              ORDER BY snapshot.observed_at DESC, snapshot.id DESC LIMIT 1
                            ) s ON true
                            WHERE j.enrichment_run_id::text = :run_id
                            ORDER BY j.retailer_id, product_name,
                              p.retailer_product_id, j.created_at, j.id
                            """
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .all()
            )
        calls = [
            {
                "retailer_id": str(row["retailer_id"]),
                "retailer_product_id": str(row["retailer_product_id"]),
                "product_name": str(row["product_name"] or "Unknown product"),
                "status": str(row["status"]),
                "http_status": (
                    int(row["last_http_status"]) if row["last_http_status"] is not None else None
                ),
                "billable_credits": int(row["billable_credits"]),
                "attempt_count": int(row["attempt_count"]),
                "request_context": dict(row["request_context"]),
                "error": str(row["last_error"]) if row["last_error"] is not None else None,
                "snapshot_id": str(row["snapshot_id"]) if row["snapshot_id"] is not None else None,
                "identity_evidence": (
                    dict(row["snapshot_document"].get("normalized", {}))
                    if isinstance(row["snapshot_document"], dict)
                    else None
                ),
            }
            for row in rows
        ]
        http_statuses = sorted(
            {int(row["last_http_status"]) for row in rows if row["last_http_status"] is not None}
        )
        return {
            "run_id": run.id,
            "status": run.status,
            "max_credits": run.max_credits,
            "planned_credits": run.planned_credits,
            "actual_credits": run.actual_credits,
            "planned_calls": len(calls),
            "succeeded_calls": sum(call["status"] == "succeeded" for call in calls),
            "failed_calls": sum(call["status"] == "failed" for call in calls),
            "http_status_counts": {
                str(status): sum(call["http_status"] == status for call in calls)
                for status in http_statuses
            },
            "calls": calls,
        }

    async def reconcile_run(self, run_id: str) -> ProductDetailRun | None:
        """Close an idle run, including a run satisfied entirely from cache."""

        async with self._engine.begin() as connection:
            await self._reconcile_run(connection, run_id)
        return await self.get_run(run_id)

    async def _reconcile_run(self, connection: AsyncConnection, run_id: str) -> None:
        counts = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT count(*) FILTER (
                                 WHERE status IN ('queued', 'running')
                               )::integer AS active_jobs,
                               count(*) FILTER (WHERE status = 'failed')::integer AS failed_jobs
                        FROM product_detail_job WHERE enrichment_run_id::text = :run_id
                        """
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .one()
        )
        if int(counts["active_jobs"]) == 0:
            await connection.execute(
                text(
                    """
                    UPDATE product_detail_enrichment_run
                    SET status = CASE WHEN :failed_jobs > 0
                          THEN 'completed_with_errors' ELSE 'completed' END,
                        completed_at = now()
                            WHERE id::text = :run_id AND status = 'active'
                    """
                ),
                {"failed_jobs": int(counts["failed_jobs"]), "run_id": run_id},
            )

    async def _audit(
        self,
        connection: AsyncConnection,
        event_type: str,
        entity_type: str,
        entity_id: str,
        details: JsonObject,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO audit_event (
                  organization_id, event_type, entity_type, entity_id, details
                ) VALUES (
                  CAST(:organization_id AS uuid), :event_type, :entity_type,
                  :entity_id, CAST(:details AS jsonb)
                )
                """
            ),
            {
                "organization_id": self._organization_id,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "details": _json(details),
            },
        )
