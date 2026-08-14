"""In-memory Product Details repository for deterministic service tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from rci_contracts import validate_instance
from rci_products.documents import (
    canonical_product_document,
    serp_identity,
    snapshot_document,
)
from rci_products.models import (
    CanonicalProductRecord,
    EnqueueProductDetailResult,
    JsonObject,
    ProductDetailEndpoint,
    ProductDetailFetchResult,
    ProductDetailJob,
    ProductDetailRequestContext,
    ProductDetailRun,
    ProductDetailSnapshotRecord,
    ProductDetailStatus,
    sha256_document,
)
from rci_products.repository import ProductDetailBudgetExceeded, require_positive_budget


@dataclass(slots=True)
class _JobState:
    job: ProductDetailJob
    available_at: datetime
    locked_by: str | None = None
    lease_expires_at: datetime | None = None


class InMemoryProductDetailRepository:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root
        self._lock = asyncio.Lock()
        self._products: dict[str, CanonicalProductRecord] = {}
        self._product_by_key: dict[tuple[str, str], str] = {}
        self._contexts: dict[str, dict[str, JsonObject]] = {}
        self._runs: dict[str, ProductDetailRun] = {}
        self._jobs: dict[str, _JobState] = {}
        self._job_by_key: dict[tuple[str, str], str] = {}
        self._snapshots: dict[str, ProductDetailSnapshotRecord] = {}
        self._snapshot_ids_by_product: dict[str, list[str]] = {}

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
        now = datetime.now(UTC)
        key = (retailer_id, retailer_product_id)
        async with self._lock:
            product_id = self._product_by_key.get(key)
            if product_id is None:
                product_id = str(uuid4())
                identity, checksum = serp_identity(
                    name=name,
                    brand=brand,
                    url=url,
                    image_primary=image_primary,
                )
                record = CanonicalProductRecord(
                    id=product_id,
                    canonical_product_id=f"{retailer_id}:{retailer_product_id}",
                    retailer_id=retailer_id,
                    retailer_product_id=retailer_product_id,
                    identifiers={
                        "retailer_product_id": retailer_product_id,
                        **identifiers,
                    },
                    identity=identity,
                    identity_checksum=checksum,
                    created_at=now,
                    updated_at=now,
                )
                self._products[product_id] = record
                self._product_by_key[key] = product_id
            else:
                record = self._products[product_id]
            context_checksum = sha256_document(context)
            self._contexts.setdefault(product_id, {})[context_checksum] = dict(context)
            return record

    async def create_run(
        self,
        *,
        max_credits: int,
        active: bool = True,
    ) -> ProductDetailRun:
        run = ProductDetailRun(
            id=str(uuid4()),
            max_credits=require_positive_budget(max_credits),
            planned_credits=0,
            actual_credits=0,
            status="active" if active else "planning",
        )
        async with self._lock:
            self._runs[run.id] = run
        return run

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
        now = datetime.now(UTC)
        async with self._lock:
            for snapshot in reversed(tuple(self._snapshots.values())):
                if (
                    snapshot.request_checksum == checksum
                    and snapshot.cache_expires_at is not None
                    and snapshot.cache_expires_at > now
                    and snapshot.document.get("normalized") is not None
                ):
                    return EnqueueProductDetailResult(
                        job_id=None,
                        snapshot_id=snapshot.id,
                        request_checksum=checksum,
                        cached=True,
                        created=False,
                    )
            existing_job_id = self._job_by_key.get((run_id, checksum))
            if existing_job_id is not None:
                return EnqueueProductDetailResult(
                    job_id=existing_job_id,
                    snapshot_id=None,
                    request_checksum=checksum,
                    cached=False,
                    created=False,
                )
            run = self._runs[run_id]
            if run.status not in {"planning", "active"}:
                raise ValueError("Product Details run is not open for planning")
            planned = run.planned_credits + endpoint.credits_per_successful_page
            if planned > run.max_credits:
                raise ProductDetailBudgetExceeded(
                    f"Product Details credit ceiling {run.max_credits} would be exceeded"
                )
            self._runs[run_id] = ProductDetailRun(
                id=run.id,
                max_credits=run.max_credits,
                planned_credits=planned,
                actual_credits=run.actual_credits,
                status=run.status,
            )
            job_id = str(uuid4())
            job = ProductDetailJob(
                id=job_id,
                run_id=run_id,
                canonical_product_db_id=product.id,
                canonical_product_id=product.canonical_product_id,
                retailer_id=product.retailer_id,
                endpoint=endpoint,
                context=context,
                request_checksum=checksum,
                credits_per_call=endpoint.credits_per_successful_page,
                status="queued",
                attempt_count=0,
                max_attempts=max_attempts,
            )
            self._jobs[job_id] = _JobState(job=job, available_at=now)
            self._job_by_key[(run_id, checksum)] = job_id
            return EnqueueProductDetailResult(
                job_id=job_id,
                snapshot_id=None,
                request_checksum=checksum,
                cached=False,
                created=True,
            )

    async def claim(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: int,
    ) -> list[ProductDetailJob]:
        if limit < 1 or lease_seconds < 1:
            raise ValueError("Product Details claim limits must be positive")
        now = datetime.now(UTC)
        claimed: list[ProductDetailJob] = []
        async with self._lock:
            for state in self._jobs.values():
                reclaimable = (
                    state.job.status == "running"
                    and state.lease_expires_at is not None
                    and state.lease_expires_at <= now
                )
                if not (
                    (state.job.status == "queued" and state.available_at <= now) or reclaimable
                ):
                    continue
                if state.job.attempt_count >= state.job.max_attempts:
                    continue
                state.job = replace(
                    state.job,
                    status="running",
                    attempt_count=state.job.attempt_count + 1,
                )
                state.locked_by = worker_id
                state.lease_expires_at = now + timedelta(seconds=lease_seconds)
                claimed.append(state.job)
                if len(claimed) >= limit:
                    break
        return claimed

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
        now = datetime.now(UTC)
        snapshot_id = str(uuid4())
        document = snapshot_document(job, result, snapshot_id=snapshot_id)
        validate_instance(
            self._root,
            "product-detail-snapshot.schema.json",
            document,
            label=f"snapshot:{snapshot_id}",
        )
        async with self._lock:
            state = self._jobs[job.id]
            if state.locked_by != worker_id or state.job.status != "running":
                raise ValueError("Product Details job lease is not owned by this worker")
            cache_expires_at = (
                now + timedelta(seconds=cache_ttl_seconds)
                if result.normalized is not None
                else None
            )
            snapshot = ProductDetailSnapshotRecord(
                id=snapshot_id,
                canonical_product_db_id=job.canonical_product_db_id,
                canonical_product_id=job.canonical_product_id,
                request_checksum=job.request_checksum,
                document=document,
                cache_expires_at=cache_expires_at,
            )
            self._snapshots[snapshot_id] = snapshot
            self._snapshot_ids_by_product.setdefault(job.canonical_product_db_id, []).append(
                snapshot_id
            )
            run = self._runs[job.run_id]
            self._runs[job.run_id] = ProductDetailRun(
                id=run.id,
                max_credits=run.max_credits,
                planned_credits=run.planned_credits,
                actual_credits=run.actual_credits + result.credits,
                status=run.status,
            )
            if result.normalized is not None:
                current = self._products[job.canonical_product_db_id]
                pdp_identity = result.normalized.identity_document()
                merged_identity = {
                    **current.identity,
                    **{key: value for key, value in pdp_identity.items() if value is not None},
                }
                self._products[current.id] = CanonicalProductRecord(
                    id=current.id,
                    canonical_product_id=current.canonical_product_id,
                    retailer_id=current.retailer_id,
                    retailer_product_id=current.retailer_product_id,
                    identifiers={**current.identifiers, **result.normalized.identifiers},
                    identity=merged_identity,
                    identity_checksum=sha256_document(merged_identity),
                    created_at=current.created_at,
                    updated_at=now,
                )
                next_status: ProductDetailStatus = "succeeded"
            elif result.should_retry and job.attempt_count < job.max_attempts:
                next_status = "queued"
                state.available_at = now + timedelta(seconds=result.retry_delay_seconds)
            else:
                next_status = "failed"
            state.job = replace(state.job, status=next_status)
            state.locked_by = None
            state.lease_expires_at = None
            self._reconcile_run_locked(job.run_id)
            return snapshot

    async def fail_transport(
        self,
        job: ProductDetailJob,
        worker_id: str,
        message: str,
        *,
        retry_delay_seconds: float,
    ) -> None:
        del message
        now = datetime.now(UTC)
        async with self._lock:
            state = self._jobs[job.id]
            if state.locked_by != worker_id or state.job.status != "running":
                raise ValueError("Product Details job lease is not owned by this worker")
            next_status: ProductDetailStatus = (
                "queued" if job.attempt_count < job.max_attempts else "failed"
            )
            state.job = replace(state.job, status=next_status)
            state.available_at = now + timedelta(seconds=max(retry_delay_seconds, 0))
            state.locked_by = None
            state.lease_expires_at = None
            self._reconcile_run_locked(job.run_id)

    async def extend_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        async with self._lock:
            state = self._jobs[job_id]
            if state.job.status != "running" or state.locked_by != worker_id:
                return False
            state.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
            return True

    async def cancel_run(self, run_id: str) -> int:
        canceled = 0
        async with self._lock:
            for state in self._jobs.values():
                if state.job.run_id != run_id or state.job.status != "queued":
                    continue
                state.job = replace(state.job, status="canceled")
                canceled += 1
            run = self._runs[run_id]
            self._runs[run_id] = ProductDetailRun(
                id=run.id,
                max_credits=run.max_credits,
                planned_credits=run.planned_credits,
                actual_credits=run.actual_credits,
                status="canceled",
            )
        return canceled

    async def get_snapshot(self, snapshot_id: str) -> ProductDetailSnapshotRecord | None:
        return self._snapshots.get(snapshot_id)

    async def product_document(self, canonical_product_db_id: str) -> JsonObject:
        product = self._products[canonical_product_db_id]
        document = canonical_product_document(
            product,
            source_contexts=list(self._contexts.get(canonical_product_db_id, {}).values()),
            snapshot_ids=self._snapshot_ids_by_product.get(canonical_product_db_id, []),
        )
        validate_instance(
            self._root,
            "canonical-product.schema.json",
            document,
            label=f"canonical-product:{product.canonical_product_id}",
        )
        return document

    async def publication_highlights(
        self,
        source_artifact_ids: list[str],
        *,
        limit: int = 8,
        per_retailer_limit: int = 16,
    ) -> list[JsonObject]:
        if not source_artifact_ids or limit < 1 or per_retailer_limit < 1:
            return []
        source_ids = set(source_artifact_ids)
        async with self._lock:
            products = [
                product
                for product_id, product in self._products.items()
                if any(
                    context.get("source_artifact_id") in source_ids
                    for context in self._contexts.get(product_id, {}).values()
                )
            ]
            products.sort(key=lambda product: (product.retailer_id, product.canonical_product_id))
            highlights: list[JsonObject] = []
            for product in products[:limit]:
                snapshot_ids = self._snapshot_ids_by_product.get(product.id, [])
                snapshot = self._snapshots[snapshot_ids[-1]].document if snapshot_ids else None
                normalized = (
                    dict(snapshot.get("normalized", {})) if isinstance(snapshot, dict) else {}
                )
                media = normalized.get("media", {})
                commerce = normalized.get("commerce", {})
                highlights.append(
                    {
                        "canonical_product_id": product.canonical_product_id,
                        "retailer": product.retailer_id,
                        "name": str(
                            normalized.get("name") or product.identity.get("name") or "Product"
                        ),
                        "brand": normalized.get("brand") or product.identity.get("brand"),
                        "seller": normalized.get("seller") or product.identity.get("seller"),
                        "url": normalized.get("url") or product.identity.get("url"),
                        "image_url": (
                            (media.get("image_primary") if isinstance(media, dict) else None)
                            or product.identity.get("image_primary")
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
                            else product.identity.get("item_condition")
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
                            "PDP-enriched reference" if snapshot else "Search identity reference"
                        ),
                    }
                )
            return highlights

    async def get_run(self, run_id: str) -> ProductDetailRun:
        return self._runs[run_id]

    async def reconcile_run(self, run_id: str) -> ProductDetailRun:
        """Close an idle run, including a run satisfied entirely from cache."""

        async with self._lock:
            self._reconcile_run_locked(run_id)
            return self._runs[run_id]

    def _reconcile_run_locked(self, run_id: str) -> None:
        run = self._runs[run_id]
        if run.status != "active":
            return
        statuses = [state.job.status for state in self._jobs.values() if state.job.run_id == run_id]
        if any(status in {"queued", "running"} for status in statuses):
            return
        self._runs[run_id] = ProductDetailRun(
            id=run.id,
            max_credits=run.max_credits,
            planned_credits=run.planned_credits,
            actual_credits=run.actual_credits,
            status="completed_with_errors" if "failed" in statuses else "completed",
        )
