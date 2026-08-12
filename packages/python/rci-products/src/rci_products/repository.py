"""Durable Product Details repository protocol and Postgres implementation."""

from __future__ import annotations

from typing import Protocol

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
)


class ProductDetailBudgetExceeded(ValueError):
    """The durable enrichment-run credit ceiling would be exceeded."""


class ProductDetailRepository(Protocol):
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
    ) -> CanonicalProductRecord: ...

    async def create_run(
        self,
        *,
        max_credits: int,
        active: bool = True,
    ) -> ProductDetailRun: ...

    async def enqueue(
        self,
        run_id: str,
        product: CanonicalProductRecord,
        endpoint: ProductDetailEndpoint,
        context: ProductDetailRequestContext,
        *,
        max_attempts: int = 3,
    ) -> EnqueueProductDetailResult: ...

    async def claim(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: int,
    ) -> list[ProductDetailJob]: ...

    async def record_fetch(
        self,
        job: ProductDetailJob,
        worker_id: str,
        result: ProductDetailFetchResult,
        *,
        cache_ttl_seconds: int,
    ) -> ProductDetailSnapshotRecord: ...

    async def fail_transport(
        self,
        job: ProductDetailJob,
        worker_id: str,
        message: str,
        *,
        retry_delay_seconds: float,
    ) -> None: ...

    async def extend_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> bool: ...

    async def cancel_run(self, run_id: str) -> int: ...

    async def get_snapshot(self, snapshot_id: str) -> ProductDetailSnapshotRecord | None: ...

    async def product_document(self, canonical_product_db_id: str) -> JsonObject: ...

    async def publication_highlights(
        self,
        source_artifact_ids: list[str],
        *,
        limit: int = 8,
        per_retailer_limit: int = 16,
    ) -> list[JsonObject]: ...

    async def get_run(self, run_id: str) -> ProductDetailRun | None: ...

    async def run_audit(self, run_id: str) -> JsonObject | None: ...

    async def reconcile_run(self, run_id: str) -> ProductDetailRun | None: ...


def require_positive_budget(value: int) -> int:
    if value < 1:
        raise ValueError("Product Details max_credits must be positive")
    return value
